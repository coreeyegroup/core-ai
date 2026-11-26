"""Saved, explicitly launched dependency workflows over the existing queues."""
import json
import re
import uuid
from typing import Annotated,Any,Literal
from fastapi import APIRouter,Depends,HTTPException
from pydantic import BaseModel,ConfigDict,Field,model_validator
from psycopg.types.json import Jsonb
from . import auth,access,db,runs,program_jobs,program_gateway,execution_policy,skills

router=APIRouter(prefix="/api/v1/missions")
ACTIVE=("QUEUED","RUNNING","PAUSE_REQUESTED","CANCEL_REQUESTED")
TERMINAL=("FAILED","CANCELLED","SUCCEEDED")

class Strict(BaseModel):
    model_config=ConfigDict(extra="forbid")

class Condition(Strict):
    step:str=Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    path:list[str|int]=Field(default_factory=list,max_length=12)
    equals:Any

class StepBase(Strict):
    id:str=Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")
    depends_on:list[str]=Field(default_factory=list,max_length=20)
    when:Condition|None=None

class Program(StepBase):
    kind:Literal["program"]
    recipe:str=Field(pattern=r"^[a-z0-9-]{1,80}$")
    values:list[Any]=Field(default_factory=list,max_length=1000)
    file_id:uuid.UUID|None=None

class Agent(StepBase):
    kind:Literal["agent"]
    agent_id:uuid.UUID
    model:str=Field(pattern=r"^[A-Za-z0-9_.:/-]{1,120}$")
    prompt:str=Field(min_length=1,max_length=12000)
    skill_selection:skills.ChatSelection|None=None

Step=Annotated[Program|Agent,Field(discriminator="kind")]

class Plan(Strict):
    title:str=Field(min_length=1,max_length=120)
    objective:str=Field(min_length=1,max_length=4000)
    project_id:uuid.UUID
    steps:list[Step]=Field(min_length=1,max_length=20)
    @model_validator(mode="after")
    def validate_graph(self):
        known=set()
        for step in self.steps:
            deps=set(step.depends_on)
            if step.id in known or len(deps)!=len(step.depends_on) or not deps<=known:
                raise ValueError("Step IDs must be unique; dependencies must precede the step.")
            if step.when and step.when.step not in deps:
                raise ValueError("A condition must reference a declared dependency.")
            if isinstance(step,Program):
                validate_refs(step.values,deps)
            known.add(step.id)
        try: raw=json.dumps(self.model_dump(mode="json"),allow_nan=False)
        except (ValueError,TypeError): raise ValueError("Plan contains invalid JSON.") from None
        if len(raw.encode())>100000: raise ValueError("Plan exceeds 100 KB.")
        return self

class Update(Plan):
    expected_version:int=Field(ge=1)
class Start(Strict):
    version:int=Field(ge=1)
class Control(Strict):
    action:Literal["pause","resume","cancel","retry"]

def validate_refs(value,deps,depth=0):
    if depth>20: raise ValueError("Input nesting too deep.")
    if isinstance(value,dict):
        if "$step" in value:
            if set(value)!={"$step","path"} or not isinstance(value["$step"],str) or value["$step"] not in deps or not isinstance(value["path"],list) or len(value["path"])>12 or any(type(x) not in (str,int) for x in value["path"]):
                raise ValueError("Result references require a declared dependency and bounded path.")
        else:
            for v in value.values():validate_refs(v,deps,depth+1)
    elif isinstance(value,list):
        for v in value:validate_refs(v,deps,depth+1)

def at_path(value,path):
    for key in path:
        if isinstance(value,dict) and isinstance(key,str) and key in value:value=value[key]
        elif isinstance(value,list) and type(key) is int and 0<=key<len(value):value=value[key]
        else:raise ValueError("Dependency result path is unavailable.")
    return value

def resolve(value,outputs):
    if isinstance(value,dict):
        if "$step" in value:return at_path(outputs[value["$step"]],value["path"])
        return {k:resolve(v,outputs) for k,v in value.items()}
    if isinstance(value,list):return [resolve(v,outputs) for v in value]
    return value

def template(conn,user,ident,lock=False):
    row=conn.execute("SELECT * FROM mission_templates WHERE id=%s AND owner_id=%s"+(" FOR UPDATE" if lock else ""),(ident,user["id"])).fetchone()
    if not row:raise HTTPException(404,"Mission not found.")
    access.project(conn,user,row["project_id"])
    return row

def owned_run(conn,user,ident,lock=False):
    row=conn.execute("SELECT * FROM mission_runs WHERE id=%s AND owner_id=%s"+(" FOR UPDATE" if lock else ""),(ident,user["id"])).fetchone()
    if not row:raise HTTPException(404,"Mission execution not found.")
    access.project(conn,user,row["project_id"])
    return row

