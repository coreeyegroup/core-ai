import {useEffect,useState,type FormEvent} from 'react';
import {api,newId} from './api';
import {isTextModel} from './ChatPopover';
import {useSession} from './Session';
import {WorkspaceHead,useResource} from './Workspace';

type Model={name:string;capabilities?:string[]|null};
type Choice={id:string;name:string;archived_at?:string;enabled?:boolean;runtime_mode?:string};
type Connection={
 id:string;name:string;client_type:'n8n'|'custom';project_id:string|null;project:string|null;
 agent_id:string|null;agent:string|null;model:string|null;allowed_models:string[];allow_model_choice:boolean;
 paused:boolean;expires_at:string|null;expired:boolean;scope_available:boolean;revoked_at:string|null;
 last_used_at:string|null;requests_per_minute:number;max_pending:number;timeout_seconds:number;
 max_output_tokens:number;can_discover:boolean;can_submit:boolean;can_read:boolean;
};
type Job={id:string;model:string;status:string;output?:string;error?:string;request_id?:string;duration_seconds?:number};
const pending=new Set(['QUEUED','RUNNING','CANCEL_REQUESTED']);
const dateTime=(date:string|null)=>date ? new Date(date).toLocaleString() : '—';

export default function Connections({tick}:{tick:number}){
 const {role}=useSession();
 return <section className="page settings-page">
  <WorkspaceHead title="Connections" description="Give n8n and other services controlled access to your local models."/>
  {role==='ADMIN'?<Manager tick={tick}/>:<div className="notice">An administrator can manage connection keys.</div>}
 </section>;
}

