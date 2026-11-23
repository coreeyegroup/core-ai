import {useState,type FormEvent} from 'react';
import {api} from './api';
import {useResource} from './Workspace';

const providers = {
 http: {label:'Custom HTTPS API', endpoint:'', method:'GET', auth:'none', hint:'Enter a public HTTPS endpoint. Use a separate connection per operation.'},
 n8n: {label:'n8n webhook', endpoint:'', method:'POST', auth:'header', hint:'Use the production HTTPS URL from an active n8n Webhook node. Copy its header-auth credential into this connection.'},
 instagram: {label:'Instagram', endpoint:'https://graph.instagram.com/v<version>/me/media?fields=id,caption,media_type,permalink,timestamp&limit=10', method:'GET', auth:'bearer', hint:'Use an Instagram professional account and an access token obtained through Instagram Login. Replace <version> with your app’s Graph API version.'},
 facebook: {label:'Facebook Pages', endpoint:'https://graph.facebook.com/v<version>/<page-id>/posts?fields=id,message,created_time,permalink_url&limit=10', method:'GET', auth:'bearer', hint:'Use a Page token and account permissions for the Page and fields you are reading. Replace the version and Page ID.'},
 whatsapp: {label:'WhatsApp Business', endpoint:'https://graph.facebook.com/v<version>/<phone-number-id>?fields=id,display_phone_number,verified_name', method:'GET', auth:'bearer', hint:'Use a WhatsApp Business access token and your phone number ID to verify the connection. For incoming messages or sending replies, use a WhatsApp workflow in n8n.'},
 twelvedata: {label:'Twelve Data · Forex', endpoint:'https://api.twelvedata.com/time_series?symbol=EUR%2FUSD&interval=1h&outputsize=50', method:'GET', auth:'apikey', hint:'Use your Twelve Data API key. Change symbol, interval and output size to suit the instrument and your plan.'},
 upstox: {label:'Upstox · India markets', endpoint:'https://api.upstox.com/v2/option/chain?instrument_key=NSE_INDEX%7CNifty%2050&expiry_date=YYYY-MM-DD', method:'GET', auth:'bearer', hint:'Use an Upstox OAuth access token and replace the expiry with an available expiry. Replace the token when it expires.'},
 corei: {label:'Corei OS Mini', endpoint:'https://corei-os-mini.coreeye.in/api/research/v1/capabilities', method:'GET', auth:'bearer', hint:'Use the dedicated market research credential. Test capabilities first. For bars, use /api/research/v1/bars with account_id, symbol, timeframe and limit.'},
} as const;

type Provider = keyof typeof providers;
type Method = 'GET'|'POST'|'PUT'|'PATCH';
type Auth = 'none'|'bearer'|'header'|'basic'|'apikey';
type Settings = {name:string;provider:Provider;endpoint:string;method:Method;auth:Auth;header_name:string;paused:boolean};
type Connection = Settings & {id:string;version:number;has_secret:boolean};
type Result = {outcome:string;upstream_status:number|null;elapsed_ms:number;method:string;data:unknown;source_id:string|null};
type Activity = Pick<Result,'outcome'|'upstream_status'|'elapsed_ms'> & {id:number;occasion:string;occurred_at:string};
type Project = {id:string;name:string;archived_at?:string|null};
const blank:Settings={name:'',provider:'http',endpoint:'',method:'GET',auth:'none',header_name:'',paused:false};
const outcomes:Record<string,string> = {
 ok:'Request succeeded', dns_unavailable:'Hostname could not be resolved', destination_blocked:'Destination is outside the public HTTPS policy',
 upstream_rejected:'The external API rejected the request', provider_error:'The provider returned an application error',
 timeout:'The external API timed out', transport_error:'HTTPS connection failed', unsupported_encoding:'The provider returned an unsupported encoding',
 invalid_json:'The provider did not return valid JSON', response_too_large:'The response exceeded 512 KB',
 source_too_large:'The response is too large for a project source', source_unavailable:'The result could not be saved to the project',
 invalid_source_options:'Check the JSON path. A row limit requires an array at that path.',
};

function message(error:unknown){return error instanceof Error?error.message:'The operation failed.';}

