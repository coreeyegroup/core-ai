import {useEffect,useRef,useState,type FormEvent} from 'react';
import {ArrowLeft,ChevronDown,Ellipsis,Plus,Search} from 'lucide-react';
import {api,newId} from './api';
import {ChatPopover,isTextModel} from './ChatPopover';
import {useSession} from './Session';
import {useResource} from './Workspace';

type Operation='generation'|'embedding';
function isEmbeddingModel(model:Model){
 return Array.isArray(model.capabilities)?model.capabilities.includes('embedding'):/embed|bge-m3/i.test(model.name);
}
type Model={name:string;capabilities?:string[]|null};
type Choice={id:string;name:string;archived_at?:string;enabled?:boolean;runtime_mode?:string};
const clients={custom:'API client',platform:'Platform integration',webhook:'Webhook sender',n8n:'n8n'};

const policyFields=[
 ['requests_per_minute','Requests per minute',1,600],
 ['max_pending','Pending jobs',1,20],
 ['timeout_seconds','Timeout (seconds)',15,300],
 ['max_output_tokens','Output tokens',128,4096],
 ['context_tokens','Context tokens',1024,32768],
] as const;
type PolicyLimit=typeof policyFields[number][0];
type ModelPolicy={enabled?:boolean}&Partial<Record<PolicyLimit,number>>;
type Usage={model:string;requests:number;recent_requests:number;pending:number;succeeded:number;failed:number;cancelled:number;measured_input_tokens:number;measured_output_tokens:number};
type Connection={
 id:string;name:string;client_type:keyof typeof clients;webhook_destination:string|null;project_id:string|null;project:string|null;
 agent_id:string|null;agent:string|null;model:string|null;allowed_models:string[];allow_model_choice:boolean;
 model_access:'selected'|'all';model_policies:Record<string,ModelPolicy>;can_cancel:boolean;
 paused:boolean;overlap_until?:string|null;expires_at:string|null;expired:boolean;scope_available:boolean;revoked_at:string|null;
 last_used_at:string|null;requests_per_minute:number;max_pending:number;timeout_seconds:number;
 max_output_tokens:number;context_tokens:number;can_reveal:boolean;can_discover:boolean;can_submit:boolean;can_read:boolean;can_embed:boolean;
};
type Job={id:string;model:string;status:string;operation?:Operation;output?:string;embeddings?:number[][];error?:string;request_id?:string;duration_seconds?:number;webhook_status?:string};
const pending=new Set(['QUEUED','RUNNING','CANCEL_REQUESTED']);
const dateTime=(date:string|null)=>date ? new Date(date).toLocaleString() : '—';

function ConnectionStatus({connection}:{connection:Connection}){
 const status=connection.revoked_at?'Revoked':connection.paused?'Paused':connection.expired?'Expired':connection.scope_available?'Enabled':'Context unavailable';
 return <span className="connection-status" data-status={status}><i aria-hidden="true"/>{status}</span>;
}

export default function Connections({tick,visible=true}:{tick:number;visible?:boolean}){
 const {role}=useSession();
 return <section className="page settings-page connections-page">
  {role==='ADMIN'?<Manager tick={tick} visible={visible}/>:<>
   <header className="page-head"><div><h1>Connections</h1><p>API access for apps, services, and automation.</p></div></header>
   <div className="notice">An administrator can manage API access.</div>
  </>}
 </section>;
}

