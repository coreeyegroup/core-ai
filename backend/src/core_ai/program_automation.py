"""Existing connection credentials, with separate opt-in offline recipe scopes."""
import uuid
from typing import Any
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,ConfigDict,Field
from psycopg.types.json import Jsonb
from . import access,auth,db,connections,program_jobs,program_gateway,capability_policy

router=APIRouter(prefix="/api/v1")
class Scope(BaseModel):
    model_config=ConfigDict(extra="forbid")
    recipes:list[str]=Field(default_factory=list,max_length=200)
class Submit(BaseModel):
    model_config=ConfigDict(extra="forbid")
    request_id:uuid.UUID
    recipe:str=Field(pattern=r"^[a-z0-9-]{1,80}$")
    values:list[Any]=Field(default_factory=list,max_length=1000)

def eligible(p):
    return p["state"]=="qualified-receipt" and not p["extensions"] and not p["output_file"]

@router.get("/connections/{ident}/program-scope")
def scope(ident:uuid.UUID,user=Depends(auth.session)):
    access.admin(user)
    row=db.query("SELECT program_scope FROM automation_connections WHERE id=%s",(ident,),one=True)
    if not row:raise HTTPException(404,"Connection not found.")
    return {"recipes":row["program_scope"]}

@router.put("/connections/{ident}/program-scope")
def configure(ident:uuid.UUID,body:Scope,user=Depends(auth.session)):
    access.admin(user)
    recipes=capability_policy.validate_scope(body.recipes)
    if "*" in recipes:raise HTTPException(422,"External keys require exact recipe IDs.")
    if recipes and not set(recipes)<={p["id"] for p in program_gateway.get_catalog()["programs"] if eligible(p)}:
        raise HTTPException(422,"Choose qualified non-file offline programs.")
    row=db.query("UPDATE automation_connections SET program_scope=%s WHERE id=%s AND revoked_at IS NULL RETURNING id",(Jsonb(recipes),ident),one=True)
    if not row:raise HTTPException(404,"Active connection not found.")
    db.event("connection.program_scope.updated",user["id"],{"id":str(ident),"recipes":recipes})
    return {"recipes":recipes}

@router.get("/automation/programs")
def catalog(request:Request):
    with db.connect() as conn:
        c=connections.authenticated_connection(conn,request)
        if not c["can_discover"]:raise HTTPException(403,"Discovery disabled.")
    return {"programs":[{k:p[k] for k in ("id","fields","example","mode","commit")} for p in program_gateway.get_catalog()["programs"] if p["id"] in c["program_scope"] and eligible(p)]}

@router.post("/automation/programs/jobs",status_code=202)
def submit(body:Submit,request:Request):
    with db.connect() as conn:
        c=connections.authenticated_connection(conn,request)
        if not c["can_submit"] or body.recipe not in c["program_scope"]:raise HTTPException(403,"Program not permitted.")
    pin=program_jobs.qualified(body.recipe)
    if not eligible(pin):raise HTTPException(422,"File programs require the authenticated workspace.")
    with db.connect() as conn:
        c=connections.authenticated_connection(conn,request)
        if not c["can_submit"] or body.recipe not in c["program_scope"]:raise HTTPException(403,"Program not permitted.")
        previous=conn.execute("SELECT id FROM program_jobs WHERE connection_id=%s AND request_id=%s",(c["id"],body.request_id)).fetchone()
        if not previous:
            usage=conn.execute("""SELECT count(*) FILTER(WHERE created_at>now()-interval '1 minute') AS recent,
                 count(*) FILTER(WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS pending
                 FROM program_jobs WHERE connection_id=%s""",(c["id"],)).fetchone()
            if usage["recent"]>=c["requests_per_minute"]:raise HTTPException(429,"Connection rate limit reached.")
            if usage["pending"]>=c["max_pending"]:raise HTTPException(409,"Connection queue full.")
        user={"id":c["created_by"],"role":c["role"]}
        return {"id":program_jobs.insert(conn,user,program_gateway.RunInput(recipe=body.recipe,values=body.values),body.request_id,c["project_id"],pin,connection_id=c["id"])}

@router.get("/automation/programs/jobs/{ident}")
def detail(ident:uuid.UUID,request:Request):
    with db.connect() as conn:
        c=connections.authenticated_connection(conn,request)
        if not c["can_read"]:raise HTTPException(403,"Reading disabled.")
        row=conn.execute("SELECT id,recipe,project_id,status,result,error,error_code,created_at,finished_at FROM program_jobs WHERE id=%s AND connection_id=%s",(ident,c["id"])).fetchone()
        if not row or row["project_id"]!=c["project_id"]:raise HTTPException(404,"Program job not found.")
        if row["project_id"]:access.project(conn,{"id":c["created_by"],"role":c["role"]},row["project_id"])
        return row

@router.post("/automation/programs/jobs/{ident}/cancel")
def cancel(ident:uuid.UUID,request:Request):
    with db.connect() as conn:
        c=connections.authenticated_connection(conn,request)
        if not c["can_cancel"]:raise HTTPException(403,"Cancellation disabled.")
        row=conn.execute("SELECT id,status FROM program_jobs WHERE id=%s AND connection_id=%s FOR UPDATE",(ident,c["id"])).fetchone()
        if not row:raise HTTPException(404,"Program job not found.")
        state=program_jobs.cancel_row(conn,ident)
        if not state and row["status"] not in ("CANCELLED","CANCEL_REQUESTED"):raise HTTPException(409,"Job has finished.")
        return {"status":state or row["status"]}
