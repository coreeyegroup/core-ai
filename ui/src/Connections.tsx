import {useEffect,useState,type FormEvent} from 'react';
import {api,newId} from './api';
import {isTextModel} from './ChatPopover';
import {useSession} from './Session';
import {useResource} from './Workspace';

type Model={name:string;capabilities?:string[]|null};
type Choice={id:string;name:string;archived_at?:string;enabled?:boolean;runtime_mode?:string};
const clients={custom:'API client',platform:'Platform integration',webhook:'Webhook sender',n8n:'n8n'};

type Connection={
 id:string;name:string;client_type:keyof typeof clients;webhook_destination:string|null;project_id:string|null;project:string|null;
 agent_id:string|null;agent:string|null;model:string|null;allowed_models:string[];allow_model_choice:boolean;
 paused:boolean;expires_at:string|null;expired:boolean;scope_available:boolean;revoked_at:string|null;
 last_used_at:string|null;requests_per_minute:number;max_pending:number;timeout_seconds:number;
 max_output_tokens:number;can_discover:boolean;can_submit:boolean;can_read:boolean;
};
type Job={id:string;model:string;status:string;output?:string;error?:string;request_id?:string;duration_seconds?:number;webhook_status?:string};
const pending=new Set(['QUEUED','RUNNING','CANCEL_REQUESTED']);
const dateTime=(date:string|null)=>date ? new Date(date).toLocaleString() : '—';

export default function Connections({tick}:{tick:number}){
 const {role}=useSession();
 return <section className="page settings-page connections-page">
  {role==='ADMIN'?<Manager tick={tick}/>:<>
   <header className="page-head"><div><h1>Connections</h1><p>API access for apps, services, and automation.</p></div></header>
   <div className="notice">An administrator can manage API access.</div>
  </>}
 </section>;
}

function Manager({tick}:{tick:number}){
 const [revision,setRevision]=useState(0),[editing,setEditing]=useState<Connection|null|undefined>();
 const [key,setKey]=useState<{id:string;token:string}|null>(null),[copied,setCopied]=useState(false);
 const [section,setSection]=useState<'Keys'|'API reference'>('Keys');
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
  <header className="page-head"><div><h1>Connections</h1><p>Provide API access to your models and send job events to webhook receivers.</p></div>
   <button className="primary" disabled={busy||!!key} onClick={()=>{setSection('Keys');setEditing(null);}}>New connection</button>
  </header>
  <nav className="project-sections" aria-label="Connection sections">
   {(['Keys','API reference'] as const).map(tab=><button key={tab} aria-current={tab===section?'page':undefined} onClick={()=>setSection(tab)}>{tab==='Keys'?'API keys':tab}</button>)}
  </nav>
  {section==='API reference'?<ApiGuide/>:<>
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
   <header>API keys</header>
   {rows.length>0?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Connection</th><th scope="col">Default model</th><th scope="col">Status</th><th scope="col">Last used</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.id} aria-selected={row.id===selection}>
     <td><button className="link" onClick={()=>{setSelection(row.id);setEditing(undefined);}}>{row.name}</button><small>{clients[row.client_type]} · {row.allowed_models.length} {row.allowed_models.length===1?'model':'models'}</small></td>
     <td>{row.model??'Caller selects'}</td>
     <td>{row.revoked_at?'Revoked':row.paused?'Paused':row.expired?'Expired':row.scope_available?'Enabled':'Context unavailable'}</td>
     <td>{dateTime(row.last_used_at)}</td>
    </tr>)}</tbody>
   </table></div>:<div className="empty">{listError?'Could not load connections.':data?'No API keys yet. Create a connection to authorize a client.':'Loading connections…'}</div>}
  </section>
  {editing!==undefined&&<ConnectionForm key={editing?.id??'new'} existing={editing} tick={tick} busy={busy}
   cancel={()=>setEditing(undefined)} save={body=>editing?change('connections/'+editing.id,'PUT',body):change('connections','POST',body,true)}/>}
  {selected&&editing===undefined&&<section className="box">
   <header>{selected.name}</header>
   <div className="settings-content">
    <p>{[selected.project,selected.agent].filter(Boolean).join(' · ')||'Direct model access'}</p>
    <p>Allowed models · {selected.allowed_models.join(', ')}</p>
    <p>Webhook events · {selected.webhook_destination||'Off'}</p>
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
  </>}
 </>;
}

