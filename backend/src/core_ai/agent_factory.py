"""Human-reviewed agent drafts, derived from actual completed tasks."""
import hashlib
import json
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field
from psycopg.types.json import Jsonb
from . import auth,access,db,capability_policy,agent_runtime

router=APIRouter(prefix="/api/v1/agent-factory")

class Draft(BaseModel):
    model_config=ConfigDict(extra="forbid")
    name:str=Field(min_length=1,max_length=120)
    instructions:str=Field(min_length=1,max_length=16000)
    runtime_mode:str=Field(default="analysis",pattern=r"^(analysis|tools)$")
    tools:list[str]=Field(default_factory=list,max_length=5)
    program_scope:list[str]=Field(default_factory=list,max_length=200)

class Import(BaseModel):
    run_id:uuid.UUID
class Review(BaseModel):
    digest:str=Field(pattern=r"^[0-9a-f]{64}$")
class Qualification(BaseModel):
    run_id:uuid.UUID
    notes:str=Field(min_length=1,max_length=2000)

def draft_for(text):
    raw=text.strip()
    fence=chr(96)*3
    if raw.startswith(fence+"json") and raw.endswith(fence):
        raw=raw[len(fence)+4:-len(fence)].strip()
    draft=Draft.model_validate_json(raw)
    if any(t not in agent_runtime.SCHEMAS for t in draft.tools) or len(set(draft.tools))!=len(draft.tools):
        raise ValueError("Unknown or duplicated tool.")
    capability_policy.validate_scope(draft.program_scope)
    if "*" in draft.program_scope:raise ValueError("Generated drafts must enumerate exact programs.")
    if draft.program_scope and ("program.run" not in draft.tools or draft.runtime_mode!="tools"):
        raise ValueError("Program scope requires Tools mode and program.run.")
    return draft.model_dump(mode="json")

def digest(draft):
    return hashlib.sha256(json.dumps(draft,sort_keys=True,separators=(",",":"),ensure_ascii=False).encode()).hexdigest()

def owned(conn,user,ident):
    row=conn.execute("SELECT * FROM agent_factory_records WHERE id=%s AND owner_id=%s FOR UPDATE",(ident,user["id"])).fetchone()
    if not row:raise HTTPException(404,"Agent draft not found.")
    access.project(conn,user,row["project_id"],True)
    return row

@router.get("")
def listing(user=Depends(auth.session)):
    ids=[p["id"] for p in access.allowed_projects(user)]
    return db.query("""SELECT f.*,a.enabled AS agent_enabled,a.version AS current_version
        FROM agent_factory_records f LEFT JOIN agents a ON a.id=f.agent_id
        WHERE f.owner_id=%s AND f.project_id=ANY(%s::uuid[]) ORDER BY f.created_at DESC LIMIT 100""",(user["id"],ids))

@router.post("/drafts",status_code=201)
def import_draft(body:Import,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        run=conn.execute("SELECT * FROM runs WHERE id=%s AND requested_by=%s AND status='SUCCEEDED' AND connection_id IS NULL",(body.run_id,user["id"])).fetchone()
        if not run or not run["project_id"]:raise HTTPException(404,"Choose your successful project task.")
        access.project(conn,user,run["project_id"],True)
        try: draft=draft_for(run["output"] or "")
        except (ValueError,HTTPException):raise HTTPException(422,"Task output must contain valid agent JSON with supported tools and explicit scope.") from None
        row=conn.execute("""INSERT INTO agent_factory_records(id,owner_id,project_id,source_run,digest,draft)
           VALUES (%s,%s,%s,%s,%s,%s) ON CONFLICT(owner_id,source_run) DO NOTHING RETURNING *""",
           (uuid.uuid4(),user["id"],run["project_id"],body.run_id,digest(draft),Jsonb(draft))).fetchone()
        return row or conn.execute("SELECT * FROM agent_factory_records WHERE owner_id=%s AND source_run=%s",(user["id"],body.run_id)).fetchone()

@router.post("/drafts/{ident}/publish",status_code=201)
def publish(ident:uuid.UUID,body:Review,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=owned(conn,user,ident)
        if body.digest!=row["digest"] or digest(row["draft"])!=row["digest"]:raise HTTPException(409,"Review the exact draft digest.")
        if row["agent_id"]:return {"id":row["agent_id"],"already_published":True}
        draft=row["draft"];agent=uuid.uuid4()
        conn.execute("""INSERT INTO agents(id,name,instructions,owner_id,enabled,runtime_mode,tools,program_scope)
                     VALUES (%s,%s,%s,%s,false,%s,%s,%s)""",(agent,draft["name"],draft["instructions"],user["id"],draft["runtime_mode"],Jsonb(draft["tools"]),Jsonb(draft["program_scope"])))
        conn.execute("UPDATE agent_factory_records SET agent_id=%s,published_at=now() WHERE id=%s",(agent,ident))
        db.event("agent.factory.published",user["id"],{"agent_id":str(agent),"draft_id":str(ident)},conn=conn)
        return {"id":agent,"enabled":False}

@router.post("/drafts/{ident}/qualify")
def qualify(ident:uuid.UUID,body:Qualification,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=owned(conn,user,ident)
        if not row["agent_id"]:raise HTTPException(409,"Publish and review the disabled agent first.")
        agent=access.agent(conn,user,row["agent_id"])
        test=conn.execute("SELECT id,agent_id,agent_version,project_id,status FROM runs WHERE id=%s AND requested_by=%s AND connection_id IS NULL",(body.run_id,user["id"])).fetchone()
        if not test or test["agent_id"]!=agent["id"] or test["agent_version"]!=agent["version"] or test["project_id"]!=row["project_id"] or test["status"]!="SUCCEEDED":
            raise HTTPException(422,"Select a successful test of this exact agent version in the same project.")
        conn.execute("UPDATE agent_factory_records SET qualification_run=%s,qualification_version=%s,reviewer_notes=%s,qualified_at=now() WHERE id=%s",(body.run_id,agent["version"],body.notes,ident))
        db.event("agent.factory.reviewed",user["id"],{"agent_id":str(agent["id"]),"version":agent["version"],"test_run":str(body.run_id)},conn=conn)
        return {"reviewed":True,"version":agent["version"]}
