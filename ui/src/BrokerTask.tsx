import {useState} from 'react';
import {api} from './api';
import {useResource} from './Workspace';

export function BrokerTask({connection,tick,datasets}:{connection:string;tick:number;datasets:string[]}){
 const projects=useResource('projects',tick), agents=useResource('agents',tick);
 const [specialists,setSpecialists]=useState<string[]>([]),[sources,setSources]=useState<string[]>([]);
 const [project,setProject]=useState(''),[agent,setAgent]=useState('');
 const [keys,setKeys]=useState(''),[goal,setGoal]=useState('');
 const [task,setTask]=useState(''),[signal,setSignal]=useState(''),[ready,setReady]=useState(false);
 const [instrument,setInstrument]=useState(''),[account,setAccount]=useState('');
 const [side,setSide]=useState('BUY'),[product,setProduct]=useState('I');
 const [quantity,setQuantity]=useState(''),[price,setPrice]=useState('');
 const [busy,setBusy]=useState(false),[notice,setNotice]=useState('');
 async function action(fn:()=>Promise<void>){
  setBusy(true);setNotice('');
  try{await fn();}catch(err){setNotice(err instanceof Error?err.message:'Request failed.');}
  finally{setBusy(false);}
 }
 async function start(){
  const instruments=keys.split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
  const result=await api('external-connections/'+connection+'/analysis/start','POST',
   {project_id:project,agent_id:agent,instruments,goal,specialist_ids:specialists,saved_request_names:sources},180000);
  setTask(result.id);setInstrument('');setSignal('');setReady(false);setNotice('Task queued. Review its result when ready.');
 }
 async function review(){
  const result=await api('external-connections/'+connection+'/analysis/'+task+'/review','POST',{});
  setReady(result.status==='SUCCEEDED');setSignal(result.output||'');setNotice(result.status);
 }
 async function submit(){
  if(!window.confirm('Send a LIVE '+product+' '+side+' DAY limit order for '+quantity+' units of '+instrument+' at '+price+' to Upstox account '+account+'?'))return;
  const result=await api('external-connections/'+connection+'/orders/live','POST',{
   run_id:task,instrument,account_id:account,side,product,quantity:Number(quantity),price:Number(price),confirmed:true},40000);
  setNotice(result.broker_order_id?'Submitted · '+result.broker_order_id:'Check the Upstox order book before taking further action. '+result.status);
 }
 return <details className="external-snapshot"><summary>Broker analysis task and live order</summary>
  <fieldset disabled={busy}>
   <div className="external-fields">
    <label>Project<select value={project} onChange={e=>setProject(e.target.value)}><option value="">Select project</option>
     {(Array.isArray(projects.data)?projects.data:[]).filter(x=>!x.archived_at).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
    <label>Master agent<select value={agent} onChange={e=>setAgent(e.target.value)}><option value="">Select agent</option>
     {(Array.isArray(agents.data)?agents.data:[]).filter(x=>x.enabled).map(x=><option key={x.id} value={x.id}>{x.name}</option>)}</select></label>
   </div>
   <details><summary>Specialist agents and additional datasets</summary>
    {(Array.isArray(agents.data)?agents.data:[]).filter(x=>x.enabled&&x.id!==agent).map(x=><label className="checkbox-label" key={x.id}><input type="checkbox" checked={specialists.includes(x.id)} onChange={e=>setSpecialists(e.target.checked?[...specialists,x.id]:specialists.filter(id=>id!==x.id))}/>{x.name}</label>)}
    {datasets.map(name=><label className="checkbox-label" key={name}><input type="checkbox" checked={sources.includes(name)} onChange={e=>setSources(e.target.checked?[...sources,name]:sources.filter(x=>x!==name))}/>{name}</label>)}
   </details>
   <label>Instrument keys<textarea value={keys} onChange={e=>setKeys(e.target.value)} placeholder="Enter one Upstox instrument key per line"/></label>
   <label>Task instructions<textarea value={goal} onChange={e=>setGoal(e.target.value)}/></label>
   <button disabled={!keys.trim()||!goal.trim()||!agent||!project} onClick={()=>void action(start)}>Collect quotes and start analysis</button>
   <label>Analysis task ID<input value={task} onChange={e=>{setTask(e.target.value);setSignal('');setReady(false);}}/></label>
   <button disabled={!task} onClick={()=>void action(review)}>Review task result</button>
   {signal&&<pre>{signal}</pre>}
   {ready&&<details><summary>Prepare live DAY limit order</summary>
    <div className="external-fields">
     <label>Upstox account ID<input value={account} onChange={e=>setAccount(e.target.value)}/></label>
     <label>Instrument key from task<input value={instrument} onChange={e=>setInstrument(e.target.value)}/></label>
     <label>Side<select value={side} onChange={e=>setSide(e.target.value)}><option>BUY</option><option>SELL</option></select></label>
     <label>Product<select value={product} onChange={e=>setProduct(e.target.value)}><option value="I">Intraday</option><option value="D">Delivery</option></select></label>
     <label>Quantity in units<input type="number" min="1" value={quantity} onChange={e=>setQuantity(e.target.value)}/></label>
     <label>Limit price<input type="number" min="0" step="any" value={price} onChange={e=>setPrice(e.target.value)}/></label>
    </div>
    <button disabled={!account||!instrument||Number(price)<=0||Number(quantity)<=0} onClick={()=>void action(submit)}>Review live order</button>
    <button disabled={!instrument} onClick={()=>void action(async()=>{const r=await api("external-connections/"+connection+"/orders/status","POST",{run_id:task,instrument});setNotice([r.status,r.order_id,r.filled_quantity!=null?"Filled units "+r.filled_quantity:"",r.average_price!=null?"Average price "+r.average_price:""].filter(Boolean).join(" · "));})}>Check broker status and fills</button>
   </details>}
   {notice&&<p role="status">{notice}</p>}
  </fieldset>
 </details>;
}