function Manager({tick,visible}:{tick:number;visible:boolean}){
 const [revision,setRevision]=useState(0),[editing,setEditing]=useState<Connection|null|undefined>();
 const [key,setKey]=useState<{id:string;token:string}|null>(null),[copied,setCopied]=useState(false);
 const [keyAction,setKeyAction]=useState<{type:'reveal'|'rotate';connection:Connection}|null>(null);
 const [section,setSection]=useState<'Keys'|'API reference'>('Keys');
 const [selection,setSelection]=useState<string|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');
 const {data,error:listError}=useResource('connections',tick+revision);
 const {data:storage}=useResource('connections/key-storage',tick);
 const storageAvailable=storage?.available===true;
 const rows:Connection[]=data??[];
 const selected=rows.find(row=>row.id===selection);
 const reload=()=>setRevision(value=>value+1);
 const keyPanel=useRef<HTMLHeadingElement>(null);
 const active=useRef(visible);
 active.current=visible;
 useEffect(()=>{if(!visible){setKey(null);setKeyAction(null);}},[visible]);
 useEffect(()=>{
  if(!key)return;
  keyPanel.current?.focus();
  const timeout=window.setTimeout(()=>setKey(null),60_000);
  return()=>window.clearTimeout(timeout);
 },[key]);

 function edit(connection:Connection){
  setError('');setKey(null);setSelection(connection.id);setEditing(connection);
 }

 async function manageKey(body:unknown){
  if(!keyAction)return;
  const {connection,type}=keyAction;
  const result=await api('connections/'+connection.id+'/'+type,'POST',body);
  if(active.current){setKey(result);setCopied(false);setSelection(connection.id);setKeyAction(null);}
  reload();
 }

 async function change(path:string,method:string,body?:unknown,showKey=false){
  setBusy(true);setError('');
  try {
   const result=await api(path,method,body);
   if(showKey&&active.current){setCopied(false);setKey(result);}
   if(method==='POST'&&path==='connections')setSelection(result.id);
   setEditing(undefined);reload();
  } catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 if(editing!==undefined)return <>
  <button className="link connection-back" disabled={busy} onClick={()=>{setEditing(undefined);setError('');}}><ArrowLeft size={16}/>API keys</button>
  <header className="page-head"><div><h1>{editing?'Edit connection':'New connection'}</h1><p>{editing?editing.name:'Set model access for an app, service, or automation.'}</p></div></header>
  {error&&<div className="error" role="alert">{error}</div>}
  <ConnectionForm storageAvailable={storageAvailable} key={editing?.id??'new'} existing={editing} tick={tick} busy={busy}
   cancel={()=>{setEditing(undefined);setError('');}} save={body=>editing?change('connections/'+editing.id,'PUT',body):change('connections','POST',body,true)}/>
 </>;

 return <>
  <header className="page-head"><div><h1>Connections</h1><p>Manage access to your models and webhook delivery.</p></div>
   <button className="primary" disabled={busy||!!key} onClick={()=>{setSection('Keys');setError('');setEditing(null);}}><Plus size={16}/>New connection</button>
  </header>
  <nav className="project-sections" aria-label="Connection sections">
   {(['Keys','API reference'] as const).map(tab=><button key={tab} aria-current={tab===section?'page':undefined} onClick={()=>{setSection(tab);setKey(null);setKeyAction(null);}}>{tab==='Keys'?'API keys':tab}</button>)}
  </nav>
  {section==='API reference'?<ApiGuide/>:<>
  {(error||listError)&&<div className="error" role="alert">{error||listError}</div>}
  {keyAction&&<KeyActionDialog action={keyAction} storageAvailable={storageAvailable} close={()=>setKeyAction(null)}
   submit={manageKey} rotate={()=>setKeyAction({...keyAction,type:'rotate'})}/>}
  {key&&visible&&<section className="box" aria-label="Connection key">
   <header><h2 tabIndex={-1} ref={keyPanel}>Connection key</h2></header>
   <div className="settings-content">
    <p role="status">Store this key in your service’s credentials. This view closes after one minute.</p>
    <label className="connection-key">Connection key<input readOnly value={key.token} onFocus={e=>e.currentTarget.select()}/></label>
    <div className="actions">
     <button onClick={async()=>{try{await navigator.clipboard.writeText(key.token);setCopied(true);}catch{setError('Select and copy the key manually.');}}}>{copied?'Copied':'Copy key'}</button>
     <button onClick={()=>setKey(null)}>Hide key</button>
    </div>
   </div>
  </section>}
  <section className="box connection-list" aria-label="API keys">
   {rows.length>0?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Connection</th><th scope="col">Default model</th><th scope="col">Status</th><th scope="col">Last used</th><th scope="col">Actions</th></tr></thead>
    <tbody>{rows.map(row=><tr key={row.id} aria-selected={row.id===selection}>
     <td><button className="link connection-name" aria-current={row.id===selection?'true':undefined} onClick={()=>{setSelection(row.id);setEditing(undefined);}}>{row.name}</button><small>{clients[row.client_type]} · {row.model_access==='all'?'All supported models':row.allowed_models.length+' selected'}</small></td>
     <td>{row.model??'Caller selects'}</td>
     <td><ConnectionStatus connection={row}/></td>
     <td>{dateTime(row.last_used_at)}</td>
     <td>{!row.revoked_at&&<div className="actions connection-row-actions">
      <button disabled={busy} aria-label={'View key for '+row.name} onClick={()=>{setKey(null);setKeyAction({type:'reveal',connection:row});}}>View key</button>
      <button disabled={busy} aria-label={'Edit '+row.name} onClick={()=>edit(row)}>Edit</button>
     </div>}</td>
    </tr>)}</tbody>
   </table></div>:<div className="empty">{listError?'Could not load connections.':data?'No API keys yet. Create a connection to authorize a client.':'Loading connections…'}</div>}
  </section>
  {selected&&<section className="box connection-details">
   <header>
    <div><h2>{selected.name}</h2><ConnectionStatus connection={selected}/></div>
    {!selected.revoked_at&&<div className="actions">
     <button disabled={busy} onClick={()=>edit(selected)}>Edit settings</button>
     <ChatPopover label="Key actions" kind="menu" align="end" buttonClass="project-menu-trigger" trigger={<Ellipsis size={18}/>}>
      {dismiss=><>
       <button role="menuitem" disabled={busy} onClick={()=>{dismiss();void change('connections/'+selected.id+'/pause','PUT',{paused:!selected.paused});}}>{selected.paused?'Resume':'Pause'}</button>
       <button role="menuitem" disabled={busy||!!key} onClick={()=>{dismiss();setKeyAction({type:'rotate',connection:selected});}}>Rotate key</button>
       {selected.overlap_until&&<button role="menuitem" disabled={busy} onClick={()=>{dismiss();if(confirm('End the rotation grace period now?'))void change('connections/'+selected.id+'/end-overlap','POST');}}>End rotation overlap</button>}
       <button role="menuitem" className="chat-menu-danger" disabled={busy} onClick={()=>{dismiss();if(confirm('Revoke this key? Requests using it will be rejected.'))void change('connections/'+selected.id+'/revoke','POST');}}>Revoke key</button>
      </>}
     </ChatPopover>
    </div>}
   </header>
   <dl className="connection-summary">
    <div><dt>Context</dt><dd>{[selected.project,selected.agent].filter(Boolean).join(' · ')||'Direct model access'}</dd></div>
    <div><dt>Default model</dt><dd>{selected.model??'Caller selects'}</dd></div>
    <div><dt>Allowed models</dt><dd>{selected.model_access==='all'?'All supported installed models':selected.allowed_models.join(', ')}</dd></div>
    <div><dt>Webhook</dt><dd>{selected.webhook_destination||'Off'}</dd></div>
    <div><dt>Key expiry</dt><dd>{selected.expires_at?dateTime(selected.expires_at):'No expiry'}</dd></div>
    {selected.overlap_until&&<div><dt>Previous key accepted until</dt><dd>{dateTime(selected.overlap_until)}</dd></div>}
    <div><dt>Last used</dt><dd>{dateTime(selected.last_used_at)}</dd></div>
   </dl>
   <ConnectionActivity key={selected.id} connection={selected} tick={tick+revision}/>
  </section>}
  </>}
 </>;
}

function KeyActionDialog({action,storageAvailable,submit,close,rotate}:{
 action:{type:'reveal'|'rotate';connection:Connection};storageAvailable:boolean;
 submit:(body:unknown)=>Promise<void>;close:()=>void;rotate:()=>void;
}){
 const dialog=useRef<HTMLDialogElement>(null);
 const [error,setError]=useState(''),[working,setWorking]=useState(false);
 const {type,connection}=action;
 useEffect(()=>{
  const node=dialog.current;
  node?.showModal?.();
  if(node&&!node.open)node.setAttribute('open','');
  return()=>node?.close?.();
 },[]);
 async function confirmAction(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setWorking(true);setError('');
  const form=event.currentTarget, fields=new FormData(form);
  const payload=type==='reveal'?{password:fields.get('password')}:{save_for_reveal:fields.has('save_for_reveal'),overlap_minutes:Number(fields.get('overlap_minutes')??0)};
  form.reset();
  try{await submit(payload);}
  catch(e){setError((e as Error).message);}
  finally{setWorking(false);}
 }
 return <dialog className="connection-key-dialog" ref={dialog} aria-label={type==='reveal'?'View API key':'Rotate API key'}
  onCancel={event=>{event.preventDefault();if(!working)close();}}>
  <h2>{type==='reveal'?'View API key':'Rotate API key'}</h2>
  <p>{connection.name}</p>
  {type==='reveal'&&!connection.can_reveal?<div>
   <p>This key was issued without a recoverable copy. Rotation can enable encrypted recovery.</p>
   <div className="actions">{storageAvailable&&<button onClick={rotate}>Rotate with recovery</button>}<button onClick={close}>Close</button></div>
  </div>:<form key={type} onSubmit={confirmAction}>
   {type==='reveal'?<label>Administrator password<input name="password" type="password" autoComplete="current-password" required maxLength={256} autoFocus/></label>:<>
    <p>Replace this key and update every client that uses it.</p>
    <label>Previous key grace period<select name="overlap_minutes">
     <option value="0">Expire immediately</option><option value="15">15 minutes</option><option value="60">1 hour</option><option value="1440">24 hours</option>
    </select></label>
    <label className="checkbox-label"><input type="checkbox" name="save_for_reveal" disabled={!storageAvailable} defaultChecked={storageAvailable}/>Save encrypted copy for later reveal</label>
   </>}
   {error&&<p className="error" role="alert">{error}</p>}
   <div className="actions">
    <button className="primary" disabled={working}>{type==='reveal'?'Reveal key':'Rotate key'}</button><button type="button" disabled={working} onClick={close}>Cancel</button>
   </div>
  </form>}
 </dialog>;
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
     <tr><td><code>POST /embeddings</code></td><td>Queue a text embedding using <code>request_id</code>, <code>input</code>, and a compatible <code>model</code>. The key needs embedding permission.</td></tr>
     <tr><td><code>GET /jobs/{'{id}'}</code></td><td>Read job status and output using the same connection key. Terminal states are <code>SUCCEEDED</code>, <code>FAILED</code>, and <code>CANCELLED</code>.</td></tr>
     <tr><td><code>POST /jobs/{'{id}'}/cancel</code></td><td>Cancel a queued or running job if the key has cancellation permission.</td></tr>
     <tr><td><code>POST /jobs/{'{id}'}/retry</code></td><td>Retry a failed or cancelled job using current settings and a new request ID.</td></tr>
     <tr><td><code>GET /model-policies</code></td><td>Discover the effective limits for models this key can use.</td></tr>
     <tr><td><code>GET /usage</code></td><td>Read 30-day per-model job counts and provider-reported tokens with result access.</td></tr>
    </tbody></table></div>
    <p>All-model access follows the installed catalog. Add <code>?operation=embedding</code> to model discovery to find permitted embedding models. Per-model limits can tighten the key limits.</p>
    <p>Reuse the same request ID and payload on retries. For HTTP 429, use the response’s <code>Retry-After</code> header.</p>
    <p><a href={base+'/openapi.json'} target="_blank" rel="noreferrer">OpenAPI schema</a></p>
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

function ConnectionForm({existing,tick,busy,save,cancel,storageAvailable}:{storageAvailable:boolean;existing:Connection|null;tick:number;busy:boolean;save:(body:unknown)=>void;cancel:()=>void}){
 const {data:projects,error:projectsError}=useResource('projects',tick);
 const {data:agents,error:agentsError}=useResource('agents',tick);
 const {data:destinations,error:destinationsError}=useResource('connections/webhook-destinations',tick);
 const {data:catalog,error:catalogError}=useResource('models?catalog=true',tick);
 const [modelAccess,setModelAccess]=useState(existing?.model_access??'selected');
 const [policies,setPolicies]=useState<Record<string,ModelPolicy>>(existing?.model_policies??{});
 const [policyName,setPolicyName]=useState('');
 const [allowed,setAllowed]=useState<string[]>(existing?.allowed_models??[]);
 const [model,setModel]=useState(existing?.model??''),[query,setQuery]=useState(''),[selectedOnly,setSelectedOnly]=useState(false);
 const [routing,setRouting]=useState(existing&&!existing.allow_model_choice?'default':'caller');
 const [projectId,setProjectId]=useState(existing?.project_id??''),[agentId,setAgentId]=useState(existing?.agent_id??'');
 const available:Model[]=(catalog?.models??[]).filter((entry:Model)=>isTextModel(entry)||isEmbeddingModel(entry));
 const models=[...new Set([...available.map(item=>item.name),...allowed,...Object.keys(policies),...(existing?.model?[existing.model]:[])])];
 const all=modelAccess==='all';
 const defaultChoices=(all?models:allowed).filter(name=>policies[name]?.enabled!==false);
 const policy=Object.hasOwn(policies,policyName)?policies[policyName]:{};
 const [destination,setDestination]=useState(existing?.webhook_destination??'');
 const visibleModels=models.filter(name=>name.toLowerCase().includes(query.trim().toLowerCase())&&(!selectedOnly||(all?policies[name]?.enabled===false:allowed.includes(name))));
 const contextError=projectsError||agentsError;
 const expiry=existing?.expires_at?new Date(new Date(existing.expires_at).getTime()-new Date(existing.expires_at).getTimezoneOffset()*60000).toISOString().slice(0,16):'';

 function changePolicy(name:string, patch:ModelPolicy){
  const current=Object.hasOwn(policies,name)?policies[name]:{};
  setPolicies({...policies,[name]:{...current,...patch}});
  if(patch.enabled===false&&name===model)setModel('');
 }
 function toggle(name:string){
  if(all){changePolicy(name,{enabled:policies[name]?.enabled===false});return;}
  const next=allowed.includes(name)?allowed.filter(current=>current!==name):[...allowed,name];
  setAllowed(next);
  if(model&&!next.includes(model))setModel(routing==='default'?(next[0]??''):'');
 }
 function submit(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  const fields=new FormData(event.currentTarget), value=(name:string)=>String(fields.get(name)??'');
  save({name:value('name'),client_type:value('client_type'),model:model||null,allowed_models:allowed,model_access:modelAccess,
   model_policies:Object.fromEntries(Object.entries(policies).filter(([,policy])=>policy.enabled===false||policyFields.some(([field])=>policy[field]!=null))),
   allow_model_choice:routing==='caller',project_id:projectId||null,agent_id:agentId||null,
   expires_at:value('expires_at')?new Date(value('expires_at')).toISOString():null,
   can_discover:fields.has('can_discover'),can_submit:fields.has('can_submit'),can_read:fields.has('can_read'),can_embed:fields.has('can_embed'),can_cancel:fields.has('can_cancel'),
   requests_per_minute:Number(value('requests_per_minute')),max_pending:Number(value('max_pending')),
   timeout_seconds:Number(value('timeout_seconds')),max_output_tokens:Number(value('max_output_tokens')),context_tokens:Number(value('context_tokens')),webhook_destination:destination||null,...(!existing?{save_for_reveal:fields.has('save_for_reveal')}: {})});
 }

 return <form className="connection-editor" onSubmit={submit}>
   <section className="box">
   <header>Connection details</header>
   <div className="form fields">
    <label>Name<input name="name" required maxLength={120} defaultValue={existing?.name} autoFocus/></label>
    <label>Client<select name="client_type" defaultValue={existing?.client_type??'custom'}>{Object.entries(clients).map(([value,label])=><option key={value} value={value}>{label}</option>)}</select></label>
   </div>
   </section>
   <section className="box">
    <header>Model access <span className="muted">{all?'Dynamic catalog':allowed.length+' selected'}</span></header>
    <div className="form">
    <label>Model access<select value={modelAccess} onChange={event=>{
     const scope=event.target.value as Connection['model_access'];
     setModelAccess(scope);
     setSelectedOnly(false);
     if(scope==='selected'&&!allowed.includes(model))setModel('');
    }}><option value="selected">Selected models</option><option value="all">All supported installed models</option></select></label>
    {all&&<p className="panel-note">New supported models are available to this key as they are installed. Clear a checkbox to block that model.</p>}
    <fieldset className="connection-model-picker">
    <legend className="sr-only">Allowed models</legend>
    <div className="connection-picker-toolbar">
     <label className="project-search"><Search size={15} aria-hidden="true"/><input type="search" aria-label="Search allowed models" placeholder="Search models" value={query} onChange={event=>setQuery(event.target.value)}/></label>
     <button type="button" aria-pressed={selectedOnly} onClick={()=>setSelectedOnly(value=>!value)}>{selectedOnly?'Show all':all?'Blocked only':'Selected only'}</button>
    </div>
    <div className="connection-models">{visibleModels.map(name=>{
     const entry=available.find(item=>item.name===name);
     const checked=all?policies[name]?.enabled!==false:allowed.includes(name);
     return <label key={name} className="connection-model" data-selected={checked}>
      <input type="checkbox" aria-label={name} checked={checked} disabled={!all&&!checked&&allowed.length>=32} onChange={()=>toggle(name)}/>
      <span><strong>{name}</strong><small>{entry?policies[name]?.enabled===false?'Blocked by policy':entry.capabilities?.join(' · ')||'Available':'Unavailable'}</small></span>
     </label>;
    })}</div>
    {!visibleModels.length&&<p className="panel-note">{models.length?(selectedOnly&&!allowed.length?'Select models to see them here.':'No matching models.'):catalog?'Start Ollama and refresh the workspace to select models.':catalogError||'Loading models…'}</p>}
    </fieldset>
   <div className="fields">
    <label>Default model<select value={model} required={routing==='default'} onChange={event=>setModel(event.target.value)}><option value="">{routing==='caller'?'Caller must specify a model':'Select a model'}</option>{defaultChoices.map(name=><option key={name}>{name}</option>)}</select></label>
    <label>Model choice<select name="routing" value={routing} onChange={event=>{setRouting(event.target.value);if(event.target.value==='default'&&!model)setModel(defaultChoices[0]??'');}}><option value="caller">Caller can choose</option><option value="default">Always use the default</option></select></label>
   </div>
    <details className="connection-policy">
     <summary>Per-model overrides</summary>
     <p className="panel-note">Blank limits inherit the key settings. Effective limits are capped by the key settings.</p>
     <label>Model to configure<select value={policyName} onChange={event=>setPolicyName(event.target.value)}>
      <option value="">Choose a model</option>{models.map(name=><option key={name}>{name}</option>)}
     </select></label>
     {policyName&&<>
      <label className="checkbox-label"><input type="checkbox" checked={policy.enabled!==false} onChange={event=>changePolicy(policyName,{enabled:event.target.checked})}/>Enable this model when in scope</label>
      <div className="fields">{policyFields.map(([field,label,min,max])=>
       <label key={field}>{label}<input type="number" min={min} max={max} value={policy[field]??''} placeholder="Inherit"
        onChange={event=>changePolicy(policyName,{[field]:event.target.value===''?undefined:Number(event.target.value)})}/></label>
      )}</div>
     </>}
    </details>
    </div>
   </section>
   <details className="box connection-disclosure" open={!!existing?.project_id||!!existing?.agent_id}>
    <summary>Project and agent context <ChevronDown size={16} aria-hidden="true"/></summary>
    <div className="form">
    <p className="panel-note">A project grants this connection access to its instructions and matching sources.</p>
    <div className="fields">
     <label>Project<select name="project_id" value={projectId} onChange={event=>setProjectId(event.target.value)}><option value="">No project</option>{(projects??[]).filter((item:Choice)=>!item.archived_at||item.id===existing?.project_id).map((item:Choice)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
     <label>Agent<select name="agent_id" value={agentId} onChange={event=>setAgentId(event.target.value)}><option value="">No agent</option>{(agents??[]).filter((item:Choice)=>(item.enabled&&item.runtime_mode==='analysis')||item.id===existing?.agent_id).map((item:Choice)=><option key={item.id} value={item.id}>{item.name}</option>)}</select></label>
    </div>
    {contextError&&<p className="error" role="alert">{contextError}</p>}
    </div>
   </details>
   <details className="box connection-disclosure" open={!!existing?.webhook_destination}>
    <summary>Job completion webhook <ChevronDown size={16} aria-hidden="true"/></summary>
    <div className="form">
    <label>Destination<select value={destination} onChange={event=>setDestination(event.target.value)}>
     <option value="">Off</option>
     {(destinations??[]).map((name:string)=><option key={name}>{name}</option>)}
     {destination&&!(destinations??[]).includes(destination)&&<option value={destination} disabled>{destination} (unavailable)</option>}
    </select></label>
    {destinationsError?<p className="error" role="alert">{destinationsError}</p>:<p className="panel-note">{destinations?.length?'Send a signed event when a job finishes.':'Ask the server operator to provision a webhook destination.'}</p>}
    </div>
   </details>
   <details className="box connection-disclosure">
    <summary>Permissions, limits, and expiry <ChevronDown size={16} aria-hidden="true"/></summary>
    <div className="form">
    <div className="fields">
     <label className="checkbox-label"><input type="checkbox" name="can_discover" defaultChecked={existing?.can_discover??true}/>Discover models</label>
     <label className="checkbox-label"><input type="checkbox" name="can_submit" defaultChecked={existing?.can_submit??true}/>Submit generation jobs</label>
     <label className="checkbox-label"><input type="checkbox" name="can_embed" defaultChecked={existing?.can_embed??false}/>Submit embedding jobs</label>
     <label className="checkbox-label"><input type="checkbox" name="can_read" defaultChecked={existing?.can_read??true}/>Read results and usage</label>
     <label className="checkbox-label"><input type="checkbox" name="can_cancel" defaultChecked={existing?.can_cancel??false}/>Cancel jobs</label>
    </div>
    <div className="fields">
     <label>Key expiry<input name="expires_at" type="datetime-local" defaultValue={expiry}/></label>
     <label>Requests per minute<input type="number" name="requests_per_minute" min={1} max={600} required defaultValue={existing?.requests_per_minute??30}/></label>
     <label>Pending jobs<input type="number" name="max_pending" min={1} max={20} required defaultValue={existing?.max_pending??20}/></label>
     <label>Generation timeout (seconds)<input type="number" name="timeout_seconds" min={15} max={300} required defaultValue={existing?.timeout_seconds??300}/></label>
     <label>Maximum output tokens<input type="number" name="max_output_tokens" min={128} max={4096} required defaultValue={existing?.max_output_tokens??2048}/></label>
     <label>Context window (tokens)<input type="number" name="context_tokens" min={1024} max={32768} required defaultValue={existing?.context_tokens??8192}/></label>
    </div>
    </div>
   </details>
   {!existing&&<section className="box">
    <header>Key recovery</header>
    <div className="form">
     <label className="checkbox-label"><input type="checkbox" name="save_for_reveal" disabled={!storageAvailable}/>Save encrypted copy for later reveal</label>
     <p className="panel-note">{storageAvailable?'Reveal requires your administrator password. Keys issued without this option are displayed only when issued.':'Encrypted recovery is unavailable on this workstation.'}</p>
    </div>
   </section>}
   <div className="actions connection-form-actions"><button className="primary" disabled={busy||(!!destination&&destination!==existing?.webhook_destination&&!(destinations??[]).includes(destination))||(!all&&!allowed.length)||(routing==='default'&&!model)|| (!!model&&!defaultChoices.includes(model))||(!!existing?.project_id&&!projects)||(!!existing?.agent_id&&!agents)}>{existing?'Save settings':'Create key'}</button><button type="button" onClick={cancel}>Cancel</button></div>
  </form>;
}

function ConnectionActivity({connection,tick}:{connection:Connection;tick:number}){
 const [job,setJob]=useState<Job|null>(null),[model,setModel]=useState(''),[error,setError]=useState('');
 const [busy,setBusy]=useState(false),[revision,setRevision]=useState(0);
 const [requestedOperation,setTestOperation]=useState<Operation>('generation');
 const testOperation=connection.can_embed&&(!connection.can_submit||requestedOperation==='embedding')?'embedding':'generation';
 const {data:activity,error:activityError}=useResource('connections/'+connection.id+'/activity',tick+revision);
 const active=!!job&&pending.has(job.status);
 const {data:access,error:accessError}=useResource('connections/'+connection.id+'/models?operation='+testOperation,tick);
 const {data:usage,error:usageError}=useResource('connections/'+connection.id+'/usage',tick+revision);
 const choices:string[]=access?.models??[];
 const selectedModel=choices.includes(model)?model:access?.default??choices[0]??'';
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
   const response=await api('connections/'+connection.id+'/test?operation='+testOperation,'POST',{request_id:newId(),prompt:testOperation==='embedding'?'CORE-AI connection test.':'Reply with CORE-AI connection OK.',model:selectedModel});
   setJob({...response,model:selectedModel,status:'QUEUED'});
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 async function jobAction(id:string,action:string){
  setBusy(true);setError('');
  try{
   const next=await api('connections/'+connection.id+'/jobs/'+id+'/'+action,'POST');
   if(action==='cancel')setJob(current=>current?.id===id?{...current,status:next.status}:current);
   setRevision(value=>value+1);
  }catch(e){setError((e as Error).message);}
  finally{setBusy(false);}
 }

 return <div className="settings-content connection-activity">
  <div className="actions">
   {connection.can_embed&&<label>Test operation<select value={testOperation} disabled={busy||active} onChange={event=>{
    setTestOperation(event.target.value as Operation);
    setModel('');
   }}><option value="generation" disabled={!connection.can_submit}>Generation</option><option value="embedding">Text embedding</option></select></label>}
   <label>Test model<select value={selectedModel} onChange={event=>setModel(event.target.value)}>
    {choices.map(name=><option key={name}>{name}</option>)}
   </select></label>
   <button disabled={!selectedModel||busy||active||connection.paused||connection.expired||!!connection.revoked_at||!(testOperation==='embedding'?connection.can_embed:connection.can_submit)||!connection.scope_available} onClick={()=>void test()}>Test connection</button>
  </div>
  {(error||activityError||accessError||usageError)&&<div className="error" role="alert">{error||activityError||accessError||usageError}</div>}
  {job&&<div role="status"><p>{job.model} · {job.status}</p>{(job.output||job.error)&&<pre>{job.output||job.error}</pre>}{job.embeddings&&<p>Embedding returned · {job.embeddings[0]?.length??0} dimensions</p>}</div>}
  <details>
   <summary>Model usage · {usage?.window_days??30} days</summary>
   {usage?.models?.length?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Model</th><th scope="col">Jobs</th><th scope="col">Last minute</th><th scope="col">Pending</th><th scope="col">Succeeded</th><th scope="col">Failed</th><th scope="col">Cancelled</th><th scope="col">Input tokens</th><th scope="col">Output tokens</th></tr></thead>
    <tbody>{usage.models.map((row:Usage)=><tr key={row.model}><td>{row.model}</td><td>{row.requests}</td><td>{row.recent_requests}</td><td>{row.pending}</td><td>{row.succeeded}</td><td>{row.failed}</td><td>{row.cancelled}</td><td>{row.measured_input_tokens}</td><td>{row.measured_output_tokens}</td></tr>)}</tbody>
   </table></div>:<p className="panel-note">{usage?'No usage recorded.':'Loading usage…'}</p>}
   <p className="panel-note">Token totals include only measurements reported by the provider.</p>
  </details>
  <details>
   <summary>Recent activity</summary>
   <button onClick={()=>setRevision(value=>value+1)}>Refresh activity</button>
   {activity?.length?<div className="table-scroll"><table>
    <thead><tr><th scope="col">Request</th><th scope="col">Model</th><th scope="col">Status</th><th scope="col">Duration</th><th scope="col">Webhook</th><th scope="col">Actions</th></tr></thead>
    <tbody>{activity.map((item:Job)=><tr key={item.id}><td>{item.request_id}</td><td>{item.model}</td><td>{item.status}{item.error&&<small> · {item.error}</small>}</td><td>{item.duration_seconds==null?'—':Number(item.duration_seconds).toFixed(1)+' s'}</td><td>{item.webhook_status??'—'}</td><td>{(item.status==='QUEUED'||item.status==='RUNNING')&&<button disabled={busy} onClick={()=>void jobAction(item.id,'cancel')}>Cancel job</button>}{(item.webhook_status==='FAILED'||item.webhook_status==='CANCELLED')&&<button disabled={busy} onClick={()=>void jobAction(item.id,'webhook/replay')}>Replay webhook</button>}</td></tr>)}</tbody>
   </table></div>:<p className="panel-note">{activity?'No jobs yet.':'Loading activity…'}</p>}
  </details>
 </div>;
}
