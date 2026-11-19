"""Project management, source versions and first-class versioned artifacts."""
import hashlib
import json
import re
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,Field,field_validator
from typing import Literal
from . import access,auth,db

router=APIRouter(prefix='/api/v1')

class ProjectEdit(BaseModel):
    name:str=Field(min_length=1,max_length=120)
    description:str=Field(default='',max_length=4000)
    instructions:str=Field(default='',max_length=8000)

@router.put('/projects/{ident}')
def edit_project(ident:uuid.UUID,body:ProjectEdit,user=Depends(auth.session)):
    with db.connect() as conn:
        access.project(conn,user,ident,True)
        conn.execute('UPDATE projects SET name=%s,description=%s,instructions=%s,updated_at=now() WHERE id=%s',(body.name,body.description,body.instructions,ident))
        db.event('project.updated',user['id'],{'project_id':str(ident)},conn=conn)
    return {'ok':True}

@router.get('/projects/{ident}/members')
def members(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:
        access.project(conn,user,ident)
        return conn.execute('SELECT m.*,u.username FROM project_members m JOIN users u ON u.id=m.user_id WHERE project_id=%s ORDER BY u.username',(ident,)).fetchall()

class Membership(BaseModel):
    username:str=Field(min_length=2,max_length=64)
    role:Literal['EDITOR','VIEWER']

@router.put('/projects/{ident}/members')
def add_member(ident:uuid.UUID,body:Membership,user=Depends(auth.session)):
    with db.connect() as conn:
        p=access.project(conn,user,ident,True)
        if user['role']!='ADMIN' and p['owner_id']!=user['id']:raise HTTPException(403,'Project owner access is required.')
        target=conn.execute('SELECT id FROM users WHERE username=%s AND enabled',(body.username,)).fetchone()
        if not target:raise HTTPException(422,'Active account not found.')
        if target['id']==p['owner_id']:raise HTTPException(409,'The owner membership cannot be replaced.')
        conn.execute('INSERT INTO project_members VALUES (%s,%s,%s) ON CONFLICT(project_id,user_id) DO UPDATE SET role=excluded.role',(ident,target['id'],body.role))
        db.event('project.member_updated',user['id'],{'project_id':str(ident),'user_id':str(target['id']),'role':body.role},conn=conn)
    return {'ok':True}

@router.delete('/projects/{ident}/members/{member}')
def remove_member(ident:uuid.UUID,member:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:
        p=access.project(conn,user,ident,True)
        if user['role']!='ADMIN' and p['owner_id']!=user['id']:raise HTTPException(403,'Project owner access is required.')
        if member==p['owner_id']:raise HTTPException(409,'The owner membership cannot be removed.')
        conn.execute('DELETE FROM project_members WHERE project_id=%s AND user_id=%s',(ident,member))
        db.event('project.member_removed',user['id'],{'project_id':str(ident),'user_id':str(member)},conn=conn)
    return {'ok':True}

@router.get('/documents/{ident}')
def source(ident:uuid.UUID,version:int|None=None,user=Depends(auth.session)):
    with db.connect() as conn:
        row=conn.execute('SELECT * FROM documents WHERE id=%s',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Source not found.')
        access.project(conn,user,row['project_id'])
        if version is not None:
            prior=conn.execute('SELECT title,content FROM document_versions WHERE document_id=%s AND version=%s',(ident,version)).fetchone()
            if not prior:raise HTTPException(404,'Source version not found.')
            row.update(prior)
        row['versions']=conn.execute('SELECT version,created_at FROM document_versions WHERE document_id=%s ORDER BY version DESC',(ident,)).fetchall()
        return row

class SourceEdit(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    content:str=Field(min_length=1,max_length=200000)
    enabled:bool=True
    expected_version:int=Field(ge=1)

@router.put('/documents/{ident}')
def edit_source(ident:uuid.UUID,body:SourceEdit,user=Depends(auth.session)):
    with db.connect() as conn:
        row=conn.execute('SELECT * FROM documents WHERE id=%s FOR UPDATE',(ident,)).fetchone()
        if not row:raise HTTPException(404,'Source not found.')
        access.project(conn,user,row['project_id'],True)
        if row['version']!=body.expected_version:raise HTTPException(409,'This source changed elsewhere. Reload before saving.')
        version=row['version']+1
        conn.execute('UPDATE documents SET title=%s,content=%s,enabled=%s,version=%s,updated_at=now() WHERE id=%s',(body.title,body.content,body.enabled,version,ident))
        conn.execute('INSERT INTO document_versions(document_id,project_id,version,title,content) VALUES (%s,%s,%s,%s,%s)',(ident,row['project_id'],version,body.title,body.content))
        db.event('source.updated',user['id'],{'document_id':str(ident),'version':version,'enabled':body.enabled},conn=conn)
    return {'version':version}

class Artifact(BaseModel):
    title:str=Field(min_length=1,max_length=200)
    kind:Literal['markdown','text','code','json']='markdown'
    language:str=Field(default='',max_length=40,pattern=r'^[A-Za-z0-9_.+-]*$')
    content:str=Field(default='',max_length=200000)
    project_id:uuid.UUID|None=None
    visibility:Literal['PRIVATE','PROJECT']='PRIVATE'
    source_message_id:uuid.UUID|None=None
    source_run_id:uuid.UUID|None=None
    @field_validator('content','title')
    @classmethod
    def text_only(cls,v):
        if '\0' in v:raise ValueError('Null characters are not allowed.')
        return v

class SaveArtifact(Artifact):
    expected_version:int=Field(ge=1)
    reason:str=Field(default='',max_length=500)

def artifact_access(conn,user,ident,write=False):
    row=conn.execute('SELECT * FROM workspace_artifacts WHERE id=%s'+(' FOR UPDATE' if write else ''),(ident,)).fetchone()
    if not row:raise HTTPException(404,'Artifact not found.')
    if user['role']=='ADMIN' or row['owner_id']==user['id']:
        if write:access.writer(user)
        return row
    if row['visibility']=='PROJECT' and row['project_id']:
        access.project(conn,user,row['project_id'],write)
        return row
    raise HTTPException(404,'Artifact not found.')

def validate_artifact(conn,user,body):
    access.writer(user)
    if body.project_id:access.project(conn,user,body.project_id,True)
    if body.visibility=='PROJECT' and not body.project_id:raise HTTPException(422,'Choose a project before sharing with project members.')
    if body.kind=='json':
        try:json.loads(body.content)
        except ValueError:raise HTTPException(422,'The artifact content must be valid JSON.')
    if body.source_message_id and not conn.execute('SELECT m.id FROM chat_messages m JOIN conversations c ON c.id=m.conversation_id WHERE m.id=%s AND c.user_id=%s',(body.source_message_id,user['id'])).fetchone():raise HTTPException(404,'Source message not found.')
    if body.source_run_id:
        run=conn.execute('SELECT project_id FROM runs WHERE id=%s',(body.source_run_id,)).fetchone()
        if not run:raise HTTPException(404,'Source task not found.')
        access.project(conn,user,run['project_id'])

def new_artifact(conn,user,body):
    validate_artifact(conn,user,body)
    ident=uuid.uuid4()
    conn.execute('''INSERT INTO workspace_artifacts(id,owner_id,project_id,title,kind,language,visibility,source_run_id,source_message_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(ident,user['id'],body.project_id,body.title,body.kind,body.language,body.visibility,body.source_run_id,body.source_message_id))
    conn.execute('INSERT INTO artifact_versions(id,artifact_id,version,content,sha256,actor_id,reason) VALUES (%s,%s,1,%s,%s,%s,%s)',(uuid.uuid4(),ident,body.content,hashlib.sha256(body.content.encode()).hexdigest(),user['id'],'Created'))
    db.event('artifact.created',user['id'],{'artifact_id':str(ident)},conn=conn)
    return ident

@router.get('/library/artifacts')
def artifact_list(source_message_id:uuid.UUID|None=None,user=Depends(auth.session)):
    return db.query('''SELECT a.*,u.username AS owner FROM workspace_artifacts a JOIN users u ON u.id=a.owner_id
        WHERE (a.owner_id=%s OR %s='ADMIN' OR (a.visibility='PROJECT' AND EXISTS(SELECT 1 FROM project_members m WHERE m.project_id=a.project_id AND m.user_id=%s)))
        AND (%s::uuid IS NULL OR (a.owner_id=%s AND a.source_message_id=%s))
        ORDER BY a.updated_at DESC LIMIT 200''',(user['id'],user['role'],user['id'],source_message_id,user['id'],source_message_id))

@router.post('/library/artifacts',status_code=201)
def artifact_create(body:Artifact,user=Depends(auth.session)):
    with db.connect() as conn:ident=new_artifact(conn,user,body)
    return {'id':ident,'version':1}

@router.get('/library/artifacts/{ident}')
def artifact_detail(ident:uuid.UUID,version:int|None=None,user=Depends(auth.session)):
    with db.connect() as conn:
        row=artifact_access(conn,user,ident)
        selected=conn.execute('SELECT * FROM artifact_versions WHERE artifact_id=%s AND version=%s',(ident,version or row['version'])).fetchone()
        if not selected:raise HTTPException(404,'Artifact version not found.')
        row['content']=selected['content'];row['selected_version']=selected['version']
        row['versions']=conn.execute('SELECT version,created_at,reason,sha256 FROM artifact_versions WHERE artifact_id=%s ORDER BY version DESC',(ident,)).fetchall()
        row['can_share']=user['role']!='VIEWER' and (user['role']=='ADMIN' or row['owner_id']==user['id'])
        row['can_edit']=row['can_share']
        if not row['can_edit'] and row['visibility']=='PROJECT' and user['role']!='VIEWER':
            try:access.project(conn,user,row['project_id'],True);row['can_edit']=True
            except HTTPException:pass
        return row

@router.put('/library/artifacts/{ident}')
def artifact_save(ident:uuid.UUID,body:SaveArtifact,user=Depends(auth.session)):
    with db.connect() as conn:
        row=artifact_access(conn,user,ident,True)
        validate_artifact(conn,user,body)
        if user['role']!='ADMIN' and row['owner_id']!=user['id'] and (body.visibility!=row['visibility'] or body.project_id!=row['project_id']):raise HTTPException(403,'Only the owner can change artifact sharing.')
        if row['version']!=body.expected_version:raise HTTPException(409,'A newer artifact version exists. Reload or save a separate copy.')
        version=row['version']+1
        conn.execute('UPDATE workspace_artifacts SET title=%s,kind=%s,language=%s,project_id=%s,visibility=%s,version=%s,updated_at=now() WHERE id=%s',(body.title,body.kind,body.language,body.project_id,body.visibility,version,ident))
        conn.execute('INSERT INTO artifact_versions(id,artifact_id,version,content,sha256,actor_id,reason) VALUES (%s,%s,%s,%s,%s,%s,%s)',(uuid.uuid4(),ident,version,body.content,hashlib.sha256(body.content.encode()).hexdigest(),user['id'],body.reason))
        db.event('artifact.saved',user['id'],{'artifact_id':str(ident),'version':version},conn=conn)
    return {'id':ident,'version':version}

class NewUser(BaseModel):
    username:str=Field(pattern=r'^[a-z][a-z0-9_@.\-]{1,63}$')
    password:str=Field(min_length=12,max_length=256)
    role:Literal['ADMIN','EDITOR','VIEWER']='EDITOR'

@router.get('/access/users')
def users(user=Depends(auth.session)):
    access.admin(user)
    return db.query('SELECT id,username,role,enabled,created_at FROM users ORDER BY created_at')

@router.post('/access/users',status_code=201)
def create_user(body:NewUser,user=Depends(auth.session)):
    access.admin(user)
    if db.query('SELECT id FROM users WHERE username=%s',(body.username,),one=True):raise HTTPException(409,'Username already exists.')
    ident=uuid.uuid4()
    db.query('INSERT INTO users(id,username,password_hash,role) VALUES (%s,%s,%s,%s)',(ident,body.username,auth.password_hash(body.password),body.role))
    db.event('account.created',user['id'],{'user_id':str(ident),'role':body.role})
    return {'id':ident}

class UserState(BaseModel):
    role:Literal['ADMIN','EDITOR','VIEWER']
    enabled:bool

@router.put('/access/users/{ident}')
def user_state(ident:uuid.UUID,body:UserState,user=Depends(auth.session)):
    access.admin(user)
    if ident==user['id'] and (not body.enabled or body.role!='ADMIN'):raise HTTPException(409,'Keep your own administrator access. Use another administrator for this change.')
    with db.connect() as conn:
        if not conn.execute('UPDATE users SET role=%s,enabled=%s WHERE id=%s RETURNING id',(body.role,body.enabled,ident)).fetchone():raise HTTPException(404,'Account not found.')
        conn.execute('DELETE FROM sessions WHERE user_id=%s',(ident,))
        db.event('account.access_changed',user['id'],{'user_id':str(ident),'role':body.role,'enabled':body.enabled},conn=conn)
    return {'ok':True}

@router.get('/capabilities')
def capabilities(user=Depends(auth.session)):
    return {'role':user['role'],'features':[
        {'id':'chat','label':'Conversations','status':'implemented','reason':'Durable private threads and incremental local replies.'},
        {'id':'files','label':'Files and project sources','status':'implemented','reason':'Text/code, PDF text, DOCX, XLSX and CSV. Scanned PDFs need OCR, which is unavailable.'},
        {'id':'artifacts','label':'Artifact editor','status':'implemented','reason':'Versioned Markdown, text, code and JSON with private/project access.'},
        {'id':'agent-tools','label':'Bounded agent tools','status':'implemented','reason':'Project inspection, knowledge retrieval and artifact creation. Requires a tools-capable model.'},
        {'id':'code-execution','label':'Repository execution','status':'planned','reason':'No qualified coding sandbox is configured. Host shell access is unavailable.'},
        {'id':'workflows','label':'Scheduled workflows','status':'planned','reason':'Scheduling and event-trigger adapters are not implemented.'},
        {'id':'web','label':'Web research connectors','status':'planned','reason':'No external search connector is configured. Local source analysis is available.'},
        {'id':'vision','label':'Vision, OCR and voice','status':'unavailable','reason':'No qualified multimodal processing pipeline is configured.'},
        {'id':'sso','label':'SSO and service tokens','status':'planned','reason':'Local revocable sessions and roles are implemented; external identity/token interfaces are not.'}]}
