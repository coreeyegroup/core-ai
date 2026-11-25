"""Current permission intersection, shared by chat, tasks, and program jobs."""
import re
from fastapi import HTTPException
from . import access, db

def validate_scope(scope):
    if scope is None: return None
    if len(scope)>200 or len(set(scope))!=len(scope):
        raise HTTPException(422,"Select distinct program IDs.")
    if "*" in scope and scope!=["*"]:
        raise HTTPException(422,"All-program access must be selected by itself.")
    if any(s!="*" and not re.fullmatch(r"[a-z0-9-]{1,80}",s) for s in scope):
        raise HTTPException(422,"Invalid program ID.")
    return scope

def current_actor(run,write=False):
    with db.connect() as conn:
        user=conn.execute("SELECT id,role FROM users WHERE id=%s AND enabled",(run["requested_by"],)).fetchone()
        if not user: raise ValueError("The requesting account is inactive.")
        access.writer(user)
        if run.get("project_id") is not None: access.project(conn,user,run["project_id"],write)
        return user

def current_profile(run,user):
    if not run.get("agent_id"): raise ValueError("An agent profile is required.")
    with db.connect() as conn:
        profile=access.agent(conn,user,run["agent_id"])
        if profile.get("deleted_at") or not profile["enabled"] or profile["runtime_mode"]!="tools":
            raise ValueError("Agent tool permission was revoked.")
        return profile

def permitted_tools(run,user):
    profile=current_profile(run,user)
    snapshot=run.get("program_tools",[]) if run.get("chat_generation") else run.get("tools",[])
    return [t for t in snapshot if t in profile["tools"]]

def require_tool(run,user,name):
    if name not in permitted_tools(run,user):
        raise ValueError("This tool is not authorized for the agent.")

def scope_allows(scope,recipe):
    return "*" in scope or recipe in scope

def program_allowed(run,user,recipe):
    profile=current_profile(run,user)
    snapshot=run.get("program_tools",[]) if run.get("chat_generation") else run.get("tools",[])
    return ("program.run" in snapshot and "program.run" in profile["tools"]
            and scope_allows(run.get("program_scope",[]),recipe)
            and scope_allows(profile.get("program_scope",[]),recipe))
