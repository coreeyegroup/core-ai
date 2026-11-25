import json
import uuid
from unittest.mock import patch
import pytest
from core_ai import db, worker, program_gateway

def example():
    return {"recipe":"position-sizing","values":[10000,.01,100,95,0,0],
            "extension":None,"file_data":None}

def catalog():
    return {"schema":1,"programs":[{"id":"position-sizing","state":"qualified-receipt",
            "commit":"a"*40,"image":"sha256:"+"b"*64,"fields":["account"],"example":[10000],
            "extensions":[],"mode":"offline"}],"repositories":[]}

def result():
    return {"id":"fixture-execution","recipe":"position-sizing","state":"succeeded",
            "commit":"a"*40,"image":"sha256:"+"b"*64,"provenance":"offline-program",
            "result":{"units":20},"file":None}

def test_program_job_persists_and_retries(signed):
    from core_ai import program_jobs
    with patch.object(program_gateway,"get_catalog",return_value=catalog()),patch.object(program_gateway,"invoke",return_value=result()):
        payload={**example(),"request_id":str(uuid.uuid4())}
        first=signed.post("/api/v1/programs/jobs",json=payload)
        assert first.status_code==201,first.text
        ident=first.json()["id"]
        assert signed.post("/api/v1/programs/jobs",json=payload).json()["id"]==ident
        assert signed.post("/api/v1/programs/jobs",json={**payload,"values":[1]}).status_code==409
        row=program_jobs.claim()
        assert str(row["id"])==ident
        program_jobs.process(row)
        detail=signed.get("/api/v1/programs/jobs/"+ident).json()
        assert detail["status"]=="SUCCEEDED" and detail["result"]["result"]["units"]==20
        assert "input_data" not in detail
        assert signed.post("/api/v1/programs/jobs/"+ident+"/retry",json={}).status_code==409

def test_program_cancel_and_expired_lease(signed):
    from core_ai import program_jobs
    with patch.object(program_gateway,"get_catalog",return_value=catalog()):
        ident=signed.post("/api/v1/programs/jobs",json={**example(),"request_id":str(uuid.uuid4())}).json()["id"]
        assert signed.post("/api/v1/programs/jobs/"+ident+"/cancel",json={}).json()["status"]=="CANCELLED"
        assert program_jobs.claim() is None
        ident=signed.post("/api/v1/programs/jobs",json={**example(),"request_id":str(uuid.uuid4())}).json()["id"]
        row=program_jobs.claim()
        db.query("UPDATE program_jobs SET lease_until=now()-interval '1 minute' WHERE id=%s",(row["id"],))
        assert program_jobs.claim() is None
        assert signed.get("/api/v1/programs/jobs/"+ident).json()["status"]=="FAILED"
        retry=signed.post("/api/v1/programs/jobs/"+ident+"/retry",json={})
        assert retry.status_code==201,retry.text
        assert retry.json()["id"]!=ident

def test_agent_scope_revalidation(signed,work):
    from core_ai import capability_policy
    agent=work["agent_id"]
    payload={"name":"Scoped agent","instructions":"Use sizing only.","runtime_mode":"tools",
             "tools":["program.list","program.run"],"program_scope":["position-sizing"]}
    assert signed.put("/api/v1/agents/"+agent,json=payload).status_code==200
    ident=signed.post("/api/v1/runs",json=work).json()["id"]
    run=worker.claim()
    user=capability_policy.current_actor(run)
    assert capability_policy.program_allowed(run,user,"position-sizing")
    assert not capability_policy.program_allowed(run,user,"black-scholes")
    assert signed.put("/api/v1/agents/"+agent,json={**payload,"program_scope":[]}).status_code==200
    assert not capability_policy.program_allowed(run,user,"position-sizing")
    assert signed.get("/api/v1/runs/"+ident).json()["program_scope"]==["position-sizing"]

def test_mission_checkpoint_and_resume(signed,work):
    from core_ai import missions,program_jobs
    with patch.object(program_gateway,"get_catalog",return_value=catalog()),patch.object(program_gateway,"invoke",return_value=result()):
        plan={"title":"Review","objective":"Calculate and review","project_id":work["project_id"],
              "steps":[{"id":"size","kind":"program","recipe":"position-sizing","values":[10000,.01,100,95,0,0]},
                       {"id":"review","kind":"agent","agent_id":work["agent_id"],"model":work["model"],"prompt":"Review sizing","depends_on":["size"]}]}
        saved=signed.post("/api/v1/missions",json=plan)
        assert saved.status_code==201,saved.text
        launched=signed.post("/api/v1/missions/"+saved.json()["id"]+"/start",json={"version":1})
        assert launched.status_code==201,launched.text
        ident=launched.json()["id"]
        missions.advance()
        child=program_jobs.claim()
        program_jobs.process(child)
        missions.advance()
        missions.advance()
        run=worker.claim()
        assert "units" in run["prompt"]
        worker.finish(run["id"],"SUCCEEDED",output="Reviewed")
        missions.advance()
        detail=signed.get("/api/v1/missions/runs/"+ident).json()
        assert detail["status"]=="SUCCEEDED" and len(detail["history"])==2

def test_mission_rejects_forward_dependency(signed,work):
    payload={"title":"Invalid","objective":"Test","project_id":work["project_id"],
             "steps":[{"id":"a","kind":"program","recipe":"position-sizing","values":[],"depends_on":["b"]},
                      {"id":"b","kind":"program","recipe":"position-sizing","values":[]}]}
    assert signed.post("/api/v1/missions",json=payload).status_code==422
