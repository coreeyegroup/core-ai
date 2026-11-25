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