function Manager({tick}:{tick:number}){
 const [revision,setRevision]=useState(0),[editing,setEditing]=useState<Connection|null|undefined>();
 const [key,setKey]=useState<{id:string;token:string}|null>(null),[copied,setCopied]=useState(false);
 const [selection,setSelection]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const {data,error:listError}=useResource('connections',tick+revision);
 const rows:Connection[]=data??[];
 const selected=rows.find(row=>row.id===selection);
 const reload=()=>setRevision(value=>value+1);

 async function change(path:string,method:string,body?:unknown,showKey=false){
  setBusy(true);setError('');
  try {
   const result=await api(path,method,body);
   if(showKey){setCopied(false);setKey(result);}
   if(method==='POST'&&path==='connections')setSelection(result.id);
   setEditing(undefined);reload();
  } catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 return <>
  {(error||listError)&&<div className="error" role="alert">{error||listError}</div>}
  {key&&<section className="box" aria-label="New connection key">
   <header>New connection key</header>
   <div className="settings-content">
    <p role="status">Save this key in your service’s credentials. It is shown once.</p>
    <label className="connection-key">Connection key<input readOnly value={key.token} onFocus={e=>e.currentTarget.select()}/></label>
    <div className="actions">
     <button onClick={async()=>{try{await navigator.clipboard.writeText(key.token);setCopied(true);}catch{setError('Select and copy the key manually.');}}}>{copied?'Copied':'Copy key'}</button>
     <button onClick={()=>setKey(null)}>Done</button>
    </div>
   </div>
  </section>}
  <section className="box">
   <header>Connections <button className="primary" disabled={busy||!!key} onClick={()=>setEditing(null)}>New connection</button></header>
   {rows.length>0?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Connection</th><th scope="col">Default model</th><th scope="col">Status</th><th scope="col">Last used</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.id} aria-selected={row.id===selection}>
     <td><button className="link" onClick={()=>{setSelection(row.id);setEditing(undefined);}}>{row.name}</button><small>{row.client_type==='n8n'?'n8n':'Custom API'} · {row.allowed_models.length} {row.allowed_models.length===1?'model':'models'}</small></td>
     <td>{row.model??'Caller selects'}</td>
     <td>{row.revoked_at?'Revoked':row.paused?'Paused':row.expired?'Expired':row.scope_available?'Enabled':'Context unavailable'}</td>
     <td>{dateTime(row.last_used_at)}</td>
    </tr>)}</tbody>
   </table></div>:<div className="empty">{listError?'Could not load connections.':data?'No connections yet.':'Loading connections…'}</div>}
  </section>
  {editing!==undefined&&<ConnectionForm key={editing?.id??'new'} existing={editing} tick={tick} busy={busy}
   cancel={()=>setEditing(undefined)} save={body=>editing?change('connections/'+editing.id,'PUT',body):change('connections','POST',body,true)}/>}
  {selected&&editing===undefined&&<section className="box">
   <header>{selected.name}</header>
   <div className="settings-content">
    <p>{[selected.project,selected.agent].filter(Boolean).join(' · ')||'Direct model access'}</p>
    <p>Allowed models · {selected.allowed_models.join(', ')}</p>
    <p>Key expires · {selected.expires_at?dateTime(selected.expires_at):'No expiry'}</p>
    {!selected.revoked_at&&<div className="actions">
     <button disabled={busy} onClick={()=>setEditing(selected)}>Edit settings</button>
     <button disabled={busy} onClick={()=>void change('connections/'+selected.id+'/pause','PUT',{paused:!selected.paused})}>{selected.paused?'Resume':'Pause'}</button>
     <button disabled={busy||!!key} onClick={()=>{if(confirm('Rotate this key? Clients must switch to the new key.'))void change('connections/'+selected.id+'/rotate','POST',undefined,true);}}>Rotate key</button>
     <button disabled={busy} onClick={()=>{if(confirm('Revoke this key? Requests using it will be rejected.'))void change('connections/'+selected.id+'/revoke','POST');}}>Revoke</button>
    </div>}
   </div>
   <ConnectionActivity key={selected.id} connection={selected} tick={tick+revision}/>
  </section>}
  <details className="box connection-guide">
   <summary>API and n8n setup</summary>
   <p>Use the HTTP Request node with Header Auth and set <code>Authorization: Bearer YOUR_KEY</code>.</p>
   <p>GET <code>{window.location.origin}/api/v1/automation/models</code> to discover allowed choices and the default.</p>
   <p>POST <code>{window.location.origin}/api/v1/automation/jobs</code> with <code>{'{"request_id":"example-1","prompt":"Summarize these notes","model":"qwen3:4b"}'}</code>. Omit <code>model</code> when the connection has a default. Reuse the request ID when retrying.</p>
   <p>GET <code>/api/v1/automation/jobs/{'{id}'}</code> with the same key. Read <code>output</code> when the status is <code>SUCCEEDED</code>.</p>
  </details>
 </>;
}

