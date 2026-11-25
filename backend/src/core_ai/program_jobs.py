"""Durable, user-scoped program queue. The gateway remains independent."""
import base64
from concurrent.futures import ThreadPoolExecutor,TimeoutError as FutureTimeout
import hashlib
import json
import time
import uuid
from fastapi import APIRouter,Depends,HTTPException
from fastapi.responses import Response
from pydantic import Field
from psycopg.types.json import Jsonb
from . import access,auth,db,program_gateway as gateway,capability_policy

router=APIRouter(prefix="/api/v1/programs/jobs")
ACTIVE=("QUEUED","RUNNING","CANCEL_REQUESTED")
PUBLIC="id,owner_id,project_id,recipe,status,expected_commit,expected_image,created_at,started_at,finished_at,error_code,error,retry_of,file_name,parent_run,parent_chat,connection_id"
MAX_STORE=128*1024*1024
MAX_JOBS=500

class Submit(gateway.RunInput):
    request_id:uuid.UUID
    project_id:uuid.UUID|None=None

def qualified(recipe):
    row=next((p for p in gateway.get_catalog()["programs"] if p["id"]==recipe and p["state"]=="qualified-receipt"),None)
    if not row: raise HTTPException(422,"Select a qualified program.")
    return row

def digest(data):
    try: raw=json.dumps(data,allow_nan=False,sort_keys=True,separators=(",",":")).encode()
    except (ValueError,TypeError): raise HTTPException(422,"Invalid program input.") from None
    if len(raw)>6*1024*1024: raise HTTPException(413,"Program input exceeds its size limit.")
    return hashlib.sha256(raw).hexdigest()

def insert(conn,user,body,request_id,project_id,pin,*,parent=None,retry_of=None,connection_id=None):
    access.writer(user)
    if project_id: access.project(conn,user,project_id,True)
    data=body.model_dump(mode="json")
    fingerprint=digest({"body":data,"project":str(project_id),"parent":str(parent["id"]) if parent else None,"connection":str(connection_id)})
    conn.execute("SELECT pg_advisory_xact_lock(187875441)")
    previous=conn.execute("SELECT id,input_digest FROM program_jobs WHERE owner_id=%s AND request_id=%s",(user["id"],request_id)).fetchone()
    if previous:
        if previous["input_digest"]!=fingerprint: raise HTTPException(409,"Request ID was already used with different inputs.")
        return previous["id"]
    usage=conn.execute("""SELECT count(*) AS total,count(*) FILTER(WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')) AS pending,
       coalesce(sum(octet_length(input_data::text)+coalesce(octet_length(result::text),0)+coalesce(octet_length(file_data),0)),0) AS bytes
       FROM program_jobs WHERE owner_id=%s""",(user["id"],)).fetchone()
    pending=conn.execute("SELECT count(*) AS n FROM program_jobs WHERE status IN ('QUEUED','RUNNING','CANCEL_REQUESTED')").fetchone()["n"]
    if usage["total"]>=MAX_JOBS or usage["bytes"]+usage["pending"]*12*1024**2+len(json.dumps(data).encode())+12*1024**2>MAX_STORE:
        raise HTTPException(409,"Program history storage limit reached. Export and manage stored jobs.")
    if pending>=30 or usage["pending"]>=10: raise HTTPException(409,"Program queue is full.")
    ident=uuid.uuid4()
    conn.execute("""INSERT INTO program_jobs(id,owner_id,project_id,parent_run,parent_chat,recipe,request_id,input_digest,input_data,
                 expected_commit,expected_image,status,retry_of,connection_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED',%s,%s)""",
                 (ident,user["id"],project_id,parent["id"] if parent and not parent.get("chat_generation") else None,
                  parent["id"] if parent and parent.get("chat_generation") else None,body.recipe,request_id,fingerprint,Jsonb(data),
                  pin["commit"],pin["image"],retry_of,connection_id))
    db.event("program.queued",user["id"],{"id":str(ident),"recipe":body.recipe},conn=conn)
    return ident

