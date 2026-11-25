import {useEffect,useState,type FormEvent} from 'react';
import {api} from './api';
import {useSession} from './Session';
import {ParameterEditor,generationModel,modelLabel,title,type Program,type Model} from './CapabilityFields';

type Agent={id:string;name:string;version:number;enabled:boolean;runtime_mode?:string};
type Project={id:string;name:string;archived_at?:string|null};
type Draft={id:string;kind:'agent'|'program';depends_on:string[];whenText:string;recipe:string;values:string;file_id:string;agent_id:string;model:string;prompt:string};
type Template={id:string;title:string;objective:string;project_id:string;version:number;steps:any[]};
type MissionRun={id:string;template_id:string;title:string;status:string;cursor:number;version:number;error?:string;history?:{step:string;kind:string;child_id:string|null;status:string}[];steps?:any[];child_id?:string;child_kind?:string};
type Listing={templates:Template[];runs:MissionRun[]};
function newStep(id:string):Draft{return {id,kind:'agent',depends_on:[],whenText:'',recipe:'',values:'[]',file_id:'',agent_id:'',model:'',prompt:''};}
function fromSaved(s:any):Draft{return {...newStep(s.id),...s,values:JSON.stringify(s.values||[],null,2),file_id:s.file_id||'',whenText:s.when?JSON.stringify(s.when,null,2):''};}
function toSaved(s:Draft){
 const base={id:s.id,kind:s.kind,depends_on:s.depends_on,...(s.whenText.trim()?{when:JSON.parse(s.whenText)}:{})};
 return s.kind==='agent'?{...base,agent_id:s.agent_id,model:s.model,prompt:s.prompt}:{...base,recipe:s.recipe,values:JSON.parse(s.values),file_id:s.file_id||null};
}
export default function MissionPanel({tick,visible=true}:{tick:number;visible?:boolean}){
 const readonly=useSession().role==='VIEWER';
 const [data,setData]=useState<Listing|null>(null),[projects,setProjects]=useState<Project[]>([]),[agents,setAgents]=useState<Agent[]>([]),[models,setModels]=useState<Model[]>([]),[programs,setPrograms]=useState<Program[]>([]),[files,setFiles]=useState<{id:string;name:string}[]>([]);
 const [selected,setSelected]=useState<Template|null>(null),[name,setName]=useState(''),[objective,setObjective]=useState(''),[project,setProject]=useState(''),[steps,setSteps]=useState<Draft[]>([newStep('step-1')]);
 const [runId,setRunId]=useState(''),[run,setRun]=useState<MissionRun|null>(null),[child,setChild]=useState<any>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false);
 async function reload(){const d=await api('missions');if(!Array.isArray(d?.templates)||!Array.isArray(d?.runs))throw new Error('Mission registry unavailable.');setData(d);}
 useEffect(()=>{if(!visible)return;let live=true;void Promise.allSettled([api('missions').then(d=>{if(live&&Array.isArray(d?.templates)&&Array.isArray(d?.runs))setData(d);}),api('projects').then(d=>{if(live&&Array.isArray(d))setProjects(d.filter(p=>!p.archived_at));}),api('agents').then(d=>{if(live&&Array.isArray(d))setAgents(d.filter(a=>a.enabled));}),api('models?catalog=true').then(d=>{if(live&&Array.isArray(d?.models))setModels(d.models.filter(generationModel));}),api('programs','GET',undefined,50000).then(d=>{if(live&&Array.isArray(d?.programs))setPrograms(d.programs.filter((p:Program)=>p.state==='qualified-receipt'));})]);return()=>{live=false;};},[visible,tick]);
 useEffect(()=>{if(!visible||!project){setFiles([]);return;}let live=true;api('files?project_id='+encodeURIComponent(project)).then(d=>{if(live&&Array.isArray(d))setFiles(d);}).catch(()=>{if(live)setFiles([]);});return()=>{live=false;};},[project,visible]);
 useEffect(()=>{if(!runId||!visible)return;let live=true;const read=()=>api('missions/runs/'+runId).then(d=>{if(live&&d?.id===runId)setRun(d);}).catch(e=>{if(live)setError(e.message);});void read();const timer=setInterval(read,1800);return()=>{live=false;clearInterval(timer);};},[runId,visible]);
 function edit(index:number,patch:Partial<Draft>){setSteps(old=>old.map((s,i)=>i===index?{...s,...patch}:s));setDirty(true);}
 function open(t:Template|null){if(dirty&&!window.confirm('Discard unsaved mission edits?'))return;setSelected(t);setName(t?.title||'');setObjective(t?.objective||'');setProject(t?.project_id||'');setSteps(t?t.steps.map(fromSaved):[newStep('step-1')]);setDirty(false);setError('');}
 async function save(e:FormEvent){e.preventDefault();setBusy(true);setError('');try{const body={title:name,objective,project_id:project,steps:steps.map(toSaved)};const r=await api(selected?'missions/'+selected.id:'missions',selected?'PUT':'POST',selected?{...body,expected_version:selected.version}:body);setSelected({...body,id:selected?.id||r.id,version:r.version});setDirty(false);await reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function start(){if(!selected||dirty)return;if(!window.confirm('Launch this saved mission version using the displayed agents, program inputs and dependencies?'))return;setBusy(true);setError('');try{const r=await api('missions/'+selected.id+'/start','POST',{version:selected.version},50000);setRun(null);setRunId(r.id);setChild(null);await reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function control(action:string){if(!run)return;setBusy(true);setError('');try{await api('missions/runs/'+run.id+'/control','POST',{action});setRun(await api('missions/runs/'+run.id));await reload();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function inspect(kind:string,id:string){try{setChild(await api((kind==='program'?'programs/jobs/':'runs/')+id));}catch(e){setError((e as Error).message);}}
 return <section className="box">
  <header>Mission workspace <button type="button" disabled={busy||readonly} onClick={()=>open(null)}>New mission</button></header>
  <p>Define an objective, select existing agents and programs, review dependencies, then launch a versioned workflow. Execution is sequential on the current resource-limited host; independent steps may be ordered explicitly.</p>
  {error&&<div className="error" role="alert">{error}</div>}
  <div className="fields"><label>Saved mission<select value={selected?.id||''} onChange={e=>open(data?.templates.find(t=>t.id===e.target.value)||null)}><option value="">New mission</option>{data?.templates.map(t=><option value={t.id} key={t.id}>{t.title} · v{t.version}</option>)}</select></label><label>Execution history<select value={runId} onChange={e=>{setRunId(e.target.value);setRun(null);setChild(null);}}><option value="">Select execution</option>{data?.runs.map(r=><option value={r.id} key={r.id}>{r.title} · {r.status}</option>)}</select></label></div>
  <form className="form" onSubmit={save}>
   <fieldset disabled={readonly||busy} className="form">
    <div className="fields"><label>Mission name<input required value={name} maxLength={120} onChange={e=>{setName(e.target.value);setDirty(true);}}/></label><label>Project<select required value={project} onChange={e=>{setProject(e.target.value);setDirty(true);}}><option value="">Choose project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label></div>
    <label>Objective & acceptance criteria<textarea required value={objective} maxLength={4000} rows={3} onChange={e=>{setObjective(e.target.value);setDirty(true);}}/></label>
    <header>Execution plan · {steps.length} steps</header>
    {steps.map((s,i)=>{
      const p=programs.find(p=>p.id===s.recipe),a=agents.find(a=>a.id===s.agent_id);
      return <section className="box form" key={i}>
       <header>Step {i+1} · {s.kind}<button type="button" disabled={steps.length===1} onClick={()=>{setSteps(old=>old.filter((_,j)=>j!==i).map(x=>({...x,depends_on:x.depends_on.filter(d=>d!==s.id)})));setDirty(true);}}>Remove step</button></header>
       <div className="fields"><label>Step ID<input required pattern="[a-z][a-z0-9-]{0,39}" value={s.id} onChange={e=>edit(i,{id:e.target.value})}/></label><label>Capability<select value={s.kind} onChange={e=>edit(i,{kind:e.target.value as Draft['kind']})}><option value="agent">Agent</option><option value="program">Independent program</option></select></label></div>
       {s.kind==='agent'?<><div className="fields"><label>Agent<select required value={s.agent_id} onChange={e=>edit(i,{agent_id:e.target.value,model:''})}><option value="">Choose agent</option>{agents.map(a=><option key={a.id} value={a.id}>{a.name} · v{a.version}</option>)}</select></label><label>Model<select required value={s.model} onChange={e=>edit(i,{model:e.target.value})}><option value="">Choose model</option>{models.filter(m=>a?.runtime_mode!=='tools'||!Array.isArray(m.capabilities)||m.capabilities.includes('tools')).map(m=><option key={m.name} value={m.name}>{modelLabel(m)}</option>)}</select></label></div><label>Instructions<textarea required rows={3} value={s.prompt} onChange={e=>edit(i,{prompt:e.target.value})}/></label></>:<>
        <label>Program<select required value={s.recipe} onChange={e=>{const p=programs.find(p=>p.id===e.target.value);edit(i,{recipe:e.target.value,values:JSON.stringify(p?.example||[],null,2),file_id:''});}}><option value="">Choose qualified program</option>{programs.map(p=><option key={p.id} value={p.id}>{title(p.id)}</option>)}</select></label>
        {p&&p.extensions.length>0?<label>Project input file<select required value={s.file_id} onChange={e=>edit(i,{file_id:e.target.value})}><option value="">Choose file</option>{files.filter(f=>p.extensions.some(ext=>f.name.toLowerCase().endsWith(ext))).map(f=><option key={f.id} value={f.id}>{f.name}</option>)}</select></label>:p&&<ParameterEditor program={p} value={s.values} onChange={values=>edit(i,{values})}/>}
       </>}
       {!!i&&<fieldset><legend>Dependencies</legend>{steps.slice(0,i).map((prev,j)=><label className="checkbox-label" key={j}><input type="checkbox" checked={s.depends_on.includes(prev.id)} onChange={e=>edit(i,{depends_on:e.target.checked?[...s.depends_on,prev.id]:s.depends_on.filter(d=>d!==prev.id)})}/>{prev.id}</label>)}</fieldset>}
       {!!i&&<details><summary>Conditional branch / result references</summary><label>Optional condition (JSON)<textarea rows={3} value={s.whenText} onChange={e=>edit(i,{whenText:e.target.value})} placeholder={'{"step":"step-1","path":["units"],"equals":20}'}/></label><small>Use Advanced JSON to reference a dependency result as a parameter: {'{"$step":"step-1","path":["units"]}'}. A condition must refer to a declared dependency.</small></details>}
      </section>;
    })}
    <div className="actions"><button type="button" disabled={steps.length>=20} onClick={()=>{let n=steps.length+1;while(steps.some(s=>s.id==='step-'+n))n++;setSteps(old=>[...old,newStep('step-'+n)]);setDirty(true);}}>Add step</button><button className="primary" type="submit">{selected?'Save new version':'Save mission'}</button><button type="button" disabled={!selected||dirty} onClick={()=>void start()}>Launch reviewed version</button></div>
   </fieldset>
  </form>
  {run&&<section className="box"><header>{run.title} · {run.status} · v{run.version}</header><p>{run.cursor} / {run.steps?.length||0} checkpoints completed · {run.id}</p>
    {run.error&&<p role="alert">{run.error}</p>}
    <div className="actions">{!readonly&&['QUEUED','RUNNING'].includes(run.status)&&<button disabled={busy} onClick={()=>void control('pause')}>Pause after current step</button>}{!readonly&&run.status==='PAUSED'&&<button disabled={busy} onClick={()=>void control('resume')}>Resume</button>}{!readonly&&run.status==='FAILED'&&<button disabled={busy} onClick={()=>void control('retry')}>Retry failed checkpoint</button>}{!readonly&&['QUEUED','RUNNING','PAUSED','PAUSE_REQUESTED'].includes(run.status)&&<button disabled={busy} onClick={()=>void control('cancel')}>Cancel mission</button>}</div>
    <div className="table-scroll"><table><thead><tr><th>Step</th><th>Status</th><th>Execution</th></tr></thead><tbody>{run.history?.map((h,i)=><tr key={i}><td>{h.step}</td><td>{h.status}</td><td>{h.child_id&&<button onClick={()=>void inspect(h.kind,h.child_id!)}>Inspect result</button>}</td></tr>)}{run.child_id&&<tr><td>{run.steps?.[run.cursor]?.id}</td><td>Active child</td><td><button onClick={()=>void inspect(run.child_kind!,run.child_id!)}>Inspect progress</button></td></tr>}</tbody></table></div>
    {child&&<section className="box"><header>Child execution · {child.status}</header><p>{child.error}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'25rem',overflow:'auto'}}>{JSON.stringify(child.result??child.output??null,null,2)}</pre>{child.file_name&&<a href={'/api/v1/programs/jobs/'+encodeURIComponent(child.id)+'/download'}>Download {child.file_name}</a>}</section>}
  </section>}
 </section>;
}