function ConnectionForm({existing,tick,busy,save,cancel}:{existing:Connection|null;tick:number;busy:boolean;save:(body:unknown)=>void;cancel:()=>void}){
 const {data:projects,error:projectsError}=useResource('projects',tick);
 const {data:agents,error:agentsError}=useResource('agents',tick);
 const {data:catalog,error:catalogError}=useResource('models?catalog=true',tick);
 const [allowed,setAllowed]=useState<string[]>(existing?.allowed_models??[]);
 const [model,setModel]=useState(existing?.model??''),[query,setQuery]=useState('');
 const [routing,setRouting]=useState(existing&&!existing.allow_model_choice?'default':'caller');
 const [projectId,setProjectId]=useState(existing?.project_id??''),[agentId,setAgentId]=useState(existing?.agent_id??'');
 const available:Model[]=(catalog?.models??[]).filter(isTextModel);
 const models=[...new Set([...available.map(item=>item.name),...allowed])];
 const contextError=projectsError||agentsError;
 const expiry=existing?.expires_at?new Date(new Date(existing.expires_at).getTime()-new Date(existing.expires_at).getTimezoneOffset()*60000).toISOString().slice(0,16):'';

 function toggle(name:string){
  const next=allowed.includes(name)?allowed.filter(current=>current!==name):[...allowed,name];
  setAllowed(next);
  if(model&&!next.includes(model))setModel(routing==='default'?(next[0]??''):'');
 }
 function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const fields=new FormData(event.currentTarget), value=(name:string)=>String(fields.get(name)??'');
  save({name:value('name'),client_type:value('client_type'),model:model||null,allowed_models:allowed,
   allow_model_choice:routing==='caller',project_id:projectId||null,agent_id:agentId||null,
   expires_at:value('expires_at')?new Date(value('expires_at')).toISOString():null,
   can_discover:fields.has('can_discover'),can_submit:fields.has('can_submit'),can_read:fields.has('can_read'),
   requests_per_minute:Number(value('requests_per_minute')),max_pending:Number(value('max_pending')),
   timeout_seconds:Number(value('timeout_seconds')),max_output_tokens:Number(value('max_output_tokens'))});
 }

 return <section className="box"><header>{existing?'Edit connection':'New connection'}</header>
  <form className="form" onSubmit={submit}>
   <div className="fields">
    <label>Name<input name="name" required maxLength={120} defaultValue={existing?.name}/></label>
    <label>Client<select name="client_type" defaultValue={existing?.client_type??'custom'}><option value="custom">Custom API</option><option value="n8n">n8n</option></select></label>
   </div>
   <fieldset className="tool-permissions">
    <legend>Allowed models</legend>
    <input aria-label="Search allowed models" placeholder="Search models…" value={query} onChange={event=>setQuery(event.target.value)}/>
    <div className="connection-models">{models.filter(name=>name.toLowerCase().includes(query.toLowerCase())).map(name=>{
     const entry=available.find(item=>item.name===name);
     return <label key={name} className="checkbox-label"><input type="checkbox" checked={allowed.includes(name)} disabled={!allowed.includes(name)&&allowed.length>=32} onChange={()=>toggle(name)}/>
      {name}<small>{entry?entry.capabilities?.join(', ')||'Available':'Unavailable'}</small>
     </label>;
    })}</div>
    {!models.length&&<p className="panel-note">{catalog?'Start Ollama and refresh the workspace to select models.':catalogError||'Loading models…'}</p>}
   </fieldset>
   <div className="fields">
    <label>Default model<select value={model} required={routing==='default'} onChange={event=>setModel(event.target.value)}><option value="">{routing==='caller'?'Caller must specify a model':'Select a model'}</option>{allowed.map(name=><option key={name}>{name}</option>)}</select></label>
    <label>Model choice<select name="routing" value={routing} onChange={event=>{setRouting(event.target.value);if(event.target.value==='default'&&!model)setModel(allowed[0]??'');}}><option value="caller">Caller can choose</option><option value="default">Always use the default</option></select></label>
   </div>
   <details open={!!existing?.project_id||!!existing?.agent_id}>
    <summary>Optional project and agent context</summary>
    <p className="panel-note">A project grants this connection access to its instructions and matching sources.</p>
    <div className="fields">
     <label>Project<select name="project_id" value={projectId} onChange={event=>setProjectId(event.target.value)}><option value="">No project</option>{(projects??[]).filter((item:Choice)=>!item.archived_at||item.id===existing?.project_id).map((item:Choice)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
     <label>Agent<select name="agent_id" value={agentId} onChange={event=>setAgentId(event.target.value)}><option value="">No agent</option>{(agents??[]).filter((item:Choice)=>(item.enabled&&item.runtime_mode==='analysis')||item.id===existing?.agent_id).map((item:Choice)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    </div>
    {contextError&&<p className="error" role="alert">{contextError}</p>}
   </details>
   <details>
    <summary>Permissions, limits, and expiry</summary>
    <div className="fields">
     <label className="checkbox-label"><input type="checkbox" name="can_discover" defaultChecked={existing?.can_discover??true}/>Discover models</label>
     <label className="checkbox-label"><input type="checkbox" name="can_submit" defaultChecked={existing?.can_submit??true}/>Submit jobs</label>
     <label className="checkbox-label"><input type="checkbox" name="can_read" defaultChecked={existing?.can_read??true}/>Read results</label>
    </div>
    <div className="fields">
     <label>Key expiry<input name="expires_at" type="datetime-local" defaultValue={expiry}/></label>
     <label>Requests per minute<input type="number" name="requests_per_minute" min={1} max={600} required defaultValue={existing?.requests_per_minute??30}/></label>
     <label>Pending jobs<input type="number" name="max_pending" min={1} max={20} required defaultValue={existing?.max_pending??20}/></label>
     <label>Generation timeout (seconds)<input type="number" name="timeout_seconds" min={15} max={300} required defaultValue={existing?.timeout_seconds??300}/></label>
     <label>Maximum output tokens<input type="number" name="max_output_tokens" min={128} max={4096} required defaultValue={existing?.max_output_tokens??2048}/></label>
    </div>
   </details>
   <div className="actions"><button className="primary" disabled={busy||!allowed.length||(routing==='default'&&!model)||(!!existing?.project_id&&!projects)||(!!existing?.agent_id&&!agents)}>{existing?'Save settings':'Create key'}</button><button type="button" onClick={cancel}>Cancel</button></div>
  </form>
 </section>;
}

function ConnectionActivity({connection,tick}:{connection:Connection;tick:number}){
 const [job,setJob]=useState<Job|null>(null),[model,setModel]=useState(''),[error,setError]=useState('');
 const [busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const {data:activity,error:activityError}=useResource('connections/'+connection.id+'/activity',tick+revision);
 const active=!!job&&pending.has(job.status);
 const selectedModel=connection.allow_model_choice&&connection.allowed_models.includes(model)?model:connection.model??connection.allowed_models[0];
 useEffect(()=>{
  if(!job||!active)return;
  const timeout=window.setTimeout(async()=>{
   try{
    const next=await api('connections/'+connection.id+'/jobs/'+job.id);
    setJob(next);
    setRevision(previous=>previous+1);
   }catch(e){setError((e as Error).message);setJob(null);}
  },1500);
  return()=>window.clearTimeout(timeout);
 },[connection.id,job,active]);

 async function test(){
  setBusy(true);setError('');setJob(null);
  try{
   const response=await api('connections/'+connection.id+'/test','POST',{request_id:newId(),prompt:'Reply with CORE-AI connection OK.',model:selectedModel});
   setJob({...response,model:selectedModel,status:'QUEUED'});
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 return <div className="settings-content">
  <div className="actions">
   <label>Test model<select value={selectedModel} onChange={event=>setModel(event.target.value)}>
    {(connection.allow_model_choice?connection.allowed_models:[selectedModel]).map(name=><option key={name}>{name}</option>)}
   </select></label>
   <button disabled={busy||active||connection.paused||connection.expired||!!connection.revoked_at||!connection.can_submit||!connection.scope_available} onClick={()=>void test()}>Test connection</button>
  </div>
  {(error||activityError)&&<div className="error" role="alert">{error||activityError}</div>}
  {job&&<div role="status"><p>{job.model} · {job.status}</p>{(job.output||job.error)&&<pre>{job.output||job.error}</pre>}</div>}
  <details>
   <summary>Recent activity</summary>
   <button onClick={()=>setRevision(value=>value+1)}>Refresh activity</button>
   {activity?.length?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Request</th><th scope="col">Model</th><th scope="col">Status</th><th scope="col">Duration</th></tr></thead>
    <tbody>{activity.map((item:Job)=><tr key={item.id}><td>{item.request_id}</td><td>{item.model}</td><td>{item.status}{item.error&&<small> · {item.error}</small>}</td><td>{item.duration_seconds==null?'—':Number(item.duration_seconds).toFixed(1)+' s'}</td></tr>)}</tbody>
   </table></div>:<p className="panel-note">{activity?'No jobs yet.':'Loading activity…'}</p>}
  </details>
 </div>;
}
