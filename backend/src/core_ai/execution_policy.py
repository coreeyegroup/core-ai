"""Administrator-configurable inference budgets and one shared model tool loop."""
import json
import time
import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from psycopg.types.json import Jsonb
from . import auth,access,db,models

router=APIRouter(prefix="/api/v1/execution-policy")

class Policy(BaseModel):
    model_config=ConfigDict(extra="forbid")
    model_read_seconds:int=Field(default=120,ge=15,le=600)
    tool_read_seconds:int=Field(default=300,ge=15,le=600)
    chat_seconds:int=Field(default=600,ge=60,le=3600)
    task_seconds:int=Field(default=600,ge=60,le=3600)
    max_turns:int=Field(default=6,ge=1,le=24)
    max_calls:int=Field(default=8,ge=1,le=40)
    max_model_gib:float=Field(default=0,ge=0,le=1024,allow_inf_nan=False)

def get():
    row=db.query("SELECT value FROM settings WHERE key='execution_policy'",one=True)
    return Policy.model_validate(row["value"]) if row else Policy()

@router.get("")
def view(user=Depends(auth.session)):
    return get()

@router.put("")
def configure(body:Policy,user=Depends(auth.session)):
    access.admin(user)
    db.query("INSERT INTO settings(key,value) VALUES ('execution_policy',%s) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(Jsonb(body.model_dump()),))
    db.event("execution.policy.updated",user["id"],body.model_dump())
    return body

def admit_model(name,policy):
    if not models.supports_generation({'name':name}):
        raise ValueError('Choose a generation model, not an embedding-only model.')
    # Optional operator-provided size cap is not a measurement of free RAM/VRAM.
    if policy.max_model_gib:
        items=models.list_models()["models"]
        item=next((x for x in items if x["name"]==name),None)
        if not item or not isinstance(item.get("size"),int):
            raise ValueError("Model size unavailable for configured admission policy.")
        if item["size"]>policy.max_model_gib*1024**3:
            raise ValueError("Model exceeds configured size limit.")

def timeout(read):
    return httpx.Timeout(max(1,read),connect=8)

def bounded(value,limit=12000):
    text=json.dumps(value,default=str,ensure_ascii=False)
    return value if len(text)<=limit else {"preview":text[:limit-200],"truncated":True}

def loop(*,model,messages,allowed,schemas,check,dispatch,record_model,record_metrics,options,budget,policy):
    if "tools" not in models.inspect_model(model)["capabilities"]:
        raise ValueError("Selected model does not advertise tool support.")
    admit_model(model,policy)
    if not allowed: raise ValueError("Enable at least one permitted tool.")
    specs=[{"type":"function","function":{"name":schemas[t][0],"description":schemas[t][1],
            "parameters":schemas[t][2].model_json_schema()}} for t in allowed]
    mapping={schemas[t][0]:t for t in allowed}
    started=time.monotonic()
    calls=0
    def gate():
        check()
        remaining=budget-(time.monotonic()-started)
        if remaining<=0: raise TimeoutError("Agent execution budget exhausted.")
        return remaining
    for turn in range(1,policy.max_turns+1):
        remaining=gate()
        record_model(turn)
        with httpx.Client(timeout=timeout(min(policy.tool_read_seconds,remaining)),trust_env=False,follow_redirects=False) as client:
            response=client.post(models.config()["endpoint"]+"/api/chat",json={"model":model,"messages":messages,
                "tools":specs,"stream":False,"options":options})
            response.raise_for_status()
            data=response.json()
        if data.get("error"): raise ValueError("Model request failed.")
        gate()
        answer=data.get("message",{})
        tool_calls=answer.get("tool_calls") or []
        if not tool_calls:
            output=answer.get("content","").strip()
            if not output: raise ValueError("The agent returned no final answer.")
            record_metrics(models.metrics(data,started))
            return output[:100000]
        if not isinstance(tool_calls,list) or calls+len(tool_calls)>policy.max_calls:
            raise ValueError("Agent tool-call limit reached.")
        messages.append({"role":"assistant","content":answer.get("content",""),"tool_calls":tool_calls})
        for call in tool_calls:
            gate()
            calls+=1
            fn=call.get("function",{})
            name=mapping.get(fn.get("name"))
            if not name: raise ValueError("Model requested an unauthorized tool.")
            args=fn.get("arguments",{})
            if isinstance(args,str): args=json.loads(args)
            result=dispatch(name,args,calls)
            gate()
            messages.append({"role":"tool","tool_name":fn["name"],"content":json.dumps(bounded(result),default=str)})
        # Retain full tool exchanges; never truncate half a tool-call group.
        # Context limits are enforced by the provider. The loop is bounded by policy.
    raise ValueError("Agent model-step limit reached. Review recorded tool calls.")