export default function ExternalConnections({tick}:{tick:number}){
 const [revision,reload]=useState(0);
 const {data,error}=useResource('external-connections',tick+revision);
 const rows:Connection[]=Array.isArray(data)?data:[];
 const [selection,setSelection]=useState('');
 const [form,setForm]=useState<Connection|null|undefined>();
 const [query,setQuery]=useState('');
 const [busy,setBusy]=useState(false);
 const [failed,fail]=useState('');
 const selected=rows.find(row=>row.id===selection);
 async function save(values:Settings&{secret?:string}){
  setBusy(true);fail('');
  try{
   const result=await api(form?'external-connections/'+form.id:'external-connections',form?'PUT':'POST',
    {...values,version:form?.version});
   setSelection(result.id);setForm(undefined);reload(value=>value+1);
  }catch(error){fail(message(error));}
  finally{setBusy(false);}
 }
 async function remove(row:Connection){
  if(!window.confirm('Delete this connection, its saved credential, and its request history?'))return;
  setBusy(true);fail('');
  try{await api('external-connections/'+row.id,'DELETE');setSelection('');reload(value=>value+1);}
  catch(error){fail(message(error));}
  finally{setBusy(false);}
 }
 return <section className="external-workspace">
  <header className="external-intro">
   <div><h2>External apps and data</h2><p>Save a connection, test its endpoint, then run it or fetch data into a project.</p></div>
   {form===undefined&&<button className="primary" disabled={busy} onClick={()=>{setForm(null);fail('');}}>Add external connection</button>}
  </header>
  {(failed||error)&&<div className="error" role="alert">{failed||error}</div>}
  {form!==undefined?<ConnectionEditor key={form?.id??'new'} row={form} busy={busy} save={save}
   cancel={()=>{setForm(undefined);fail('');}}/>:<div className="external-grid">
   <section className="box external-list">
    <header>Saved connections <span>{rows.length}</span></header>
    {rows.length>0&&<label className="external-search">Find connections<input type="search" value={query} onChange={e=>setQuery(e.target.value)}/></label>}
    <div className="record-list">{rows.filter(row=>(row.name+' '+providers[row.provider].label).toLowerCase().includes(query.trim().toLowerCase())).map(row=>
     <button className="record" key={row.id} aria-current={selection===row.id?'true':undefined}
      onClick={()=>{setSelection(row.id);fail('');}}><b>{row.name}</b><span>{providers[row.provider].label} · {row.paused?'Paused':row.method}</span></button>)}</div>
    {!data&&!error&&<p role="status">Loading connections…</p>}
    {Array.isArray(data)&&!rows.length&&<p>No external connections yet.</p>}
    {rows.length>0&&!rows.some(row=>(row.name+' '+providers[row.provider].label).toLowerCase().includes(query.trim().toLowerCase()))&&<p>No matching connections.</p>}
   </section>
   {selected?<ConnectionRun key={selected.id+':'+selected.version} row={selected} tick={tick} busy={busy}
    edit={()=>{setForm(selected);fail('');}} remove={()=>void remove(selected)}/>:<section className="box settings-content">
    <h3>Choose a connection</h3><p>Select a saved connection to test it, preview data, or inspect its request history.</p>
   </section>}
  </div>}
 </section>;
}

