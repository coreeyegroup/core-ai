import {useRef,useState,type FormEvent} from 'react';
import {api} from './api';
import type {View} from './layout';
import {useSession} from './Session';
import {AgentCollections,type Collection} from './Skills';
import {useResource} from './Workspace';

export type SkillSetup = {repository:string; collection?:Collection};
export type RunSetup = {agentId:string; prompt:string};

const presets = [
 {id:'forex', title:'International Forex', agent:'International Forex Research',
  purpose:'Major and cross currency pairs, rates, sessions, and macro events. Also covers XAUUSD as a separate instrument.',
  repository:'marian2js/trading-skills', skills:'Macro Event Analysis · Market Regime Analysis · Pre Trade Check',
  instructions:'Review international forex pairs and XAUUSD using supplied or connected market data. State instrument, timeframe, session, source, timestamp and freshness. Explain rate differentials, calendar catalysts, trend, volatility and contradictory evidence when supported. Use verified values and flag missing data. Describe research scenarios and invalidation only when supported. Leave signal selection, risk enforcement and orders to the trading platform.',
  prompt:'Review the market snapshot I provide for EURUSD and USDJPY. Separate price observations, rates and macro catalysts, and explain which evidence is missing or stale.'},
 {id:'india', title:'India F&O', agent:'India F&O Research',
  purpose:'NIFTY, BANKNIFTY, and NSE equity or index futures and options.',
  repository:'reddygopalkrishna/trading-skills', skills:'India and US F&O Analysis (option chains, OI, implied volatility, and Greeks)',
  instructions:'Review Indian F&O using supplied or connected market data. Identify the underlying, expiry, strike, source and timestamp. Keep observed OI, change in OI, LTP, IV and Greeks separate from interpretation. Flag missing inputs or comparison periods. Leave signal selection, risk enforcement and orders to the trading platform.',
  prompt:'Review the NSE option-chain snapshot I provide. Compare the ATM strike and nearby strikes and flag missing values or unclear OI comparison periods.'},
 {id:'validation', title:'Strategy validation', agent:'Strategy Validation',
  purpose:'Evaluate a strategy or backtest across markets.',
  repository:'ml4t/skills', skills:'Walk-Forward Validation · Backtest Trading Costs',
  instructions:'Review strategy evidence for time ordering, leakage, out-of-sample results, trade costs, liquidity and drawdown. Use supplied data and identify missing tests. Separate findings from hypotheses.',
  prompt:'Review the backtest report I provide. Check out-of-sample testing, leakage, transaction costs and drawdown. List the checks still needed.'},
 {id:'custom', title:'Custom agent', agent:'', purpose:'Define an agent for any kind of work.',
  repository:'', skills:'', instructions:'', prompt:''}
] as const;
type Preset = typeof presets[number];
type Agent = {id:string;name:string;enabled:boolean};
const steps = ['Choose an agent','Attach skills','Start work'];