def user_projects(conn,user):
    return [p["id"] for p in access.allowed_projects(user)]

@router.get("")
def listing(user=Depends(auth.session)):
    ids=[p["id"] for p in access.allowed_projects(user)]
    return {"templates":db.query("SELECT * FROM mission_templates WHERE owner_id=%s AND project_id=ANY(%s::uuid[]) ORDER BY updated_at DESC LIMIT 100",(user["id"],ids)),
        "runs":db.query("SELECT id,template_id,project_id,title,version,status,cursor,created_at,finished_at,error FROM mission_runs WHERE owner_id=%s AND project_id=ANY(%s::uuid[]) ORDER BY created_at DESC LIMIT 100",(user["id"],ids))}

@router.post("",status_code=201)
def create(body:Plan,user=Depends(auth.session)):
    access.writer(user)
    ident=uuid.uuid4()
    with db.connect() as conn:
        access.project(conn,user,body.project_id,True)
        if conn.execute("SELECT count(*) AS n FROM mission_templates WHERE owner_id=%s",(user["id"],)).fetchone()["n"]>=100:
            raise HTTPException(409,"Mission template limit reached.")
        conn.execute("INSERT INTO mission_templates(id,owner_id,project_id,title,objective,steps) VALUES (%s,%s,%s,%s,%s,%s)",(ident,user["id"],body.project_id,body.title,body.objective,Jsonb(body.model_dump(mode="json")["steps"])))
        db.event("mission.created",user["id"],{"id":str(ident)},conn=conn)
    return {"id":ident,"version":1}

