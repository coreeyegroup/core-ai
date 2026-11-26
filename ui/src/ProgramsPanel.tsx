import {useEffect,useRef,useState,type FormEvent} from 'react';
import {api,newId} from './api';
import {useSession} from './Session';
import {ParameterEditor,title,type Program} from './CapabilityFields';

type Repo={repository:string;commit:string;source_present:boolean;recipes:string[];coverage:string;inventory_counts?:Record<string,number>;file_count?:number;next_action?:string;family?:string;installation_state?:string;entrypoints?:{path:string;present:boolean}[]};
type Catalog={schema:number;programs:Program[];repositories:Repo[];native?:unknown;native_execution?:{profile:string;model:string;mode:string;state:string;report_id:string;evidence:unknown}[];native_profiles?:{profile:string;registration:string;model_execution:string;route?:string;report_id?:string;checks?:unknown}[];packages?:{id:string;state:string;repo:string;commit:string;image?:string;report_id?:string}[]};
type Job={id:string;recipe:string;status:string;created_at:string;error?:string;error_code?:string;file_name?:string;result?:{id:string;result:unknown;provenance:string;commit:string;image:string};retry_of?:string;parent_run?:string;parent_chat?:string;connection_id?:string};
const active=(s:string)=>['QUEUED','RUNNING','CANCEL_REQUESTED'].includes(s);
function encode(file:File):Promise<string>{return new Promise((resolve,reject)=>{const r=new FileReader();r.onerror=()=>reject(new Error('Unable to read file.'));r.onload=()=>{const t=String(r.result);resolve(t.slice(t.indexOf(',')+1));};r.readAsDataURL(file);});}
function group(id:string,mode:string){return mode==='diagnostic'?'Diagnostics':/pdf|pptx|docx|xlsx|notebook/.test(id)?'Documents':/research/.test(id)?'Research':/diagram|ui-ux|graph|chapter/.test(id)?'Engineering':'Finance & analytics';}
export default function ProgramsPanel({tick,visible=true}:{tick:number;visible?:boolean}){
 const readonly=useSession().role==='VIEWER';
 const [catalog,setCatalog]=useState<Catalog|null>(null),[loadError,setLoadError]=useState(''),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(''),[category,setCategory]=useState('All'),[selected,setSelected]=useState(''),[values,setValues]=useState('[]'),[file,setFile]=useState<File|null>(null);
 const [jobs,setJobs]=useState<Job[]>([]),[jobId,setJobId]=useState(''),[job,setJob]=useState<Job|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 const request=useRef<{body:string;id:string}|null>(null);
 async function refreshJobs(){const d=await api('programs/jobs');if(!Array.isArray(d))throw new Error('Program history unavailable.');setJobs(d);}
 useEffect(()=>{if(!visible)return;let alive=true;setLoadError('');api('programs','GET',undefined,50000).then((d:Catalog)=>{if(!d||d.schema!==1||!Array.isArray(d.programs)||!Array.isArray(d.repositories)||!d.programs.every(r=>r&&typeof r.id==='string'&&Array.isArray(r.example)&&Array.isArray(r.extensions)))throw new Error('Invalid program catalog.');if(alive)setCatalog(d);}).catch(e=>{if(alive)setLoadError(e.message);});return()=>{alive=false;};},[tick,refresh,visible]);
 useEffect(()=>{if(!visible)return;let alive=true;const read=()=>api('programs/jobs').then(d=>{if(alive&&Array.isArray(d))setJobs(d);}).catch(e=>{if(alive)setError(e.message);});void read();const timer=setInterval(read,5000);return()=>{alive=false;clearInterval(timer);};},[visible,refresh]);
 useEffect(()=>{if(!jobId||!visible||(job?.id===jobId&&!active(job.status)))return;let alive=true;const read=()=>api('programs/jobs/'+jobId).then(d=>{if(alive&&d?.id===jobId)setJob(d);}).catch(e=>{if(alive)setError(e.message);});void read();const timer=setInterval(read,1800);return()=>{alive=false;clearInterval(timer);};},[jobId,visible,job?.id,job?.status]);
 const coverageRef=useRef<HTMLDetailsElement>(null);
 const catalogReady=catalog!==null;
 useEffect(()=>{
  if(!visible||!catalogReady)return;
  const reveal=()=>{if(window.location.hash==='#repository-coverage'&&coverageRef.current){coverageRef.current.open=true;coverageRef.current.scrollIntoView?.({block:'start'});}};
  reveal();window.addEventListener('hashchange',reveal);window.addEventListener('popstate',reveal);
  return()=>{window.removeEventListener('hashchange',reveal);window.removeEventListener('popstate',reveal);};
 },[visible,catalogReady]);
 const current=catalog?.programs.find(p=>p.id===selected);
 const qualified=catalog?.programs.filter(p=>p.state==='qualified-receipt').length??0;
 function select(p:Program){setSelected(p.id);setValues(JSON.stringify(p.example,null,2));setFile(null);setError('');request.current=null;}
 async function run(e:FormEvent){
  e.preventDefault();if(!current||busy||readonly||current.state!=='qualified-receipt')return;
  setBusy(true);setError('');
  try{
   const params=JSON.parse(values);if(!Array.isArray(params))throw new Error('Enter a JSON array of parameters.');
   let extension:null|string=null,file_data:null|string=null;
   if(current.extensions.length){
    if(!file||file.size>4*1024*1024||file.size===0)throw new Error('Choose a file of at most 4 MiB.');
    extension='.'+file.name.split('.').pop()?.toLowerCase();if(!current.extensions.includes(extension))throw new Error('Unsupported file type.');
    file_data=await encode(file);
   }
   const body={recipe:current.id,values:params,extension,file_data},key=JSON.stringify(body);
   if(request.current?.body!==key)request.current={body:key,id:newId()};
   const r=await api('programs/jobs','POST',{...body,request_id:request.current.id},50000);
   request.current=null;setJob(null);setJobId(r.id);
   setJob(await api('programs/jobs/'+r.id));await refreshJobs();
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 async function control(action:'cancel'|'retry'){
  if(!job)return;setBusy(true);setError('');
  try{const r=await api('programs/jobs/'+job.id+'/'+action,'POST',{});if(r.id){setJob(null);setJobId(r.id);}else setJob(await api('programs/jobs/'+job.id));await refreshJobs();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <section className="box">
  <header>Independent executable programs <span>{catalog?qualified+' / '+catalog.programs.length+' qualified':'—'}</span><button type="button" onClick={()=>setRefresh(n=>n+1)}>Refresh catalog</button></header>
  {loadError&&<div className="error" role="alert">{loadError} · Check the independent gateway service.</div>}
  {!catalog&&!loadError&&<p role="status">Checking runtime qualification records…</p>}
  {catalog&&<>
   <p className="panel-note">Actual pinned software. Queue execution, inspect progress and recover recorded outputs. Mock research is not live evidence.</p>
   <div className="fields"><label>Category<select value={category} onChange={e=>setCategory(e.target.value)}>{['All','Documents','Finance & analytics','Research','Engineering','Diagnostics'].map(x=><option key={x}>{x}</option>)}</select></label><label>Filter programs<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name, repository or runtime"/></label></div>
   <div className="table-scroll"><table><thead><tr><th>Program</th><th>Runtime</th><th>Qualification</th><th>Action</th></tr></thead><tbody>
   {catalog.programs.filter(p=>(category==='All'||group(p.id,p.mode)===category)&&(p.id+' '+p.repository+' '+p.runtime).toLowerCase().includes(query.toLowerCase())).map(p=><tr key={p.id}><td><b>{title(p.id)}</b><p>{p.id} · {p.repository}</p></td><td>{p.runtime}</td><td>{p.mode==='mock'?'Mock · ':p.mode==='diagnostic'?'Diagnostic · ':''}{p.state==='qualified-receipt'?'Qualified':p.state}</td><td><button disabled={busy} onClick={()=>select(p)} aria-pressed={selected===p.id}>Inspect / run</button></td></tr>)}
   </tbody></table></div>
   {current&&<form className="form" onSubmit={run} key={current.id}>
    <header>{title(current.id)}</header><p>Source: {current.commit} · {current.state}</p>{current.scope&&<p className="panel-note">{current.scope}</p>}
    {current.extensions.length?<label>Document ({current.extensions.join(', ')}, max 4 MiB)<input type="file" required accept={current.extensions.join(',')} disabled={busy||readonly} onChange={e=>setFile(e.target.files?.[0]??null)}/></label>:<ParameterEditor key={current.id} program={current} value={values} onChange={setValues} disabled={busy||readonly}/>}
    <button type="submit" className="primary" disabled={busy||readonly||!!loadError||current.state!=='qualified-receipt'}>{busy?'Submitting…':'Run qualified program'}</button>
    {readonly&&<small>Read-only account.</small>}
   </form>}
   <details ref={coverageRef} data-repository-coverage id={visible?'repository-coverage':undefined}><summary>Repository coverage ({catalog.repositories.length})</summary><p>Source repositories: {catalog.repositories.filter(r=>r.source_present).length}/{catalog.repositories.length} verified · Executable programs: {qualified}/{catalog.programs.length} qualified · Repositories with qualified recipes: {catalog.repositories.filter(r=>catalog.programs.some(p=>p.repository===r.repository&&p.state==='qualified-receipt')).length}/{catalog.repositories.length}</p><p className="panel-note">A verified source checkout or qualified recipe is not proof of full upstream installation. Native plugins, remaining packages and provider-dependent capabilities require separate functional verification.</p><div className="table-scroll"><table><thead><tr><th>Repository</th><th>Source</th><th>Inventory</th><th>Installation coverage</th></tr></thead><tbody>{catalog.repositories.map(r=><tr key={r.repository}><td>{r.repository}</td><td>{r.source_present?'Verified':'Unavailable'}</td><td>{r.file_count===undefined?'—':r.file_count+' files'}{r.inventory_counts&&<p>{['program','hook','manifest','skill','agent-candidate'].map(k=>k+': '+(r.inventory_counts?.[k]??0)).join(' · ')}</p>}</td><td>{catalog.programs.filter(p=>p.repository===r.repository&&p.state==='qualified-receipt').length}/{r.recipes.length} recipes qualified · {r.coverage}<p>{r.family} · {r.installation_state}</p><p>{r.next_action||''}</p>{!!r.entrypoints?.length&&<details><summary>Candidate entry points</summary>{r.entrypoints.map(e=><p key={e.path}>{e.path} · {e.present?'Present':'Verify path'}</p>)}</details>}</td></tr>)}</tbody></table></div></details>
   {catalog.native_profiles&&<details><summary>Native runtime profiles ({catalog.native_profiles.length})</summary><table><thead><tr><th>Profile</th><th>Registration</th><th>Model execution</th></tr></thead><tbody>{catalog.native_profiles.map(r=><tr key={r.profile}><td>{r.profile}</td><td>{r.registration} · {r.route||"—"}{r.checks!=null&&<details><summary>Probe evidence</summary><pre style={{whiteSpace:"pre-wrap"}}>{JSON.stringify(r.checks,null,2)}</pre></details>}</td><td>{r.model_execution}</td></tr>)}</tbody></table><p>Native profiles are isolated; they do not alter production or personal agent settings.</p></details>}
   {catalog.native_execution&&<details><summary>Native model qualification ({catalog.native_execution.length})</summary><p>Model-specific evidence. Each run rechecks source, image, model digest and approved mode. Enable the matching native tool in a project agent. No host files are mounted.</p>{catalog.native_execution.length===0?<p>No model qualification recorded. Review and qualify from the server.</p>:<div className="table-scroll"><table><thead><tr><th>Profile</th><th>Model</th><th>Mode</th><th>Evidence</th></tr></thead><tbody>{catalog.native_execution.map(r=><tr key={r.report_id}><td>{r.profile}</td><td>{r.model}</td><td>{r.mode}</td><td>{r.state}<details><summary>Observed execution</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(r.evidence,null,2)}</pre></details></td></tr>)}</tbody></table></div>}</details>}
   {catalog.packages&&<details><summary>Upstream package runtimes</summary><table><thead><tr><th>Package</th><th>State</th><th>Source</th></tr></thead><tbody>{catalog.packages.map(r=><tr key={r.id}><td>{r.id}</td><td>{r.state}</td><td>{r.repo} · {r.commit.slice(0,12)}</td></tr>)}</tbody></table><p>Installation requires an operator-reviewed package build and offline functional check.</p></details>}
   {catalog.native!=null&&<details><summary>Native runtime evidence</summary><pre style={{whiteSpace:'pre-wrap'}}>{JSON.stringify(catalog.native,null,2)}</pre></details>}
  </>}
  {error&&<div className="error" role="alert">{error}</div>}
  <section className="box"><header>Execution history <span>{jobs.length}</span></header><p className="panel-note">Full results and generated files persist here. Native/provider installations require a separate reviewed qualification; see repository coverage.</p>
   {jobs.length===0?<p>No program jobs recorded for this account.</p>:<div className="table-scroll"><table><thead><tr><th>Program</th><th>Status</th><th>Created</th></tr></thead><tbody>{jobs.map(j=><tr key={j.id}><td><button aria-pressed={jobId===j.id} onClick={()=>{setJob(null);setJobId(j.id);}}>{title(j.recipe)}</button></td><td>{j.status}</td><td>{new Date(j.created_at).toLocaleString()}</td></tr>)}</tbody></table></div>}
   {job&&<section className="box"><header>{title(job.recipe)} · {job.status}</header><p>{job.id}</p>
    {job.error&&<p role="alert">{job.error_code} · {job.error}</p>}
    {active(job.status)&&<p role="status">Job is retained even if you close this screen.</p>}
    {!readonly&&active(job.status)&&<button disabled={busy||job.status==='CANCEL_REQUESTED'} onClick={()=>void control('cancel')}>Cancel job</button>}
    {!readonly&&!job.parent_run&&!job.parent_chat&&!job.connection_id&&['FAILED','CANCELLED'].includes(job.status)&&<button disabled={busy} onClick={()=>void control('retry')}>Retry reviewed version</button>}
    {job.result&&<><p>{job.result.provenance} · Execution {job.result.id}</p><p>Source {job.result.commit} · Image {job.result.image}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'30rem',overflow:'auto'}}>{JSON.stringify(job.result.result,null,2)}</pre></>}
    {job.file_name&&<a href={'/api/v1/programs/jobs/'+encodeURIComponent(job.id)+'/download'}>Download {job.file_name}</a>}
   </section>}
  </section>
 </section>;
}
