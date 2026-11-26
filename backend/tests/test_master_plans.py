import json
from unittest.mock import patch
from core_ai import db,worker,program_gateway

def catalog():
    return {"programs":[{"id":"position-sizing","state":"qualified-receipt","commit":"a"*40,"image":"sha256:"+"b"*64,"fields":["equity"],"example":[10000],"extensions":[],"mode":"offline"}],"repositories":[]}

def submit(signed,work):
    body={"project_id":work["project_id"],"planner_agent_id":work["agent_id"],"model":work["model"],
          "objective":"Review position sizing", "agent_ids":[work["agent_id"]],"program_ids":["position-sizing"]}
    response=signed.post("/api/v1/master-plans",json=body)
    assert response.status_code==201,response.text
    return response.json()

def draft(work):
    return {"title":"Sizing review","steps":[{"id":"size","kind":"program","recipe":"position-sizing","values":[10000]},
        {"id":"review","kind":"agent","agent_id":work["agent_id"],"model":work["model"],"prompt":"Review the computed result","depends_on":["size"]}]}

def test_reviewed_master_plan_creates_mission_without_launch(signed,work):
    with patch.object(program_gateway,"get_catalog",return_value=catalog()):
        r=submit(signed,work)
        row=worker.claim()
        assert row["runtime_mode"]=="analysis" and not row["tools"]
        assert "position-sizing" in row["prompt"]
        worker.finish(row["id"],"SUCCEEDED",output=json.dumps(draft(work)))
        detail=signed.get("/api/v1/master-plans/"+r["id"]).json()
        assert detail["state"]=="REVIEW_REQUIRED"
        assert signed.post("/api/v1/master-plans/"+r["id"]+"/approve",json={"digest":"a"*64}).status_code==409
        approval=signed.post("/api/v1/master-plans/"+r["id"]+"/approve",json={"digest":detail["digest"]})
        assert approval.status_code==201,approval.text
        template=approval.json()["mission_id"]
        assert signed.post("/api/v1/master-plans/"+r["id"]+"/approve",json={"digest":detail["digest"]}).json()["mission_id"]==template
        assert db.query("SELECT count(*) AS n FROM mission_runs",one=True)["n"]==0
        assert db.query("SELECT steps FROM mission_templates WHERE id=%s",(template,),one=True)["steps"][0]["recipe"]=="position-sizing"

def test_master_rejects_unapproved_capability_and_changed_agent(signed,work):
    with patch.object(program_gateway,"get_catalog",return_value=catalog()):
        r=submit(signed,work)
        row=worker.claim()
        bad=draft(work);bad["steps"][0]["recipe"]="black-scholes"
        worker.finish(row["id"],"SUCCEEDED",output=json.dumps(bad))
        detail=signed.get("/api/v1/master-plans/"+r["id"]).json()
        assert detail["state"]=="INVALID_PLAN"
        assert signed.post("/api/v1/master-plans/"+r["id"]+"/approve",json={"digest":"a"*64}).status_code==409
        r=submit(signed,work)
        row=worker.claim();worker.finish(row["id"],"SUCCEEDED",output=json.dumps(draft(work)))
        detail=signed.get("/api/v1/master-plans/"+r["id"]).json()
        db.query("UPDATE agents SET version=version+1 WHERE id=%s",(work["agent_id"],))
        assert signed.post("/api/v1/master-plans/"+r["id"]+"/approve",json={"digest":detail["digest"]}).status_code==409