function ApiGuide(){
 const [active,setActive]=useState<'REST API'|'Webhooks'|'Platform examples'>('REST API');
 const [copied,setCopied]=useState(false);
 const base=window.location.origin+'/api/v1/automation';
 const example=`curl --fail-with-body -X POST '${base}/jobs' \\
  -H "Authorization: Bearer $CORE_AI_API_KEY" \\
  -H 'Content-Type: application/json' \\
  --data '{"request_id":"example-1","prompt":"Summarize these notes."}'`;
 return <section className="box connection-guide" aria-label="API reference">
  <header>API reference</header>
  <div className="settings-content">
   <div className="actions guide-tabs" aria-label="Reference topics">
    {(['REST API','Webhooks','Platform examples'] as const).map(tab=><button key={tab} aria-pressed={tab===active} onClick={()=>setActive(tab)}>{tab}</button>)}
   </div>
   {active==='REST API'&&<>
    <p><b>Base URL</b> <code>{base}</code></p>
    <p>Authenticate server-side with <code>Authorization: Bearer YOUR_KEY</code>. For JSON requests send <code>Content-Type: application/json</code>.</p>
    <div className="table-scroll"><table><thead><tr><th scope="col">Method and path</th><th scope="col">What it does</th></tr></thead><tbody>
     <tr><td><code>GET /models</code></td><td>List the models this key can use and its default.</td></tr>
     <tr><td><code>POST /jobs</code></td><td>Queue a prompt. Send <code>request_id</code>, <code>prompt</code>, and <code>model</code> when the key has no default. HTTP 202 returns the job ID.</td></tr>
     <tr><td><code>GET /jobs/{'{id}'}</code></td><td>Read job status and output using the same connection key. Terminal states are <code>SUCCEEDED</code>, <code>FAILED</code>, and <code>CANCELLED</code>.</td></tr>
    </tbody></table></div>
    <p>Reuse the same request ID and payload on retries. For HTTP 429, use the response’s <code>Retry-After</code> header.</p>
    <div className="actions"><button onClick={async()=>{try{await navigator.clipboard.writeText(example);setCopied(true);}catch{setCopied(false);}}}>{copied?'Copied':'Copy cURL example'}</button></div>
    <pre>{example}</pre>
   </>}
   {active==='Webhooks'&&<>
    <p><b>Inbound</b> A webhook sender that supports Bearer authentication and a configurable JSON body can call <code>POST /jobs</code>. Map its event ID to <code>request_id</code> and the text you want processed to <code>prompt</code>.</p>
    <p><b>Outbound</b> Choose a provisioned destination under <strong>Job completion webhook</strong>. CORE-AI sends signed <code>job.finished</code> events with job metadata. The receiver can fetch the result separately with the connection key.</p>
    <p>Verify <code>X-Core-AI-Signature</code> against the timestamp and raw body. Use the event ID to deduplicate retries. Delivery status appears in Recent activity.</p>
   </>}
   {active==='Platform examples'&&<>
    <p><b>Custom apps and scripts</b> Use the REST endpoints with an HTTP client or cURL. Store the key on the server.</p>
    <p><b>Make, Zapier, and similar platforms</b> Use an HTTP action that can set a Bearer header and send JSON. Save the returned job ID and poll for the result.</p>
    <p><b>n8n</b> Use an HTTP Request node with Header Auth. Configure the same method, URL, headers, and JSON body as the REST example.</p>
   </>}
  </div>
 </section>;
}

function ConnectionForm({existing,tick,busy,save,cancel}:{existing:Connection|null;tick:number;busy:boolean;save:(body:unknown)=>void;cancel:()=>void}){
 const {data:projects,error:projectsError}=useResource('projects',tick);
 const {data:agents,error:agentsError}=useResource('agents',tick);
 const {data:destinations,error:destinationsError}=useResource('connections/webhook-destinations',tick);
 const {data:catalog,error:catalogError}=useResource('models?catalog=true',tick);
 const [allowed,setAllowed]=useState<string[]>(existing?.allowed_models??[]);
 const [model,setModel]=useState(existing?.model??''),[query,setQuery]=useState('');
 const [routing,setRouting]=useState(existing&&!existing.allow_model_choice?'default':'caller');
 const [projectId,setProjectId]=useState(existing?.project_id??''),[agentId,setAgentId]=useState(existing?.agent_id??'');
 const available:Model[]=(catalog?.models??[]).filter(isTextModel);
 const models=[...new Set([...available.map(item=>item.name),...allowed])];
 const [destination,setDestination]=useState(existing?.webhook_destination??'');
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
   timeout_seconds:Number(value('timeout_seconds')),max_output_tokens:Number(value('max_output_tokens')),webhook_destination:destination||null});
 }

 return <section className="box"><header>{existing?'Edit connection':'New connection'}</header>
  <form className="form" onSubmit={submit}>
   <div className="fields">
    <label>Name<input name="name" required maxLength={120} defaultValue={existing?.name}/></label>
    <label>Client<select name="client_type" defaultValue={existing?.client_type??'custom'}>{Object.entries(clients).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
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
   <details open={!!existing?.webhook_destination}>
    <summary>Job completion webhook</summary>
    <label>Destination<select value={destination} onChange={event=>setDestination(event.target.value)}>
     <option value="">Off</option>
     {(destinations??[]).map((name:string)=><option key={name}>{name}</option>)}
     {destination&&!(destinations??[]).includes(destination)&&<option value={destination} disabled>{destination} (unavailable)</option>}
    </select></label>
    {destinationsError?<p className="error" role="alert">{destinationsError}</p>:<p className="panel-note">{destinations?.length?'Send a signed event when a job finishes.':'Ask the server operator to provision a webhook destination.'}</p>}
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
   <div className="actions"><button className="primary" disabled={busy||(!!destination&&!(destinations??[]).includes(destination))||!allowed.length||(routing==='default'&&!model)||(!!existing?.project_id&&!projects)||(!!existing?.agent_id&&!agents)}>{existing?'Save settings':'Create key'}</button><button type="button" onClick={cancel}>Cancel</button></div>
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
    <thead><tr><th scope="col">Request</th><th scope="col">Model</th><th scope="col">Status</th><th scope="col">Duration</th><th scope="col">Webhook</th></tr></thead>
    <tbody>{activity.map((item:Job)=><tr key={item.id}><td>{item.request_id}</td><td>{item.model}</td><td>{item.status}{item.error&&<small> · {item.error}</small>}</td><td>{item.duration_seconds==null?'—':Number(item.duration_seconds).toFixed(1)+' s'}</td><td>{item.webhook_status??'—'}</td></tr>)}</tbody>
   </table></div>:<p className="panel-note">{activity?'No jobs yet.':'Loading activity…'}</p>}
  </details>
 </div>;
}