def enqueue(user,body,request_id,project_id=None,parent=None,retry_of=None):
    pin=qualified(body.recipe)
    with db.connect() as conn:
        return insert(conn,user,body,request_id,project_id,pin,parent=parent,retry_of=retry_of)

def owned(conn,user,ident,lock=False):
    row=conn.execute("SELECT * FROM program_jobs WHERE id=%s AND owner_id=%s"+(" FOR UPDATE" if lock else ""),(ident,user["id"])).fetchone()
    if not row: raise HTTPException(404,"Program job not found.")
    if row["project_id"]: access.project(conn,user,row["project_id"])
    return row

@router.post("",status_code=201)
def submit(body:Submit,user=Depends(auth.session)):
    access.writer(user)
    payload=gateway.RunInput.model_validate(body.model_dump(exclude={"request_id","project_id"}))
    return {"id":enqueue(user,payload,body.request_id,body.project_id)}

@router.get("")
def listing(user=Depends(auth.session)):
    return db.query("SELECT "+PUBLIC+" FROM program_jobs j WHERE owner_id=%s AND (project_id IS NULL OR EXISTS(SELECT 1 FROM projects p LEFT JOIN project_members m ON m.project_id=p.id AND m.user_id=%s WHERE p.id=j.project_id AND p.deleted_at IS NULL AND (%s='ADMIN' OR m.user_id IS NOT NULL))) ORDER BY created_at DESC LIMIT 100",(user["id"],user["id"],user["role"]))