export default function AgentSetup({tick,refresh,go,openSkills,openTask,openChat}: {
 tick:number;refresh:()=>void;go:(view:View)=>void;openSkills:(setup:SkillSetup)=>void;
 openTask:(setup:RunSetup)=>void;openChat:(setup:RunSetup)=>boolean;
}){
 const {role}=useSession();
 const {data:agents,error:agentError}=useResource('agents',tick);
 const {data:catalog,error:catalogError}=useResource('skills',tick);
 const [step,setStep]=useState(0);
 const [preset,setPreset]=useState<Preset>(presets[0]);
 const [mode,setMode]=useState<'new'|'existing'>('new');
 const [name,setName]=useState<string>(preset.agent);
 const [instructions,setInstructions]=useState<string>(preset.instructions);
 const [existing,setExisting]=useState('');
 const [agent,setAgent]=useState<Agent|null>(null);
 const [assigned,setAssigned]=useState<string[]|null>(null);
 const [dirty,setDirty]=useState(false);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const heading=useRef<HTMLHeadingElement>(null);
 const rows:Collection[]=Array.isArray(catalog)?catalog:[];
 const enabled:Agent[]=Array.isArray(agents)?agents.filter((item:Agent)=>item.enabled):[];
 const recommended=rows.find(row=>row.repository===preset.repository&&row.active_commit)??rows.find(row=>row.repository===preset.repository);
 const active=!!recommended?.active_commit;
 const agentRow=enabled.find(row=>row.id===agent?.id);
 const canStart=!!agent&&(!!agentRow||busy||!Array.isArray(agents));
 const assignmentCount=assigned?.length??0;
 function advance(next:number){
  setStep(next);setError('');
  window.requestAnimationFrame(()=>heading.current?.focus());
 }
 function chooseTemplate(value:Preset){
  if (mode==='new' && (name!==preset.agent||instructions!==preset.instructions) && !window.confirm('Replace the agent name and instructions with this template?')) return;
  setPreset(value);setName(value.agent);setInstructions(value.instructions);
 }
 function chooseAgent(value:Agent){
  if(value.id!==agent?.id){setAssigned(null);setDirty(false);}
  setAgent(value);setMode('existing');setExisting(value.id);advance(1);
 }
 async function saveAgent(event:FormEvent<HTMLFormElement>){
  event.preventDefault();
  if(busy||role==='VIEWER') return;
  if(mode==='existing'){
   const selected=enabled.find(row=>row.id===existing);
   if(selected) chooseAgent(selected);
   return;
  }
  setBusy(true);setError('');
  try {
   const result=await api('agents','POST',{name,instructions});
   chooseAgent({id:result.id,name,enabled:true});
   refresh();
  } catch(failure){setError((failure as Error).message);}
  finally{setBusy(false);}
 }
 function launch(kind:'chat'|'task'){
  if (!agent) return;
  const setup={agentId:agent.id,prompt:preset.prompt};
  if(kind==='task') openTask(setup);
  else if(!openChat(setup)) setError('Close a chat tab to make room for this test, then try again.');
 }
 return <section className="page setup-page">
  <header className="page-head"><div><h1>Get started</h1><p>Set up an agent, attach skills if you need them, then try it in Chat or queue a task.</p></div>
   <button onClick={()=>go('Agents')}>Manage agents</button>
  </header>
  {role==='VIEWER'?<section className="box settings-content"><h2>Explore the workspace</h2>
   <p>Your viewer role can browse existing agents, their skills, and task results. An editor or administrator can set up and run agents.</p>
   <div className="actions"><button onClick={()=>go('Agents')}>Browse agents</button><button onClick={()=>go('Tasks')}>View tasks</button></div>
  </section>:<>
   <ol className="setup-steps" aria-label="Agent setup progress">{steps.map((label,index)=><li key={label} aria-current={index===step?'step':undefined}>{index+1}. {label}</li>)}</ol>
   <section className="box settings-content setup-card">
    <h2 ref={heading} tabIndex={-1}>{steps[step]}</h2>
    {(error||agentError||catalogError)&&<p className="error" role="alert">{error||agentError||catalogError}</p>}
    {step===0&&<form onSubmit={saveAgent}>
     <fieldset className="setup-fieldset"><legend>How do you want to start?</legend>
      <label className="checkbox-label"><input type="radio" checked={mode==='new'} onChange={()=>setMode('new')}/>Create an agent</label>
      <label className="checkbox-label"><input type="radio" checked={mode==='existing'} onChange={()=>setMode('existing')}/>Use an existing agent</label>
     </fieldset>
     <label>{mode==='new'?'Starting template':'Research focus'}<select value={preset.id} disabled={busy} onChange={event=>{
      const value=presets.find(item=>item.id===event.target.value);
      if(value) chooseTemplate(value);
     }}>{presets.map(item=><option value={item.id} key={item.id}>{item.title}</option>)}</select></label>
     <p className="panel-note">{preset.purpose}</p>
     {mode==='new'?<>
      <label>Agent name<input required maxLength={120} value={name} onChange={event=>setName(event.target.value)}/></label>
      <label>Agent instructions<textarea rows={5} required maxLength={16000} value={instructions} onChange={event=>setInstructions(event.target.value)}/></label>
     </>:<label>Enabled agent<select value={existing} required onChange={event=>setExisting(event.target.value)}>
      <option value="">{agents?'Select an agent':'Loading agents…'}</option>
      {enabled.map(item=><option key={item.id} value={item.id}>{item.name}</option>)}
     </select></label>}
     {mode==='existing'&&Array.isArray(agents)&&!enabled.length&&<p>There are no enabled agents. Create one or enable an agent in Agents.</p>}
     <button className="primary" disabled={busy||(mode==='existing'&&!enabled.length)}>{busy?'Saving…':mode==='new'?'Create agent and continue':'Continue with this agent'}</button>
    </form>}
    {step===1&&agent&&<>
     <p>Skills give <strong>{agent.name}</strong> reusable instructions. Select collections and save the assignment, or continue with its current setup.</p>
     {preset.repository&&<div className="setup-recommendation">
      <div><strong>{preset.title} collection</strong><p>{preset.repository} · {active?'Active':recommended?'Awaiting review':catalog?'Available on GitHub':'Checking catalog…'}</p><p>{preset.skills}</p></div>
      {role==='ADMIN'&&Array.isArray(catalog)&&!active&&<button type="button" onClick={()=>openSkills({repository:preset.repository,collection:recommended})}>{recommended?'Review collection':'Open import form'}</button>}
     </div>}
     {Array.isArray(catalog)&&!active&&preset.repository&&role!=='ADMIN'&&<p>An administrator can import and activate this collection.</p>}
     <AgentCollections key={agent.id} agent={agent.id} rows={rows} tick={tick} onDirtyChange={setDirty}
      onSelectionSaved={setAssigned} suggestedCollection={active?recommended?.id:undefined} onReview={()=>go('Skills')}/>
     <div className="actions setup-footer"><button onClick={()=>{if(!dirty||window.confirm('Discard unsaved collection selections?')){setDirty(false);advance(0);}}}>Back</button>
      <button className="primary" disabled={dirty||assigned===null} onClick={()=>advance(2)}>{assigned?.length?'Continue to start work':'Continue without skills'}</button></div>
     {dirty&&<p role="status">Save the collection assignment to continue, or clear the unsaved selections.</p>}
    </>}
    {step===2&&agent&&<>
     <p><strong>{agent.name}</strong> · {assignmentCount} skill {assignmentCount===1?'collection':'collections'} assigned</p>
     {!canStart&&<p role="alert">This agent is no longer enabled. Choose an enabled agent to continue.</p>}
     <div className="setup-route">
      <div><h3>Try in Chat</h3><p>Start with a sample prompt. Add your own data, then send when ready.</p></div>
      <button className="primary" disabled={!canStart} onClick={()=>launch('chat')}>Open test chat</button>
     </div>
     <div className="setup-route">
      <div><h3>Queue a task</h3><p>Use a project and model to run work in the background and keep its result.</p></div>
      <button disabled={!canStart} onClick={()=>launch('task')}>Open task form</button>
     </div>
     <button onClick={()=>advance(1)}>Back to skills</button>
    </>}
   </section>
  </>}
 </section>;
}
