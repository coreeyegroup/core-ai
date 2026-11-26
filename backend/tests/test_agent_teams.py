import time
import uuid
from core_ai import db,skills,missions,worker
from test_skills import bundle

def test_team_create_assign_launch_and_snapshot(signed,work,monkeypatch):
    entries,_=skills.discover(bundle(),time.monotonic()+5)
    sha="a"*40
    monkeypatch.setattr(skills,"fetch_collection",lambda *args:(sha,entries[:2],[],[],[]))
    ident=signed.post("/api/v1/skills/import",json={"repository":"example/skills"}).json()["id"]
    assert signed.put("/api/v1/skills/collections/"+ident+"/activate",json={"commit":sha}).status_code==200
    choice={"collection_id":ident,"commit":sha,"path":entries[0]["path"]}
    body={"request_id":str(uuid.uuid4()),"title":"Team test","objective":"Review facts","project_id":work["project_id"],
          "agents":[{"id":"research","name":"New researcher","instructions":"Use facts.","model":work["model"],"prompt":"Review case 000","collections":[{"id":ident,"commit":sha}],"skill_selection":{"mode":"manual","selected":[choice]}},
                    {"id":"review","name":"New reviewer","instructions":"Review evidence.","model":work["model"],"prompt":"Check research","depends_on":["research"],"skill_selection":{"mode":"off"}}]}
    r=signed.post("/api/v1/agent-teams",json=body)
    assert r.status_code==201,r.text
    result=r.json()
    assert signed.post("/api/v1/agent-teams",json=body).json()==result
    assert db.query("SELECT count(*) AS n FROM runs",one=True)["n"]==0
    assert signed.get("/api/v1/skills/agents/"+result["agents"][0]["id"]).status_code==200
    run=signed.post("/api/v1/missions/"+result["mission_id"]+"/start",json={"version":1})
    assert run.status_code==201,run.text
    missions.advance()
    child=worker.claim()
    assert child["skill_versions"][0]["commit"]==sha
    assert child["skill_versions"][0]["path"]==choice["path"]
    worker.finish(child["id"],"SUCCEEDED",output="Reviewed facts")
    missions.advance();missions.advance()
    review=worker.claim()
    assert review["skill_versions"]==[]
    assert "Reviewed facts" in review["prompt"]
    worker.finish(review["id"],"SUCCEEDED",output="Accepted")
    missions.advance()
    assert signed.get("/api/v1/missions/runs/"+run.json()["id"]).json()["status"]=="SUCCEEDED"

def test_team_invalid_collection_rolls_back(signed,work):
    before=db.query("SELECT count(*) AS n FROM agents",one=True)["n"]
    body={"request_id":str(uuid.uuid4()),"title":"Bad","objective":"Review","project_id":work["project_id"],"agents":[
        {"id":"first","name":"First","instructions":"Review","model":work["model"],"prompt":"Review"},
        {"id":"second","name":"Second","instructions":"Review","model":work["model"],"prompt":"Review","collections":[{"id":str(uuid.uuid4()),"commit":"a"*40}]}]}
    assert signed.post("/api/v1/agent-teams",json=body).status_code==409
    assert db.query("SELECT count(*) AS n FROM agents",one=True)["n"]==before
