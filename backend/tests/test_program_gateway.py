from unittest.mock import patch
import pytest
from fastapi import HTTPException
from core_ai import program_gateway,agent_runtime

def test_agent_program_schema_and_registration():
    assert "program.list" in agent_runtime.SCHEMAS
    assert "program.run" in agent_runtime.SCHEMAS
    body=program_gateway.RunInput(recipe="position-sizing",values=[10000,.01,100,95,0,0])
    with patch.object(program_gateway,"request",return_value={"id":"test"}) as call:
        assert program_gateway.invoke(body)["id"]=="test"
        assert call.call_args.args[0]["action"]=="run"

def test_viewer_cannot_execute():
    with patch.object(program_gateway,"invoke") as invoke:
        with pytest.raises(HTTPException) as error:
            program_gateway.manual_run(program_gateway.RunInput(recipe="position-sizing"),{"id":"viewer","role":"VIEWER"})
        assert error.value.status_code==403
        invoke.assert_not_called()

def test_chat_programs_requires_explicit_permission(signed):
    import uuid
    from core_ai import db
    r=signed.post('/api/v1/chat/conversations',json={'model':'test:latest'})
    assert r.status_code==201
    ident=r.json()['id']
    body={'model':'test:latest','content':'calculate','request_id':str(uuid.uuid4()),'use_programs':True}
    assert signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=body).status_code==422
    agent=signed.post('/api/v1/agents',json={'name':'Program agent','instructions':'Use qualified programs only.',
        'runtime_mode':'tools','tools':['program.list','program.run']})
    assert agent.status_code==201,agent.text
    body['agent_id']=agent.json()['id']
    reply=signed.post('/api/v1/chat/conversations/'+ident+'/messages',json=body)
    assert reply.status_code==201,reply.text
    snapshot=db.query('SELECT program_tools FROM chat_generations WHERE id=%s',(reply.json()['id'],),one=True)
    assert snapshot['program_tools']==['program.list','program.run']
