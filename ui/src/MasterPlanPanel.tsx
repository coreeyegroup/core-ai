import {useEffect,useState} from 'react';
import {api} from './api';
import {useSession} from './Session';
import {modelLabel,type Model,type Program} from './CapabilityFields';

type Project={id:string;name:string};
type Agent={id:string;name:string;version:number;enabled:boolean};
type Row={id:string;objective:string;run_status?:string;state?:string;planner_run?:string;mission_id?:string;digest?:string;plan?:{title:string;steps:{id:string;kind:string;depends_on?:string[];recipe?:string;agent_id?:string;model?:string;prompt?:string;values?:unknown[]}[]};capabilities?:unknown;error?:string};

export default function MasterPlanPanel({projects,agents,models,programs,visible,onApproved}:{projects:Project[];agents:Agent[];models:Model[];programs:Program[];visible:boolean;onApproved:()=>Promise<void>}){
 const readonly=useSession().role==='VIEWER';
 const [project,setProject]=useState(''),[planner,setPlanner]=useState(''),[model,setModel]=useState(''),[objective,setObjective]=useState('');
 const [agentIds,setAgentIds]=useState<string[]>([]),[programIds,setProgramIds]=useState<string[]>([]);
 const [rows,setRows]=useState<Row[]>([]),[id,setId]=useState(''),[detail,setDetail]=useState<Row|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[open,setOpen]=useState(false);
 async function list(){const r=await api('master-plans');if(Array.isArray(r))setRows(r);}
 useEffect(()=>{if(open&&visible)void list().catch(e=>setError(e.message));},[open,visible]);
 useEffect(()=>{if(!open||!visible||!id)return;let live=true;const read=()=>api('master-plans/'+id).then(r=>{if(live&&r?.id===id)setDetail(r);}).catch(e=>{if(live)setError(e.message);});void read();const timer=setInterval(read,2500);return()=>{live=false;clearInterval(timer);};},[id,open,visible]);
 function toggle(ids:string[],value:string,checked:boolean){return checked?[...ids,value]:ids.filter(x=>x!==value);}
 async function submit(){setBusy(true);setError('');try{const r=await api('master-plans','POST',{project_id:project,planner_agent_id:planner,model,objective,agent_ids:agentIds,program_ids:programIds},50000);setDetail(null);setId(r.id);await list();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function cancel(){if(!detail?.planner_run)return;setBusy(true);setError("");try{await api("runs/"+detail.planner_run+"/cancel","POST",{});setDetail(await api("master-plans/"+id));await list();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function approve(){if(!detail?.digest||!window.confirm('Save this exact reviewed plan as a mission? This does not launch it.'))return;setBusy(true);setError('');try{await api('master-plans/'+id+'/approve','POST',{digest:detail.digest},50000);setDetail(await api('master-plans/'+id));await list();await onApproved();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <details className="box" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>Master planner · objective to reviewed mission</summary>
  <p>Generate a dependency plan using only selected capabilities. The planning job has no execution tools. Review its proposed agents, parameters and dependencies before saving a mission.</p>
  {error&&<div role="alert" className="error">{error}</div>}
  <fieldset className="form" disabled={readonly||busy}>
   <div className="fields"><label>Project<select value={project} onChange={e=>setProject(e.target.value)}><option value="">Select project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>Planner profile<select value={planner} onChange={e=>setPlanner(e.target.value)}><option value="">Select agent</option>{agents.map(a=><option key={a.id} value={a.id}>{a.name} · v{a.version}</option>)}</select></label><label>Model<select value={model} onChange={e=>setModel(e.target.value)}><option value="">Select generation model</option>{models.map(m=><option key={m.name} value={m.name}>{modelLabel(m)}</option>)}</select></label></div>
   <label>Objective and acceptance criteria<textarea rows={4} maxLength={4000} value={objective} onChange={e=>setObjective(e.target.value)} placeholder="Include the actual input data, constraints and required deliverable."/></label>
   <details><summary>Allowed delegate agents ({agentIds.length})</summary>{agents.map(a=><label className="checkbox-label" key={a.id}><input type="checkbox" checked={agentIds.includes(a.id)} onChange={e=>setAgentIds(toggle(agentIds,a.id,e.target.checked))}/>{a.name} · v{a.version}</label>)}</details>
   <details><summary>Allowed qualified programs ({programIds.length})</summary>{programs.filter(p=>!p.extensions.length).map(p=><label className="checkbox-label" key={p.id}><input type="checkbox" checked={programIds.includes(p.id)} onChange={e=>setProgramIds(toggle(programIds,p.id,e.target.checked))}/>{p.id} · {p.mode}</label>)}</details>
   <button type="button" className="primary" disabled={busy||!project||!planner||!model||!objective.trim()||(!agentIds.length&&!programIds.length)} onClick={()=>void submit()}>Generate reviewed-plan candidate</button>
  </fieldset>
  <label>Planning history<select value={id} onChange={e=>{setId(e.target.value);setDetail(null);}}><option value="">Select planning job</option>{rows.map(r=><option key={r.id} value={r.id}>{r.objective.slice(0,80)} · {r.mission_id?'Approved':r.run_status}</option>)}</select></label>
  {detail&&<section className="box"><header>Planning result · {detail.state}</header><p>Task {detail.planner_run}</p>{detail.error&&<p role="alert">{detail.error}</p>}
   {detail.plan&&<><h3>{detail.plan.title}</h3><div className="table-scroll"><table><thead><tr><th>Step</th><th>Capability</th><th>Depends on</th><th>Inputs</th></tr></thead><tbody>{detail.plan.steps.map(s=><tr key={s.id}><td>{s.id}</td><td>{s.kind==='agent'?(agents.find(a=>a.id===s.agent_id)?.name||s.agent_id):s.recipe}</td><td>{s.depends_on?.join(', ')||'—'}</td><td>{s.prompt||JSON.stringify(s.values)}</td></tr>)}</tbody></table></div><details><summary>Exact plan and capability versions</summary><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere'}}>{JSON.stringify({plan:detail.plan,capabilities:detail.capabilities},null,2)}</pre><p>Digest: {detail.digest}</p></details></>}
   {!readonly&&["QUEUED","RUNNING"].includes(detail.state||"")&&<button type="button" disabled={busy} onClick={()=>void cancel()}>Cancel planning job</button>}
   {detail.state==='REVIEW_REQUIRED'&&!readonly&&<button type="button" disabled={busy} onClick={()=>void approve()}>Approve and save mission</button>}
   {detail.mission_id&&<p>Saved mission {detail.mission_id}. Select it in the Mission workspace below, then launch the reviewed version.</p>}
  </section>}
 </details>;
}
