"""Server-derived roles and project membership; clients cannot grant permissions."""
from fastapi import HTTPException
from . import db

def admin(user):
    if user.get('role','ADMIN')!='ADMIN': raise HTTPException(403,'Administrator access is required.')

def writer(user):
    if user.get('role','ADMIN')=='VIEWER': raise HTTPException(403,'This account has read-only access.')

def project(conn,user,ident,write=False,*,include_deleted=False):
    row=conn.execute('SELECT p.*,m.role AS member_role FROM projects p LEFT JOIN project_members m ON m.project_id=p.id AND m.user_id=%s WHERE p.id=%s',(user['id'],ident)).fetchone()
    if not row or (row['deleted_at'] is not None and not include_deleted) or (user.get('role','ADMIN')!='ADMIN' and row['member_role'] is None): raise HTTPException(404,'Project not found or access unavailable.')
    if write:
        writer(user)
        if row['archived_at'] is not None: raise HTTPException(409,'Restore the archived project before making changes.')
        if user.get('role','ADMIN')!='ADMIN' and row['member_role'] not in ('OWNER','EDITOR'): raise HTTPException(403,'Project editor access is required.')
    return row

def allowed_projects(user, deleted=False):
    if user.get('role','ADMIN')=='ADMIN':
        return db.query('SELECT * FROM projects WHERE (deleted_at IS NOT NULL)=%s ORDER BY created_at', (deleted,))
    return db.query("""SELECT p.*,m.role AS member_role FROM projects p JOIN project_members m ON p.id=m.project_id
        WHERE m.user_id=%s AND (p.deleted_at IS NOT NULL)=%s AND (NOT %s OR p.owner_id=%s)
        ORDER BY p.created_at""", (user['id'],deleted,deleted,user['id']))

def agent(conn,user,ident):
    row=conn.execute('SELECT * FROM agents WHERE id=%s',(ident,)).fetchone()
    if not row or (user.get('role','ADMIN')!='ADMIN' and row['owner_id']!=user['id']):raise HTTPException(404,'Agent not found or access unavailable.')
    return row
