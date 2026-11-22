import {useEffect,useRef,useState, type FormEvent} from 'react';
import {ArrowUpRight} from 'lucide-react';
import {api} from './api';
import Chat,{MessageMarkdown} from './Chat';
import Connections from './Connections';
import ProjectWorkspace,{type ProjectLocation} from './Projects';
import Sources from './Sources';
import Settings from './Settings';
import Skills,{AgentCollections,SkillVersions,type Collection} from './Skills';
import {FilesPanel,ArtifactLibrary,AccessPanel,CapabilitiesPanel,useResource,openArtifact} from './Workspace';
import {useSession} from './Session';
import {views,type View} from './layout';
import {themes,type Appearance} from './appearance';
type Row=Record<string,any>;
export function useData(path:string,tick:number){
 const [data,setData]=useState<any>(null),[error,setError]=useState('');
 useEffect(()=>{let alive=true;api(path).then(x=>{if(alive){setData(x);setError('');}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[path,tick]);
 return {data,error};
}
const when=(v:string|null)=>v?new Date(v).toLocaleString():'—';
export function ErrorNote({error}:{error:string}){return error?<div className="error" role="alert">{error}</div>:null;}
function Empty({children}:{children:React.ReactNode}){return <div className="empty">{children}</div>;}
function Status({value}:{value:string}){return <span className={'state '+value.toLowerCase()}>{value.replaceAll('_',' ')}</span>;}
export function Module({view,tick,refresh,go,appearance,changeAppearance,visible,projectLocation,changeProjectLocation}:{projectLocation:ProjectLocation;changeProjectLocation:(location:ProjectLocation)=>void;view:View;visible?:boolean;tick:number;refresh:()=>void;go:(v:View)=>void;appearance:Appearance;changeAppearance:(p:Partial<Appearance>)=>void}){
 const lastVisibleTick=useRef(tick);
 if(visible!==false)lastVisibleTick.current=tick;
 tick=lastVisibleTick.current;
 switch(view){
  case 'Chat':return <Chat tick={tick} visible={visible} sendKey={appearance.sendKey} chatDefaults={appearance.chatDefaults}/>;
  case 'Overview':return <Overview tick={tick} go={go}/>;
  case 'Projects':return <ProjectWorkspace tick={tick} refresh={refresh} location={projectLocation} changeLocation={changeProjectLocation}/>;
  case 'Skills':return <Skills tick={tick} refreshWorkspace={refresh} go={go}/>;
  case 'Agents':return <Agents tick={tick} refresh={refresh} go={go}/>;
  case 'Tasks':return <Tasks tick={tick} refresh={refresh}/>;
  case 'Knowledge':return <Sources tick={tick} refresh={refresh}/>;
  case 'Artifacts':return <ArtifactLibrary tick={tick} refresh={refresh}/>;
  case 'Files':return <FilesPanel tick={tick} refresh={refresh}/>;
  case 'Access':return <AccessPanel tick={tick} refresh={refresh}/>;
  case 'Capabilities':return <CapabilitiesPanel tick={tick}/>;
  case 'Workflows':return <Tasks tick={tick} refresh={refresh} researchOnly/>;
  case 'Models':return <Models tick={tick} refresh={refresh}/>;
  case 'Tools':return <Tools tick={tick}/>;
  case 'Integrations':return <Connections tick={tick} visible={visible}/>;
  case 'Operations':return <Operations tick={tick}/>;
  case 'Settings':return <Settings appearance={appearance} change={changeAppearance}/>;
 }
}
function PageHead({title,subtitle,children}:{title:string;subtitle:string;children?:React.ReactNode}){return <div className="page-head"><div><h1>{title}</h1><p>{subtitle}</p></div>{children}</div>;}
function Overview({tick,go}:{tick:number;go:(v:View)=>void}){
 const {data:d,error}=useData('overview',tick);
 const pending=d?.runs.filter((r:Row)=>['QUEUED','RUNNING','CANCEL_REQUESTED'].includes(r.status)).reduce((n:number,r:Row)=>n+Number(r.n),0);
 return <section className="page"><PageHead title="Overview" subtitle="Workspace activity and service readiness."/><ErrorNote error={error}/><div className="metric-grid">{[['Projects',d?.projects,'Projects'],['Agents',d?.agents,'Agents'],['Active tasks',pending,'Tasks'],['Knowledge documents',d?.documents,'Knowledge']].map(([label,n,v])=><button className="metric" key={label} onClick={()=>go(v as View)}><small>{label}</small><strong>{n??'—'}</strong><ArrowUpRight className="metric-link" size={14} aria-hidden="true"/></button>)}</div><div className="overview-grid"><section className="box"><header>Runtime readiness</header><div className="readiness"><div><span className={'dot '+(d?.worker?.online?'ready':'')}/><b>Task worker</b><span>{d?d.worker?.online?'Online · one inference slot':'Offline or heartbeat stale':'Checking…'}</span></div><div><span className="dot"/><b>Model provider</b><span>{d?.inference.endpoint??'Checking…'}</span><button onClick={()=>go('Models')}>Inspect models</button></div><div><b>Product interfaces</b><span>Independent operation · no connectors required</span><button onClick={()=>go('Integrations')}>Interfaces</button></div></div></section><section className="box"><header>Your workspace</header><div className="pipeline">{(['Projects','Agents','Knowledge','Tasks','Artifacts'] as View[]).map((v,i)=><button key={v} onClick={()=>go(v)}><b>{v}</b><span>{['Define the work','Set instructions','Add project sources','Queue and inspect','Review outputs'][i]}</span></button>)}</div></section></div><div className="two-col overview-notes"><section className="box"><header>Execution boundary</header><p>This release supports local model generation and bounded project tools. Each task records its agent version, tool events and result. Host commands and product actions are unavailable.</p></section><section className="box"><header>Workspace controls</header><p>Use Ctrl K to find a panel or command. Open views together, split your workspace, pin tabs and detach a workspace into its own window.</p><button onClick={()=>go('Tasks')}>Create a task →</button></section></div></section>;
}
type AgentProfile = {name:string;instructions:string;enabled:boolean;runtime_mode:string;tools:string[]};
type AgentRecord = AgentProfile & {id:string;version:number};
const agentTools = ['knowledge.search','project.inspect','artifact.create'];
const initialProfile: AgentProfile = {name:'',instructions:'',enabled:true,runtime_mode:'analysis',tools:agentTools.slice(0,2)};

function Agents({tick,refresh,go}:{tick:number;refresh:()=>void;go:(view:View)=>void}){
 const readonly = useSession().role==='VIEWER';
 const {data,error} = useData('agents',tick);
 const {data:catalog,error:catalogError} = useResource('skills',tick);
 const rows: AgentRecord[] = Array.isArray(data)?data:[];
 const collections: Collection[] = Array.isArray(catalog)?catalog:[];
 const [selected,setSelected] = useState<AgentRecord|null>(null);
 const [section,setSection] = useState<'profile'|'collections'|null>(null);
 const [profile,setProfile] = useState(initialProfile);
 const [dirty,setDirty] = useState(false);
 const [collectionsDirty,setCollectionsDirty] = useState(false);
 const [err,setErr] = useState('');
 const [notice,setNotice] = useState('');
 const [busy,setBusy] = useState(false);
 const heading = useRef<HTMLElement>(null);

 function open(agent:AgentRecord|null,editing=true){
  if ((dirty || collectionsDirty) && !window.confirm('Discard unsaved changes to this agent?')) return;
  setSelected(agent);
  setProfile(agent?{name:agent.name,instructions:agent.instructions,enabled:agent.enabled,runtime_mode:agent.runtime_mode||'analysis',tools:agent.tools||[]}:initialProfile);
  setSection(editing?'profile':null);setErr('');setNotice('');setDirty(false);setCollectionsDirty(false);
  if (editing) window.requestAnimationFrame(()=>heading.current?.focus());
 }
 function edit(change:Partial<AgentProfile>){
  setProfile(current=>({...current,...change}));setDirty(true);setNotice('');
 }
 async function submit(event:FormEvent){
  event.preventDefault();
  if (readonly) return;
  setBusy(true);setErr('');
  try {
   const result = await api(selected?'agents/'+selected.id:'agents',selected?'PUT':'POST',profile);
   setSelected({...profile,id:selected?.id??result.id,version:selected?result.version:1});
   setDirty(false);
   setNotice(selected?'Profile saved.':'Agent created. Choose collections to use with it.');
   if (!selected) setSection('collections');
   refresh();
  } catch (failure) {setErr((failure as Error).message);}
  finally {setBusy(false);}
 }
 return <section className="page agents-page">
  <PageHead title="Agents" subtitle="Set up an agent, attach skill collections, and use it in Chat.">
   <div className="actions"><button type="button" onClick={()=>go('Skills')}>Open Skills</button>
    {!readonly&&<button type="button" className="primary" disabled={busy} onClick={()=>open(null)}>New agent</button>}</div>
  </PageHead>
  <ErrorNote error={error}/>
  <div className="two-col agents-grid">
   <section className="box"><header>Agent registry <span>{data&&rows.length+(rows.length===1?' agent':' agents')}</span></header>
    <div className="skill-index">{rows.map(agent=><button type="button" className="record" key={agent.id}
     aria-current={selected?.id===agent.id?'true':undefined} disabled={busy} onClick={()=>open(agent)}>
     <b>{agent.name}</b><span>v{agent.version} · {agent.enabled?'Enabled':'Disabled'}</span>
    </button>)}</div>
    {rows.length===0&&<Empty>{data?'No agents yet.':'Loading agents…'}</Empty>}
   </section>
   {section ? <section className="box agent-detail">
    <header tabIndex={-1} ref={heading}>{selected?.name??'New agent'} {selected&&<span>Version {selected.version}</span>}</header>
    <nav className="skill-steps" aria-label="Agent setup">
     <button type="button" aria-current={section==='profile'?'step':undefined} onClick={()=>setSection('profile')}>1. Profile</button>
     <button type="button" aria-current={section==='collections'?'step':undefined} disabled={!selected||busy} onClick={()=>setSection('collections')}>2. Attach skills</button>
     <button type="button" disabled={!selected?.enabled||busy} onClick={()=>go('Chat')}>3. Open Chat</button>
    </nav>
    <ErrorNote error={err}/>
    {notice&&<p role="status" className="panel-note">{notice}</p>}
    <form hidden={section!=='profile'} className="form" onSubmit={submit}>
     <fieldset className="agent-profile" disabled={busy||readonly}>
      <label>Agent name<input required maxLength={120} value={profile.name} onChange={event=>edit({name:event.target.value})}/></label>
      <label>Instructions<textarea required rows={7} maxLength={16000} value={profile.instructions} onChange={event=>edit({instructions:event.target.value})} placeholder="Define the role, purpose, and expected output."/></label>
      <label>Execution mode<select value={profile.runtime_mode} onChange={event=>edit({runtime_mode:event.target.value})}><option value="analysis">Analysis · retrieve and answer</option><option value="tools">Tools · bounded model-directed execution</option></select></label>
      {profile.runtime_mode==='tools'&&<fieldset className="tool-permissions"><legend>Permitted tools</legend>
       {agentTools.map(tool=><label className="checkbox-label" key={tool}><input type="checkbox" checked={profile.tools.includes(tool)} onChange={event=>edit({tools:event.target.checked?[...profile.tools,tool]:profile.tools.filter(value=>value!==tool)})}/>{tool}</label>)}
       <small>Requires model tool support. Up to six model steps and eight tool calls.</small>
      </fieldset>}
      <label><input type="checkbox" checked={profile.enabled} onChange={event=>edit({enabled:event.target.checked})}/>Enabled for new tasks</label>
     </fieldset>
     <div className="actions">
      {!readonly&&<button className="primary" disabled={busy}>{busy?'Saving…':selected?'Save new version':'Create agent'}</button>}
      {selected?<button type="button" disabled={busy} onClick={()=>setSection('collections')}>Continue to skill setup</button>
       :<button type="button" disabled={busy} onClick={()=>open(null,false)}>Cancel</button>}
     </div>
    </form>
    {selected&&<div className="form" hidden={section!=='collections'}>
     <p className="panel-note">A collection is a group of skills. Attach the groups this agent should be able to use. In Chat, choose this agent beside Skills, then use automatic matching or choose specific skills.</p>
     <ErrorNote error={catalogError}/>
     <AgentCollections key={selected.id} agent={selected.id} rows={collections} tick={tick} readonly={readonly} onDirtyChange={setCollectionsDirty} onSaved={selected.enabled?()=>go('Chat'):undefined} onReview={()=>go('Skills')}/>
    </div>}
   </section> : <section className="box settings-content"><h2>Start with an agent</h2>
    <p>{readonly?'Select an agent to see its profile and collections.':'Select an agent from the registry or choose New agent to start. Save the profile, attach collections, then open Chat.'}</p>
   </section>}
  </div>
 </section>;
}
function Tasks({tick,refresh,researchOnly=false}:{tick:number;refresh:()=>void;researchOnly?:boolean}){
 const readonly=useSession().role==='VIEWER';
 const {data:projects}=useData('projects',tick),{data:agents}=useData('agents',tick),{data:models}=useData('models',tick),{data:runs,error}=useData('runs',tick);
 const [id,setId]=useState(''),{data:detail,error:detailError}=useData(id?'runs/'+id:'runs',tick);
 const [err,setErr]=useState(''),[busy,setBusy]=useState(false),[research,setResearch]=useState(researchOnly),[calcs,setCalcs]=useState<number[]>([]);
 async function submit(e:FormEvent<HTMLFormElement>){
  e.preventDefault();
  const form=e.currentTarget,f=new FormData(form),field=(name:string)=>String(f.get(name)??'');
  const body={project_id:field('project_id'),agent_id:field('agent_id'),model:field('model'),prompt:field('prompt'),
   ...(research?{research:{success_criteria:field('criteria'),queries:field('queries').split(/\r?\n/).map(v=>v.trim()).filter(Boolean),
    ...(field('scheduled')?{scheduled_for:new Date(field('scheduled')).toISOString()}:{}),
    require_review:f.has('require_review'),timeout_seconds:Number(field('timeout')),max_output_tokens:Number(field('tokens')),
    calculations:calcs.map(n=>({label:field('label'+n),left:field('left'+n),right:field('right'+n),operation:field('operation'+n)}))}}:{})};
  setBusy(true);
  try{
   const r=await api('runs','POST',body);
   setId(r.id);
   (form.elements.namedItem('prompt') as HTMLTextAreaElement).value='';
   setErr('');refresh();
  }catch(e){setErr((e as Error).message);}
  finally{setBusy(false);}
 }
 async function action(name:string,body:unknown={}){
  setBusy(true);
  try{const result=await api('runs/'+id+'/'+name,'POST',body);if(name==='retry')setId(result.id);setErr('');refresh();}
  catch(e){setErr((e as Error).message);}
  finally{setBusy(false);}
 }
 const enabled=agents?.filter((a:Row)=>a.enabled);
 return <section className="page">
  <PageHead title={researchOnly?'Workflows':'Tasks'} subtitle={researchOnly?'Project research with cited evidence, checkpoints, and review.':'Queue work and inspect the recorded result.'}/>
  <ErrorNote error={err||error||detailError}/>
  <details className="box" open={!id}><summary>{researchOnly?'New research run':'New task'}</summary>
   <form className="form research-form" onSubmit={submit}>
    <div className="fields task-fields">
     <label>Project<select name="project_id" required defaultValue=""><option value="" disabled>Select project</option>{projects?.filter((p:Row)=>!p.archived_at).map((p:Row)=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label>
     <label>Agent<select name="agent_id" required defaultValue=""><option value="" disabled>Select agent</option>{enabled?.map((p:Row)=><option key={p.id} value={p.id}>{p.name} · v{p.version}</option>)}</select></label>
     <label>Model<select name="model" required defaultValue=""><option value="" disabled>Select model</option>{models?.models.map((p:Row)=><option key={p.name}>{p.name}</option>)}</select></label>
    </div>
    {models&&!models.available&&<p className="warn">Model host is offline. Open Models to inspect the connection.</p>}
    {!researchOnly&&<label>Execution<select value={research?'research':'agent'} onChange={e=>setResearch(e.target.value==='research')}><option value="agent">Agent settings</option><option value="research">Durable research</option></select></label>}
    <label>{research?'Research goal':'Task instructions'}<textarea name="prompt" rows={4} required maxLength={20000} placeholder="Describe the work and the expected result…"/></label>
    {research&&<>
     <label>Success criteria<input name="criteria" maxLength={240} required placeholder="Which questions must the report answer?"/></label>
     <label>Search queries, one per line<textarea name="queries" rows={3} maxLength={1204} placeholder="Optional. Leave blank to let the model propose up to five queries."/></label>
     <details className="research-options"><summary>Limits and calculations</summary>
      <div className="fields">
       <label>Scheduled start (optional)<input type="datetime-local" name="scheduled"/></label>
       <label>Deadline (seconds)<input type="number" name="timeout" defaultValue={600} min={60} max={3600} required/></label>
       <label>Output tokens per model call<input type="number" name="tokens" defaultValue={1200} min={256} max={2048} required/></label>
      </div>
      {calcs.map(n=><fieldset key={n} className="research-calculation"><legend>Calculation {n}</legend>
       <label>Label<input name={'label'+n} required maxLength={240}/></label>
       <div className="fields">
        <label>First value<input name={'left'+n} inputMode="decimal" maxLength={32} required/></label>
        <label>Operation<select name={'operation'+n}><option value="add">Add</option><option value="subtract">Subtract</option><option value="multiply">Multiply</option><option value="divide">Divide</option><option value="percent_change">Percent change from first to second</option></select></label>
        <label>Second value<input name={'right'+n} inputMode="decimal" maxLength={32} required/></label>
       </div>
       <button type="button" onClick={()=>setCalcs(current=>current.filter(value=>value!==n))}>Remove calculation</button>
      </fieldset>)}
      <button type="button" disabled={calcs.length>=8} onClick={()=>setCalcs(current=>[...current,Math.max(0,...current)+1])}>Add calculation</button>
     </details>
     <label className="checkbox-label"><input type="checkbox" name="require_review" defaultChecked/>Review before saving the private report</label>
    </>}
    <button className="primary" disabled={busy||readonly||!projects?.length||!enabled?.length||!models?.available}>{research?'Queue research':'Queue task'}</button>
   </form>
  </details>
  <section className="box"><header>{researchOnly?'Research runs':'Recent tasks'} <span>Latest 100</span></header>
   <div className="table-scroll"><table><thead><tr><th>Task</th><th>Project / agent</th><th>Model</th><th>Status</th><th>Created</th></tr></thead>
    <tbody>{runs?.filter((r:Row)=>!researchOnly||r.research_phase).map((r:Row)=><tr key={r.id} aria-selected={r.id===id}>
     <td><button className="link" onClick={()=>setId(r.id)}>{r.prompt.slice(0,70)}</button></td><td>{r.project}<small className="block">{r.agent}</small></td>
     <td>{r.model}</td><td><Status value={r.status}/></td><td>{when(r.created_at)}</td>
    </tr>)}</tbody></table></div>
   {runs&&!runs.some((r:Row)=>!researchOnly||r.research_phase)&&<Empty>No runs submitted.</Empty>}
  </section>
  {id&&detail?.id===id&&<section className="box result"><header><span>Task result · <Status value={detail.status}/></span>
   <div className="actions">
    {['QUEUED','RUNNING','PAUSED','WAITING_REVIEW','SCHEDULED'].includes(detail.status)&&<button disabled={readonly||busy} onClick={()=>void action('cancel')}>Cancel task</button>}
    {detail.research&&['QUEUED','RUNNING'].includes(detail.status)&&<button disabled={readonly||busy} onClick={()=>void action('pause')}>Pause</button>}
    {detail.research&&detail.status==='PAUSED'&&<button disabled={readonly||busy} onClick={()=>void action('resume')}>Resume</button>}
    {detail.research&&['FAILED','CANCELLED'].includes(detail.status)&&<button disabled={readonly||busy} onClick={()=>void action('retry')}>Start new attempt</button>}
    {detail.output&&<button onClick={()=>download(detail.output,'core-ai-'+id+'.md')}>Download result</button>}
   </div></header>
   <div className="meta">Agent v{detail.agent_version} · {detail.model} · {detail.id}</div>
   <SkillVersions versions={detail.skill_versions}/>
   <p>{detail.prompt}</p><ErrorNote error={detail.error||''}/>
   {detail.research&&<ResearchDetails detail={detail} readonly={readonly||busy} action={action}/>}
   {detail.output?<><MessageMarkdown text={detail.output}/>
    {detail.research?.artifact_id?<button onClick={()=>openArtifact(detail.research.artifact_id)}>Open saved artifact</button>:
     !detail.research&&<button onClick={async()=>{try{const a=await api('library/artifacts','POST',{title:detail.prompt.slice(0,80),kind:'markdown',content:detail.output,project_id:detail.project_id,source_run_id:detail.id});openArtifact(a.id);refresh();}catch(e){setErr((e as Error).message);}}}>Open as artifact</button>}
   </>:detail.status!=='WAITING_REVIEW'&&<Empty>{detail.status==='CANCEL_REQUESTED'?'Cancellation requested. Waiting for the current provider read to stop.':detail.status==='RUNNING'?'The task is running. Its recorded steps and final result appear below.':'No final output recorded.'}</Empty>}
   <details><summary>Agent steps · {detail.steps?.length||0}</summary>{detail.steps?.map((s:Row)=><div className="log-line" key={s.id}><b>{s.step} · {s.kind} {s.tool}</b><details><summary>Input and result</summary><pre>{JSON.stringify({input:s.input,result:s.result},null,2)}</pre></details></div>)}</details>
   <details><summary>Execution timeline</summary>{detail.events?.map((e:Row)=><div className="log-line" key={e.id}><time>{when(e.created_at)}</time><b>{e.action}</b><code>{JSON.stringify(e.detail)}</code></div>)}</details>
  </section>}
 </section>;

}
function ResearchDetails({detail,readonly,action}:{detail:Row;readonly:boolean;action:(name:string,body:unknown)=>Promise<void>}){
 const run=detail.research;
 const phases:Record<string,string>={PLAN:'Planning',COLLECT:'Collecting evidence',SYNTHESIZE:'Preparing report',COMPLETE:'Report prepared'};
 return <div className="research-details">
  <dl><dt>Checkpoint</dt><dd>{phases[run.phase]||run.phase}</dd><dt>Success criteria</dt><dd>{run.specification.success_criteria}</dd>
   <dt>Usage</dt><dd>{run.calls} model calls · {run.measured_input_tokens} reported input tokens · {run.measured_output_tokens} reported output tokens</dd>
   {run.scheduled_for&&<><dt>Scheduled start</dt><dd>{when(run.scheduled_for)}</dd></>}
   <dt>Run deadline</dt><dd>{when(run.deadline)}</dd></dl>
  {run.plan&&<details><summary>Search plan</summary><ul>{run.plan.queries.map((q:string,i:number)=><li key={i}>{q}</li>)}</ul></details>}
  {run.evidence&&<details><summary>Source revisions · {run.evidence.length}</summary><ol>{run.evidence.map((source:Row)=><li key={source.id}><b>{source.title}</b> · revision {source.version}<blockquote>{source.excerpt}</blockquote></li>)}</ol></details>}
  {detail.status==='WAITING_REVIEW'&&<section className="research-review">
   <h3>Review private report</h3><p>Review expires {when(run.review_expires_at)}.</p><MessageMarkdown text={run.draft}/>
   <div className="actions">
    <button className="primary" disabled={readonly} onClick={()=>void action('review',{digest:run.review_digest,decision:'approve'})}>Approve and save</button>
    <button disabled={readonly} onClick={()=>void action('review',{digest:run.review_digest,decision:'reject'})}>Reject draft</button>
   </div>
  </section>}
 </div>;
}
export function download(text:string,name:string){const url=URL.createObjectURL(new Blob([text],{type:'text/plain'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function Models({tick,refresh}:{tick:number;refresh:()=>void}){
 const session=useSession();const {data,error}=useData('models',tick),[inspection,setInspection]=useState<Row|null>(null),[err,setErr]=useState(''),[busy,setBusy]=useState(false);
 async function submit(e:FormEvent<HTMLFormElement>){e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);try{await api('models/config','PUT',Object.fromEntries(f));refresh();setErr('');}catch(e){setErr((e as Error).message);}finally{setBusy(false);}}
 return <section className="page"><PageHead title="Models" subtitle="Ollama inference · laptop now, private VPS endpoint later"><button onClick={refresh}>Refresh</button></PageHead><ErrorNote error={error||err||data?.error||''}/>{data&&<form className="box form" key={JSON.stringify(data.config)} onSubmit={submit}><header>Inference connection <Status value={data.available?'ONLINE':'OFFLINE'}/></header><div className="fields"><label>Private Ollama endpoint<input name="endpoint" required defaultValue={data.config.endpoint}/></label><label>Default model<input name="model" required defaultValue={data.config.model}/></label></div><p>Only private or loopback IPv4 endpoints are accepted. Changing the endpoint does not move model files.</p><button className="primary" disabled={busy||session.role!=='ADMIN'}>Save connection</button>{session.role!=='ADMIN'&&<small>Administrator access is required to change inference configuration.</small>}</form>}<section className="box"><header>Installed models <span>{data?.models.length??'—'}</span></header><div className="table-scroll"><table><thead><tr><th>Name</th><th>Size</th><th>Family</th><th>Quantization</th><th>Capabilities</th></tr></thead><tbody>{data?.models.map((m:Row)=><tr key={m.name}><td>{m.name}</td><td>{(m.size/1e9).toFixed(2)} GB</td><td>{m.details?.family??'—'}</td><td>{m.details?.quantization_level??'—'}</td><td><button onClick={async()=>{try{setInspection(await api('models/inspect?model='+encodeURIComponent(m.name)));setErr('');}catch(e){setErr((e as Error).message);}}}>Inspect</button></td></tr>)}</tbody></table></div><p className="panel-note">Installed models are not certified for every task. Embedding models should not be selected for text generation; model errors are recorded against the task.</p></section>{inspection&&<section className="box"><header>{inspection.model} · Provider-reported capabilities</header><div className="settings-content"><p>{inspection.capabilities.length?inspection.capabilities.join(', '):'Provider did not report capabilities.'}</p><pre>{JSON.stringify(inspection.context_windows,null,2)}</pre><details><summary>Model parameters and license</summary><pre>{inspection.parameters}{'\n'}{inspection.license}</pre></details></div></section>}</section>;
}
function Tools({tick}:{tick:number}){const {data,error}=useData('tools',tick);return <section className="page"><PageHead title="Tools" subtitle="Backend-enforced capabilities · no unrestricted host execution"/><ErrorNote error={error}/><section className="box"><header>Available tools</header>{data?.map((r:Row)=><div className="document-row" key={r.id}><div><b>{r.id}</b><p>{r.description}</p></div><Status value={r.enabled?'ENABLED':'DISABLED'}/></div>)}</section><p>Analysis mode retrieves and answers. Tools mode performs bounded, recorded calls to the agent’s permitted tools using a tools-capable model. Host shell, coding sandboxes and external actions remain unavailable.</p></section>;}

export function Operations({tick}:{tick:number}){const {data,error}=useData('events',tick),{data:metrics}=useResource('operations/metrics',tick);return <section className="page"><PageHead title="Operations" subtitle="Persisted audit events · latest 200 · local service logs through ./core-ai logs"/><ErrorNote error={error}/><section className="box"><header>Observed inference metrics · latest requests</header><div className="table-scroll"><table><thead><tr><th>Model</th><th>Status</th><th>Duration</th><th>Tokens/s</th></tr></thead><tbody>{[...(metrics?.chats||[]),...(metrics?.tasks||[])].slice(0,30).map((r:Row)=><tr key={r.id}><td>{r.model}</td><td>{r.status}</td><td>{r.metrics.duration_ms!==undefined?(r.metrics.duration_ms/1000).toFixed(2)+' s':'—'}</td><td>{r.metrics.tokens_per_second??'Not reported'}</td></tr>)}</tbody></table></div></section><section className="box"><header>Audit timeline</header>{data?.map((e:Row)=><div className="log-line" key={e.id}><time>{when(e.created_at)}</time><b>{e.action}</b><code>{JSON.stringify(e.detail)}</code></div>)}{data?.length===0&&<Empty>No events recorded.</Empty>}</section></section>;}
export function Inspector({view,tick}:{view:View;tick:number}){const {data}=useData('overview',tick);return <><div className="panel-heading">CONTEXT</div><div className="inspector-body"><span className="eyebrow">ACTIVE PANEL</span><h2>{view}</h2><dl><dt>Product</dt><dd>CORE-AI</dd><dt>Release</dt><dd>{data?.release??'—'}</dd><dt>Worker</dt><dd>{data?.worker?.online?'Online':'Unavailable'}</dd><dt>Provider</dt><dd>{data?.inference.endpoint??'—'}</dd><dt>Execution</dt><dd>Read project sources + local inference</dd></dl><p>No mandatory product connections. No host commands enabled.</p></div></>;}
export function Activity({tick}:{tick:number}){const {data,error}=useData('events',tick);return <div className="activity-log"><ErrorNote error={error}/>{data?.slice(0,30).map((e:Row)=><div key={e.id}><time>{when(e.created_at)}</time><b>{e.action}</b><span>{JSON.stringify(e.detail)}</span></div>)}{data?.length===0&&<span>No activity yet.</span>}</div>;}