function ConnectionEditor({row,busy,save,cancel}:{row:Connection|null;busy:boolean;save:(value:Settings&{secret?:string})=>Promise<void>;cancel:()=>void}){
 const [fields,setFields]=useState<Settings>(row??blank);
 const [secret,setSecret]=useState('');
 const {provider,auth}=fields;
 const preset=providers[provider];
 const patch=(change:Partial<Settings>)=>setFields(current=>({...current,...change}));
 function submit(event:FormEvent){
  event.preventDefault();
  if(busy)return;
  void save({...fields,secret:auth!=='none'&&secret?secret:undefined});
 }
 return <form className="box form external-editor" onSubmit={submit}>
  <header>{row?'Edit external connection':'New external connection'}</header>
  <fieldset disabled={busy}>
   <div className="external-fields">
    <label>Platform<select value={provider} onChange={e=>{
     const provider=e.target.value as Provider, entry=providers[provider];
     setSecret('');patch({provider,name:entry.label,endpoint:entry.endpoint,method:entry.method,auth:entry.auth,header_name:provider==='n8n'?'X-N8N-Webhook-Key':''});
    }}>{Object.entries(providers).map(([key,entry])=><option key={key} value={key}>{entry.label}</option>)}</select></label>
    <label>Connection name<input required maxLength={100} value={fields.name} onChange={e=>patch({name:e.target.value})}/></label>
   </div>
   <p className="panel-note">{preset.hint}</p>
   <label>HTTPS endpoint<input required maxLength={2048} placeholder="https://api.example.com/resource" value={fields.endpoint} onChange={e=>patch({endpoint:e.target.value})}/></label>
   <div className="external-fields">
    <label>Method<select value={fields.method} disabled={provider!=='http'} onChange={e=>patch({method:e.target.value as Method})}>
     {['GET','POST','PUT','PATCH'].map(value=><option key={value}>{value}</option>)}</select></label>
    <label>Authentication<select value={auth} disabled={provider!=='http'&&provider!=='n8n'} onChange={e=>{setSecret('');patch({auth:e.target.value as Auth});}}>
     <option value="none">None</option><option value="bearer">Bearer token</option><option value="header">API key in header</option>
     <option value="basic">Basic authentication</option>{provider==='twelvedata'&&<option value="apikey">Twelve Data API key</option>}
    </select></label>
   </div>
   {auth==='header'&&<label>Header name<input maxLength={64} required value={fields.header_name} onChange={e=>patch({header_name:e.target.value})}/></label>}
   {auth!=='none'&&<label>{auth==='basic'?'Credential (username:password)':'Token or API key'}<input type="password" autoComplete="new-password" maxLength={4096}
    value={secret} required={!row?.has_secret} placeholder={row?.has_secret?'Leave blank to keep current credential':undefined} onChange={e=>setSecret(e.target.value)}/></label>}
   <label className="checkbox-label"><input type="checkbox" checked={fields.paused} onChange={e=>patch({paused:e.target.checked})}/> Pause this connection</label>
  </fieldset>
  <div className="actions"><button className="primary" disabled={busy}>{busy?'Saving…':'Save connection'}</button>
   <button type="button" disabled={busy} onClick={cancel}>Cancel</button></div>
 </form>;
}