@router.get("/{ident}")
def detail(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:
        row=owned(conn,user,ident)
        return {k:v for k,v in row.items() if k not in ("input_data","input_digest","file_data","claim_token","lease_until","request_id")}

@router.get("/{ident}/download")
def download(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn: row=owned(conn,user,ident)
    if row["status"]!="SUCCEEDED" or not row["file_data"]: raise HTTPException(404,"No generated file.")
    return Response(bytes(row["file_data"]),media_type="application/octet-stream",headers={"Content-Disposition":'attachment; filename="'+row["file_name"]+'"'})

def cancel_row(conn,ident):
    row=conn.execute("""UPDATE program_jobs SET status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,
                     finished_at=CASE WHEN status='QUEUED' THEN now() ELSE finished_at END
                     WHERE id=%s AND status IN ('QUEUED','RUNNING') RETURNING status""",(ident,)).fetchone()
    return row["status"] if row else None

@router.post("/{ident}/cancel")
def cancel(ident:uuid.UUID,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=owned(conn,user,ident,True)
        if row["project_id"]: access.project(conn,user,row["project_id"],True)
        status=cancel_row(conn,ident)
        if not status:
            if row["status"] in ("CANCEL_REQUESTED","CANCELLED"): status=row["status"]
            else: raise HTTPException(409,"Program job has finished.")
        return {"status":status}

@router.post("/{ident}/retry",status_code=201)
def retry(ident:uuid.UUID,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn: row=owned(conn,user,ident)
    if row["status"] not in ("FAILED","CANCELLED") or row["parent_run"] or row["parent_chat"] or row["connection_id"]:
        raise HTTPException(409,"Retry a failed or cancelled standalone job, or retry its parent workflow.")
    body=gateway.RunInput.model_validate(row["input_data"])
    pin=qualified(body.recipe)
    if (pin["commit"],pin["image"])!=(row["expected_commit"],row["expected_image"]):
        raise HTTPException(409,"Version changed; submit a new reviewed job.")
    with db.connect() as conn:
        return {"id":insert(conn,user,body,uuid.uuid4(),row["project_id"],pin,retry_of=ident)}

def claim():
    with db.connect() as conn:
        conn.execute("SELECT pg_advisory_xact_lock(187875442)")
        conn.execute("""UPDATE program_jobs SET status=CASE WHEN status='CANCEL_REQUESTED' THEN 'CANCELLED' ELSE 'FAILED' END,
                     error_code='LEASE_EXPIRED',error='Worker interrupted; review before retry.',finished_at=now(),lease_until=NULL,claim_token=NULL
                     WHERE status IN ('RUNNING','CANCEL_REQUESTED') AND lease_until<now()""")
        if conn.execute("SELECT id FROM program_jobs WHERE status IN ('RUNNING','CANCEL_REQUESTED') LIMIT 1").fetchone(): return None
        row=conn.execute("SELECT * FROM program_jobs WHERE status='QUEUED' ORDER BY (parent_run IS NULL AND parent_chat IS NULL),created_at,id FOR UPDATE SKIP LOCKED LIMIT 1").fetchone()
        if not row:return None
        token=uuid.uuid4()
        conn.execute("UPDATE program_jobs SET status='RUNNING',claim_token=%s,lease_until=now()+interval '30 seconds',started_at=now() WHERE id=%s",(token,row["id"]))
        return {**row,"claim_token":token,"status":"RUNNING"}

def authorize(row):
    with db.connect() as conn:
        user=conn.execute("SELECT id,role FROM users WHERE id=%s AND enabled",(row["owner_id"],)).fetchone()
        if not user: raise ValueError("Account disabled.")
        access.writer(user)
        if row["project_id"]: access.project(conn,user,row["project_id"],True)
        if row["connection_id"]:
            c=conn.execute("""SELECT id,program_scope,can_submit,project_id FROM automation_connections
                WHERE id=%s AND created_by=%s AND revoked_at IS NULL AND NOT paused
                AND (expires_at IS NULL OR expires_at>now())""",(row["connection_id"],user["id"])).fetchone()
            if not c or user["role"]!="ADMIN" or not c["can_submit"] or row["recipe"] not in c["program_scope"] or c["project_id"]!=row["project_id"]:
                raise ValueError("Connection program permission revoked.")
        parent=None
        if row["parent_run"]:
            parent=conn.execute("SELECT * FROM runs WHERE id=%s",(row["parent_run"],)).fetchone()
        elif row["parent_chat"]:
            parent=conn.execute("SELECT * FROM chat_generations WHERE id=%s",(row["parent_chat"],)).fetchone()
            if parent: parent["chat_generation"]=True
    if row["parent_run"] or row["parent_chat"]:
        if not parent or parent["status"]!="RUNNING" or parent["requested_by"]!=row["owner_id"]:
            raise InterruptedError("Parent stopped.")
        if not capability_policy.program_allowed(parent,user,row["recipe"]):
            raise ValueError("Program permission revoked.")

def finish(row,status,*,result=None,code=None,error=None):
    file_name=file_data=None
    if result is not None:
        result=dict(result)
        generated=result.pop("file",None)
        if generated:
            file_name=generated["name"]
            if file_name not in ("result.docx","result.xlsx","result.ipynb"): raise ValueError("Unexpected file type.")
            file_data=base64.b64decode(generated["data"],validate=True)
            if len(file_data)>6*1024**2: raise ValueError("Output exceeds limit.")
    with db.connect() as conn:
        current=conn.execute("SELECT status,claim_token,lease_until>now() AS valid FROM program_jobs WHERE id=%s FOR UPDATE",(row["id"],)).fetchone()
        if not current or current["claim_token"]!=row["claim_token"] or not current["valid"]:return
        if current["status"]=="CANCEL_REQUESTED":
            status,result,file_name,file_data,code,error="CANCELLED",None,None,None,None,None
        conn.execute("""UPDATE program_jobs SET status=%s,result=%s,file_name=%s,file_data=%s,error_code=%s,error=%s,
             finished_at=now(),claim_token=NULL,lease_until=NULL WHERE id=%s""",(status,Jsonb(result) if result is not None else None,file_name,file_data,code,error,row["id"]))
        db.event("program."+status.lower(),row["owner_id"],{"id":str(row["id"]),"recipe":row["recipe"],"code":code},conn=conn)

def process(row,stopping=None):
    try:
        state=db.query("SELECT status,claim_token,lease_until>now() AS valid FROM program_jobs WHERE id=%s",(row["id"],),one=True)
        if not state or state["claim_token"]!=row["claim_token"] or not state["valid"]:return
        if state["status"]=="CANCEL_REQUESTED" or (stopping and stopping.is_set()):
            finish(row,"CANCELLED")
            return
        if state["status"]!="RUNNING":return
        authorize(row)
        body=gateway.RunInput.model_validate(row["input_data"])
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(gateway.invoke,body,execution={"job_id":row["id"].hex,"expected_commit":row["expected_commit"],"expected_image":row["expected_image"]})
            cancelled=False
            while True:
                try:
                    result=future.result(timeout=1)
                    break
                except FutureTimeout:
                    state=db.query("UPDATE program_jobs SET lease_until=now()+interval '30 seconds' WHERE id=%s AND claim_token=%s AND lease_until>now() RETURNING status",(row["id"],row["claim_token"]),one=True)
                    if not state or state["status"]=="CANCEL_REQUESTED" or (stopping and stopping.is_set()):
                        cancelled=True
                    if not cancelled:
                        try: authorize(row)
                        except (ValueError,HTTPException,InterruptedError): cancelled=True
                    if cancelled:
                        try: gateway.request({"action":"cancel","job_id":row["id"].hex},timeout=3)
                        except HTTPException: pass
            if cancelled:
                finish(row,"CANCELLED")
                return
        if result["commit"]!=row["expected_commit"] or result["image"]!=row["expected_image"] or result["state"]!="succeeded":
            raise ValueError("Execution provenance mismatch.")
        authorize(row)
        finish(row,"SUCCEEDED",result=result)
    except InterruptedError:
        finish(row,"CANCELLED")
    except HTTPException as exc:
        finish(row,"FAILED",code="GATEWAY_"+str(exc.status_code),error="Gateway unavailable, busy, or request rejected. Review qualification and inputs before retry.")
    except Exception as exc:
        finish(row,"FAILED",code=type(exc).__name__,error="Program execution stopped. Review permissions, inputs and service health.")

def wait_manual(user,body):
    ident=enqueue(user,body,uuid.uuid4())
    deadline=time.monotonic()+205
    while time.monotonic()<deadline:
        with db.connect() as conn: row=owned(conn,user,ident)
        if row["status"]=="SUCCEEDED":
            result={**row["result"],"job_id":str(ident)}
            result["file"]={"name":row["file_name"],"data":base64.b64encode(bytes(row["file_data"])).decode()} if row["file_data"] else None
            return result
        if row["status"] in ("FAILED","CANCELLED"):raise HTTPException(422,"Program job "+str(ident)+" ended "+row["status"]+".")
        time.sleep(.5)
    raise HTTPException(504,"Program job "+str(ident)+" remains in the durable queue; inspect its history.")

def wait(user,body,parent):
    ident=enqueue(user,body,uuid.uuid4(),parent["project_id"],parent=parent)
    deadline=time.monotonic()+420
    while time.monotonic()<deadline:
        with db.connect() as conn:
            row=owned(conn,user,ident)
            table="chat_generations" if parent.get("chat_generation") else "runs"
            state=conn.execute("SELECT status FROM "+table+" WHERE id=%s",(parent["id"],)).fetchone()
            if not state or state["status"]!="RUNNING":
                cancel_row(conn,ident)
                stopped=True
            else: stopped=False
        if stopped: raise InterruptedError("Parent stopped.")
        if row["status"]=="SUCCEEDED":
            result={**row["result"],"job_id":str(ident)}
            result["file"]={"name":row["file_name"],"data":base64.b64encode(bytes(row["file_data"])).decode()} if row["file_data"] else None
            return result
        if row["status"] in ("CANCELLED","FAILED"): raise ValueError("Program job "+str(ident)+" ended "+row["status"]+".")
        time.sleep(.5)
    with db.connect() as conn: cancel_row(conn,ident)
    raise TimeoutError("Program queue wait expired.")
