"""Create a complete agent team, assignments and mission atomically."""
import hashlib
import json
import uuid
from fastapi import APIRouter,Depends,HTTPException
from pydantic import Field,model_validator
from psycopg.types.json import Jsonb
from . import access,auth,db,missions,skills,models,agent_runtime,capability_policy,program_gateway

router=APIRouter(prefix="/api/v1/agent-teams")

class Collection(missions.Strict):
    id:uuid.UUID
    commit:str=Field(pattern=r"^[0-9a-f]{40}$")

class Member(missions.StepBase):
    name:str=Field(min_length=1,max_length=120)
    instructions:str=Field(min_length=1,max_length=16000)
    model:str=Field(pattern=r"^[A-Za-z0-9_.:/-]{1,120}$")
    prompt:str=Field(min_length=1,max_length=12000)
    collections:list[Collection]=Field(default_factory=list,max_length=24)
    skill_selection:skills.ChatSelection=Field(default_factory=skills.ChatSelection)
    tools:list[str]=Field(default_factory=list,max_length=5)
    program_scope:list[str]=Field(default_factory=list,max_length=40)

class Team(missions.Strict):
    request_id:uuid.UUID
    project_id:uuid.UUID
    title:str=Field(min_length=1,max_length=120)
    objective:str=Field(min_length=1,max_length=4000)
    agents:list[Member]=Field(min_length=1,max_length=8)
    @model_validator(mode="after")
    def validate_members(self):
        known=set()
        names=set()
        for member in self.agents:
            if not member.name.strip() or not member.instructions.strip() or not member.prompt.strip():
                raise ValueError("Agent name, instructions and task prompt are required.")
            if member.id in known or not set(member.depends_on)<=known or len(set(member.depends_on))!=len(member.depends_on):
                raise ValueError("Unique step IDs and earlier dependencies are required.")
            if member.name.strip().casefold() in names:raise ValueError("Choose distinct team agent names.")
            if member.when and member.when.step not in member.depends_on:raise ValueError("Condition must reference a dependency.")
            if len({c.id for c in member.collections})!=len(member.collections):raise ValueError("Choose each collection once.")
            if len(set(member.tools))!=len(member.tools) or any(t not in agent_runtime.SCHEMAS for t in member.tools):raise ValueError("Unknown or duplicated tool.")
            if "*" in member.program_scope or (member.program_scope and "program.run" not in member.tools):raise ValueError("Choose explicit programs and enable program.run.")
            if member.skill_selection.mode=="manual" and not member.skill_selection.selected:raise ValueError("Choose manual skills or Auto/Off.")
            if member.skill_selection.mode!="manual" and member.skill_selection.selected:raise ValueError("Only manual mode accepts selected skills.")
            if not models.supports_generation({"name":member.model}):raise ValueError("Choose generation models.")
            known.add(member.id);names.add(member.name.strip().casefold())
        if len(json.dumps(self.model_dump(mode="json"),allow_nan=False).encode())>100000:raise ValueError("Team exceeds 100 KB.")
        return self

def fingerprint(body):
    return hashlib.sha256(json.dumps(body.model_dump(mode="json"),sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()

def existing(conn,user,body,digest):
    row=conn.execute("SELECT owner_id,project_id,reviewed_capabilities FROM mission_templates WHERE id=%s",(body.request_id,)).fetchone()
    if not row:return None
    cap=row["reviewed_capabilities"] or {}
    if row["owner_id"]!=user["id"] or row["project_id"]!=body.project_id or cap.get("team_digest")!=digest:
        raise HTTPException(409,"Request ID already used. Review and use a new ID.")
    return {"mission_id":body.request_id,"agents":cap["team_agents"],"version":1}

@router.post("",status_code=201)
def create(body:Team,user=Depends(auth.session)):
    access.writer(user)
    digest=fingerprint(body)
    with db.connect() as conn:
        access.project(conn,user,body.project_id,True)
        prior=existing(conn,user,body,digest)
        if prior:return prior
    requested=set()
    for member in body.agents:
        requested.update(capability_policy.validate_scope(member.program_scope))
    pins={}
    if requested:
        pins={p["id"]:{"commit":p["commit"],"image":p["image"]} for p in program_gateway.get_catalog()["programs"] if p["id"] in requested and p["state"]=="qualified-receipt"}
        if set(pins)!=requested:raise HTTPException(422,"Choose only currently qualified programs.")
    with db.connect() as conn:
        access.project(conn,user,body.project_id,True)
        conn.execute("SELECT pg_advisory_xact_lock(187875445)")
        prior=existing(conn,user,body,digest)
        if prior:return prior
        if conn.execute("SELECT count(*) AS n FROM mission_templates WHERE owner_id=%s",(user["id"],)).fetchone()["n"]>=100:raise HTTPException(409,"Mission template limit reached.")
        if conn.execute("SELECT count(*) AS n FROM agents WHERE owner_id=%s AND deleted_at IS NULL",(user["id"],)).fetchone()["n"]+len(body.agents)>200:raise HTTPException(409,"Agent limit reached.")
        created=[];steps=[];versions={}
        for member in body.agents:
            for collection in member.collections:
                row=conn.execute("SELECT active_commit FROM skill_collections WHERE id=%s AND deleted_at IS NULL FOR SHARE",(collection.id,)).fetchone()
                if not row or row["active_commit"]!=collection.commit:raise HTTPException(409,"A selected collection changed or is unavailable. Refresh and review.")
            ident=uuid.uuid4()
            conn.execute("INSERT INTO agents(id,name,instructions,enabled,owner_id,runtime_mode,tools,program_scope) VALUES (%s,%s,%s,true,%s,%s,%s,%s)",
                (ident,member.name.strip(),member.instructions,user["id"],"tools" if member.tools else "analysis",Jsonb(member.tools),Jsonb(member.program_scope)))
            for collection in member.collections:
                conn.execute("INSERT INTO agent_skill_collections(agent_id,collection_id) VALUES (%s,%s)",(ident,collection.id))
            # Check the requested effective skill selection before saving any records.
            skills.snapshot(conn,ident,member.prompt,member.skill_selection)
            created.append({"id":str(ident),"name":member.name.strip(),"step":member.id})
            versions[str(ident)]={"version":1}
            steps.append({"id":member.id,"kind":"agent","agent_id":str(ident),"model":member.model,
                "prompt":member.prompt,"depends_on":member.depends_on,"when":member.when.model_dump(mode="json") if member.when else None,
                "skill_selection":member.skill_selection.model_dump(mode="json")})
            db.event("agent.created",user["id"],{"id":str(ident),"team":str(body.request_id)},conn=conn)
            db.event("skills.assigned",user["id"],{"agent":str(ident),"collections":[str(c.id) for c in member.collections]},conn=conn)
        plan=missions.Plan.model_validate({"title":body.title,"objective":body.objective,"project_id":body.project_id,"steps":steps})
        caps={"agents":versions,"programs":pins,"team_digest":digest,"team_agents":created}
        conn.execute("INSERT INTO mission_templates(id,owner_id,project_id,title,objective,steps,reviewed_capabilities) VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (body.request_id,user["id"],body.project_id,body.title,body.objective,Jsonb(plan.model_dump(mode="json")["steps"]),Jsonb(caps)))
        db.event("agent_team.created",user["id"],{"mission":str(body.request_id),"agents":len(created)},conn=conn)
        return {"mission_id":body.request_id,"agents":created,"version":1}