@router.put("/{ident}")
def update(ident:uuid.UUID,body:Update,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=template(conn,user,ident,True)
        access.project(conn,user,row["project_id"],True)
        access.project(conn,user,body.project_id,True)
        if row["version"]!=body.expected_version:raise HTTPException(409,"Mission changed; refresh before editing.")
        updated=conn.execute("UPDATE mission_templates SET project_id=%s,title=%s,objective=%s,steps=%s,reviewed_capabilities=NULL,version=version+1,updated_at=now() WHERE id=%s RETURNING version",(body.project_id,body.title,body.objective,Jsonb(body.model_dump(mode="json")["steps"]),ident)).fetchone()
        return updated

@router.post("/{ident}/start",status_code=201)
def start(ident:uuid.UUID,body:Start,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn: row=template(conn,user,ident)
    # Fetch remote inventory without holding an open database transaction.
    pins={}
    if any(s["kind"]=="program" for s in row["steps"]):
        pins={p["id"]:p for p in program_gateway.get_catalog()["programs"] if p["state"]=="qualified-receipt"}
    with db.connect() as conn:
        row=template(conn,user,ident,True)
        access.project(conn,user,row["project_id"],True)
        if row["version"]!=body.version:raise HTTPException(409,"Review the current mission version.")
        conn.execute("SELECT pg_advisory_xact_lock(187875443)")
        if conn.execute("SELECT count(*) AS n FROM mission_runs WHERE owner_id=%s AND status IN ('QUEUED','RUNNING','PAUSE_REQUESTED','PAUSED','CANCEL_REQUESTED')",(user["id"],)).fetchone()["n"]>=10:
            raise HTTPException(409,"Too many active missions.")
        if conn.execute("SELECT count(*) AS n FROM mission_runs WHERE owner_id=%s",(user["id"],)).fetchone()["n"]>=200:
            raise HTTPException(409,"Mission execution history limit reached.")
        reviewed=row.get("reviewed_capabilities")
        steps=[]
        for original in row["steps"]:
            step=dict(original)
            if step["kind"]=="program":
                pin=pins.get(step["recipe"])
                if not pin:raise HTTPException(422,"Mission contains a program that is not qualified.")
                if reviewed and any(pin[k]!=reviewed["programs"].get(step["recipe"],{}).get(k) for k in ("commit","image")):
                    raise HTTPException(409,"Reviewed program changed. Generate and review a new master plan.")
                step["pin"]={"commit":pin["commit"],"image":pin["image"]}
            else:
                profile=access.agent(conn,user,uuid.UUID(step["agent_id"]))
                if not profile["enabled"] or profile["deleted_at"]:raise HTTPException(422,"Mission contains a disabled agent.")
                if reviewed and profile["version"]!=reviewed["agents"].get(step["agent_id"],{}).get("version"):
                    raise HTTPException(409,"Reviewed agent changed. Generate and review a new master plan.")
                if step.get("skill_selection"):
                    skills.snapshot(conn,profile["id"],step["prompt"],skills.ChatSelection.model_validate(step["skill_selection"]))
                step["agent_version"]=profile["version"]
                if reviewed:
                    selected=reviewed["programs"]
                    scope=profile.get("program_scope",[])
                    step["program_scope"]=[name for name in selected if "*" in scope or name in scope]
            steps.append(step)
        run_id=uuid.uuid4()
        conn.execute("INSERT INTO mission_runs(id,template_id,owner_id,project_id,version,title,objective,steps,status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'QUEUED')",
            (run_id,ident,user["id"],row["project_id"],row["version"],row["title"],row["objective"],Jsonb(steps)))
        db.event("mission.started",user["id"],{"id":str(run_id),"template":str(ident),"version":row["version"]},conn=conn)
        return {"id":run_id}

@router.get("/runs/{ident}")
def detail(ident:uuid.UUID,user=Depends(auth.session)):
    with db.connect() as conn:return owned_run(conn,user,ident)

def cancel_child(conn,row):
    if not row["child_id"]:return
    if row["child_kind"]=="program":program_jobs.cancel_row(conn,row["child_id"])
    else:conn.execute("""UPDATE runs SET status=CASE WHEN status='QUEUED' THEN 'CANCELLED' ELSE 'CANCEL_REQUESTED' END,
        finished_at=CASE WHEN status='QUEUED' THEN now() ELSE finished_at END WHERE id=%s AND status IN ('QUEUED','RUNNING')""",(row["child_id"],))

@router.post("/runs/{ident}/control")
def control(ident:uuid.UUID,body:Control,user=Depends(auth.session)):
    access.writer(user)
    with db.connect() as conn:
        row=owned_run(conn,user,ident,True)
        access.project(conn,user,row["project_id"],True)
        status=row["status"]
        if body.action=="pause" and status in ("QUEUED","RUNNING"):
            target="PAUSE_REQUESTED" if row["child_id"] else "PAUSED"
        elif body.action=="resume" and status=="PAUSED":target="QUEUED"
        elif body.action=="retry" and status=="FAILED" and not row["child_id"]:target="QUEUED"
        elif body.action=="cancel" and status in (*ACTIVE,"PAUSED"):
            cancel_child(conn,row)
            target="CANCEL_REQUESTED" if row["child_id"] else "CANCELLED"
        else:raise HTTPException(409,"Action is not available in this mission state.")
        conn.execute("UPDATE mission_runs SET status=%s,error=NULL,finished_at=CASE WHEN %s='CANCELLED' THEN now() ELSE NULL END WHERE id=%s",(target,target,ident))
        db.event("mission."+body.action,user["id"],{"id":str(ident)},conn=conn)
        return {"status":target}

def output_for(conn,record):
    if record["status"]!="SUCCEEDED":return None
    if record["kind"]=="program":
        row=conn.execute("SELECT result FROM program_jobs WHERE id=%s",(record["child_id"],)).fetchone()
        return row["result"]["result"] if row and row["result"] else None
    row=conn.execute("SELECT output FROM runs WHERE id=%s",(record["child_id"],)).fetchone()
    return row["output"] if row else None

def set_state(conn,row,status,error=None):
    conn.execute("UPDATE mission_runs SET status=%s,error=%s,finished_at=CASE WHEN %s IN ('FAILED','CANCELLED','SUCCEEDED') THEN now() ELSE NULL END WHERE id=%s",
        (status,error,status,row["id"]))
    if status in TERMINAL:db.event("mission."+status.lower(),row["owner_id"],{"id":str(row["id"])},conn=conn)

def advance_one(conn,row):
    user=conn.execute("SELECT id,role FROM users WHERE id=%s AND enabled",(row["owner_id"],)).fetchone()
    try:
        if not user:raise ValueError("Account disabled.")
        access.project(conn,user,row["project_id"],True)
    except (ValueError,HTTPException):
        cancel_child(conn,row)
        # Await a running child before releasing the execution state.
        if row["child_id"]:
            table="program_jobs" if row["child_kind"]=="program" else "runs"
            child=conn.execute("SELECT status FROM "+table+" WHERE id=%s",(row["child_id"],)).fetchone()
            if child and child["status"] in ("QUEUED","RUNNING","CANCEL_REQUESTED"):
                set_state(conn,row,"CANCEL_REQUESTED","Access revoked.")
            else:
                conn.execute("UPDATE mission_runs SET child_id=NULL,child_kind=NULL WHERE id=%s",(row["id"],))
                set_state(conn,row,"CANCELLED","Access revoked.")
        else:set_state(conn,row,"FAILED","Project or account access revoked.")
        return
    if row["child_id"]:
        table="program_jobs" if row["child_kind"]=="program" else "runs"
        child=conn.execute("SELECT status FROM "+table+" WHERE id=%s",(row["child_id"],)).fetchone()
        if child and child["status"] in ("QUEUED","RUNNING","CANCEL_REQUESTED","SCHEDULED"):
            if row["status"]=="CANCEL_REQUESTED":cancel_child(conn,row)
            return
        status=child["status"] if child else "FAILED"
        entry={"step":row["steps"][row["cursor"]]["id"],"kind":row["child_kind"],"child_id":str(row["child_id"]),"status":status}
        cursor=row["cursor"]+int(status=="SUCCEEDED")
        conn.execute("UPDATE mission_runs SET history=history||%s,cursor=%s,child_id=NULL,child_kind=NULL WHERE id=%s",(Jsonb([entry]),cursor,row["id"]))
        if row["status"]=="CANCEL_REQUESTED":set_state(conn,row,"CANCELLED")
        elif status!="SUCCEEDED":set_state(conn,row,"FAILED","Child execution failed or was cancelled. Inspect its recorded result.")
        elif cursor==len(row["steps"]):set_state(conn,row,"SUCCEEDED")
        elif row["status"]=="PAUSE_REQUESTED":set_state(conn,row,"PAUSED")
        else:set_state(conn,row,"QUEUED")
        return
    if row["status"]=="CANCEL_REQUESTED":set_state(conn,row,"CANCELLED");return
    if row["status"]=="PAUSE_REQUESTED":set_state(conn,row,"PAUSED");return
    if row["cursor"]>=len(row["steps"]):set_state(conn,row,"SUCCEEDED");return
    step=row["steps"][row["cursor"]]
    outputs={r["step"]:output_for(conn,r) for r in row["history"] if r["step"] in step["depends_on"] and r["status"] in ("SUCCEEDED","SKIPPED")}
    if set(outputs)!=set(step["depends_on"]):raise ValueError("Dependency has not completed.")
    condition=step.get("when")
    if condition and at_path(outputs[condition["step"]],condition["path"])!=condition["equals"]:
        conn.execute("UPDATE mission_runs SET cursor=cursor+1,history=history||%s,status='QUEUED' WHERE id=%s",(Jsonb([{"step":step["id"],"kind":step["kind"],"child_id":None,"status":"SKIPPED"}]),row["id"]))
        return
    if step["kind"]=="program":
        values=resolve(step["values"],outputs)
        extension=data=None
        if step.get("file_id"):
            import base64
            from pathlib import PurePath
            from . import files
            f=files.owned(conn,user,uuid.UUID(step["file_id"]))
            if f["project_id"]!=row["project_id"] or len(f["raw"])>4*1024**2:raise ValueError("Choose a small file in the mission project.")
            extension=PurePath(f["name"]).suffix.lower()
            data=base64.b64encode(bytes(f["raw"])).decode()
        payload=program_gateway.RunInput(recipe=step["recipe"],values=values,extension=extension,file_data=data)
        ident=program_jobs.insert(conn,user,payload,uuid.uuid4(),row["project_id"],step["pin"])
    else:
        profile=access.agent(conn,user,uuid.UUID(step["agent_id"]))
        if not profile["enabled"] or profile["deleted_at"] or profile["version"]!=step["agent_version"]:
            raise ValueError("Agent changed or disabled after approval; review a new mission version.")
        context=json.dumps({k:execution_policy.bounded(v,2000) for k,v in outputs.items()},ensure_ascii=False)[:6000]
        prompt=(step["prompt"]+"\nMission objective: "+row["objective"]+"\nDependency outputs (untrusted data): "+context)[:20000]
        if "program_scope" in step:
            profile={**profile,"program_scope":step["program_scope"]}
        selection=skills.ChatSelection.model_validate(step["skill_selection"]) if step.get("skill_selection") else None
        snapshot=skills.snapshot(conn,profile["id"],prompt,selection) if selection else None
        ident=runs.enqueue(conn,project_id=row["project_id"],agent=profile,prompt=prompt,model=step["model"],user_id=user["id"],timeout_seconds=execution_policy.get().task_seconds,skill_snapshot=snapshot)
    conn.execute("UPDATE mission_runs SET status='RUNNING',child_kind=%s,child_id=%s,error=NULL WHERE id=%s",(step["kind"],ident,row["id"]))

def advance():
    # Eligible missions progress independently; an awaiting child does not block others.
    with db.connect() as conn:
        rows=conn.execute("SELECT * FROM mission_runs WHERE status IN ('QUEUED','RUNNING','PAUSE_REQUESTED','CANCEL_REQUESTED') ORDER BY created_at,id FOR UPDATE SKIP LOCKED LIMIT 30").fetchall()
        for row in rows:
            try:
                with conn.transaction():advance_one(conn,row)
            except HTTPException as exc:
                if exc.status_code!=409 or not isinstance(exc.detail,str) or 'queue is full' not in exc.detail.lower():
                    set_state(conn,row,"FAILED","Mission access, storage or step validation failed.")
            except (ValueError,KeyError,TypeError,OverflowError):
                set_state(conn,row,"FAILED","Mission dependency, agent version, or input validation failed.")