function ConnectionRun({row,tick,busy,edit,remove}:{row:Connection;tick:number;busy:boolean;edit:()=>void;remove:()=>void}){
 const [revision,reload]=useState(0);
 const {data:history,error:historyError}=useResource('external-connections/'+row.id+'/activity',tick+revision);
 const {data:projects}=useResource('projects',tick);
 const [project,setProject]=useState('');
 const [sourcePath,setSourcePath]=useState('');
 const [rowLimit,setRowLimit]=useState('');
 const [body,setBody]=useState('');
 const [result,setResult]=useState<Result|null>(null);
 const [failed,fail]=useState('');
 const [running,setRunning]=useState(false);
 const [confirming,setConfirming]=useState(false);
 const writable=row.method!=='GET';
 async function execute(occasion:'test'|'run', destination?:string, confirmed=false){
  if(running)return;
  fail('');setResult(null);setConfirming(false);
  let json:unknown;
  if(occasion==='run'&&writable&&body.trim()){
   try{json=JSON.parse(body);if(!json||typeof json!=='object')throw new Error();}
   catch{fail('Enter a JSON object or array for the request body.');return;}
  }
  if(destination&&rowLimit&&(!Number.isInteger(Number(rowLimit))||Number(rowLimit)<1||Number(rowLimit)>500)){
   fail('Enter a row limit between 1 and 500.');return;
  }
  setRunning(true);
  try{setResult(await api('external-connections/'+row.id+'/'+occasion,'POST',{
   body:json,project_id:destination||undefined,confirmed,
   source_path:destination?sourcePath.trim():undefined,row_limit:destination&&rowLimit?Number(rowLimit):undefined,
  },40_000));}
  catch(error){fail(message(error));}
  finally{setRunning(false);reload(value=>value+1);}
 }
 return <section className="box external-run">
  <header>{row.name}<span>{row.paused?'Paused':row.method+' · '+providers[row.provider].label}</span></header>
  <div className="settings-content">
   <div className="external-endpoint"><code>{row.endpoint}</code></div>
   <div className="actions"><button disabled={busy||running} onClick={edit}>Edit connection</button>
    <button disabled={busy||running} onClick={remove}>Delete connection</button></div>
   {row.paused&&<p role="status">Open Edit connection to resume requests.</p>}
   <form onSubmit={e=>{e.preventDefault();if(writable)setConfirming(true);else void execute('run');}}>
    {writable&&<label>Request body (optional JSON)<textarea value={body} maxLength={32768} rows={4} placeholder='{"event":"research.ready"}'
     onChange={e=>{setBody(e.target.value);setConfirming(false);}}/></label>}
    <div className="actions">
     <button type="button" disabled={row.paused||running||busy} onClick={()=>void execute('test')}>Test connection</button>
     <button className="primary" disabled={row.paused||running||busy}>{running?'Waiting for API…':writable?'Review and send':'Fetch preview'}</button>
    </div>
    {writable&&<p className="panel-note">Testing uses HEAD. Some POST-only endpoints return 404 or 405 during this check.</p>}
   </form>
   {confirming&&<section className="external-confirm" aria-label="Confirm external request">
    <b>Send {row.method} to {row.name}?</b><p>The destination may perform an external action.</p>
    <div className="actions"><button className="primary" disabled={running||busy||row.paused} onClick={()=>void execute('run',undefined,true)}>Confirm and send</button>
     <button onClick={()=>setConfirming(false)}>Cancel</button></div>
   </section>}
   {!writable&&<div>
    <details className="external-snapshot"><summary>Snapshot options</summary>
     <p>For large responses, choose a section of the JSON and limit the rows saved to the project.</p>
     <div className="external-fields">
      <label>JSON path (optional)<input value={sourcePath} maxLength={200} placeholder="data.items" onChange={e=>setSourcePath(e.target.value)}/></label>
      <label>Maximum rows (optional)<input type="number" min={1} max={500} value={rowLimit} placeholder="50" onChange={e=>setRowLimit(e.target.value)}/></label>
     </div>
    </details>
    <div className="external-project">
    <label>Save as project source<select value={project} onChange={e=>setProject(e.target.value)}>
     <option value="">Choose active project</option>
     {Array.isArray(projects)&&projects.filter((entry:Project)=>!entry.archived_at).map((entry:Project)=><option key={entry.id} value={entry.id}>{entry.name}</option>)}
    </select></label>
    <button disabled={!project||row.paused||running||busy} onClick={()=>void execute('run',project)}>Fetch and save</button>
   </div></div>}
   {failed&&<p className="error" role="alert">{failed}</p>}
   {result&&<section className="external-result" aria-label="Connection result">
    <p role="status"><b>{outcomes[result.outcome]??result.outcome}</b> · {result.method}{result.upstream_status!==null?' · HTTP '+result.upstream_status:''} · {result.elapsed_ms} ms</p>
    {result.source_id&&<div className="actions">
     <p>Snapshot saved to the project.</p>
     <button type="button" onClick={()=>window.dispatchEvent(new CustomEvent('core-ai-source',{detail:{id:result.source_id}}))}>Open saved source</button>
    </div>}
    {result.data!==null&&<details><summary>View JSON response</summary><pre>{JSON.stringify(result.data,null,2)}</pre></details>}
   </section>}
   <details className="external-history"><summary>Recent requests</summary>
    {historyError&&<p role="alert">{historyError}</p>}
    {Array.isArray(history)&&history.length>0?<div className="table-scroll"><table><thead><tr><th>Time</th><th>Action</th><th>Result</th></tr></thead>
     <tbody>{(history as Activity[]).map(entry=><tr key={entry.id}><td>{new Date(entry.occurred_at).toLocaleString()}</td><td>{entry.occasion}</td>
      <td>{outcomes[entry.outcome]??entry.outcome}{entry.upstream_status!==null?' · HTTP '+entry.upstream_status:''}</td></tr>)}</tbody></table></div>:<p>{history?'No requests yet.':'Loading request history…'}</p>}
   </details>
  </div>
 </section>;
}
