import {useRef,useState,type FormEvent} from 'react';
import {api} from './api';
import type {View} from './layout';
import {useSession} from './Session';
import {AgentCollections,type Collection} from './Skills';
import {useResource} from './Workspace';

export type SkillSetup = {repository?:string; collection?:Collection; agentId?:string};
export type AgentHandoff = {collectionId?:string; agentId?:string};
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
type Step = 0|1|2;
type Checkpoint = {agentId:string;presetId:Preset['id'];step:Step};

function readCheckpoint(key:string):Checkpoint|null{
 try{
  const value=JSON.parse(localStorage.getItem(key)??'null');
  if(typeof value?.agentId==='string'&&value.agentId&&presets.some(preset=>preset.id===value.presetId)&&
    (value.step===0||value.step===1||value.step===2))return value;
 }catch{/* Browser storage is optional. */}
 return null;
}

function keepCheckpoint(key:string,value:Checkpoint|null){
 try{
  if(value)localStorage.setItem(key,JSON.stringify(value));
  else localStorage.removeItem(key);
 }catch{/* Setup still works without browser storage. */}
}
const steps = ['Choose an agent','Attach skills','Start work'];

export default function AgentSetup({tick,refresh,go,openSkills,openTask,openChat}: {
 tick:number;refresh:()=>void;go:(view:View)=>void;openSkills:(setup:SkillSetup)=>void;
 openTask:(setup:RunSetup)=>void;openChat:(setup:RunSetup)=>boolean;
}){
 const {id,username,role}=useSession();
 const storageKey='core-ai.agent-setup.v1.'+(id??username);
 const [checkpoint]=useState(()=>role==='VIEWER'?null:readCheckpoint(storageKey));
 const {data:agents,error:agentError}=useResource('agents',tick);
 const {data:catalog,error:catalogError}=useResource('skills',tick);
 const [step,setStep]=useState<Step>(checkpoint?.step??0);
 const [preset,setPreset]=useState<Preset>(()=>presets.find(item=>item.id===checkpoint?.presetId)??presets[0]);
 const [mode,setMode]=useState<'new'|'existing'>(checkpoint?'existing':'new');
 const [name,setName]=useState<string>(preset.agent);
 const [instructions,setInstructions]=useState<string>(preset.instructions);
 const [existing,setExisting]=useState(checkpoint?.agentId??'');
 const [agentId,setAgentId]=useState(checkpoint?.agentId??'');
 const [created,setCreated]=useState<Agent|null>(null);
 const [assigned,setAssigned]=useState<string[]|null>(null);
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');
 const heading=useRef<HTMLHeadingElement>(null);
 const rows:Collection[]=Array.isArray(catalog)?catalog:[];
 const enabled:Agent[]=Array.isArray(agents)?agents.filter((item:Agent)=>item.enabled):[];
 const recommended=rows.find(row=>row.repository===preset.repository&&row.active_commit)??rows.find(row=>row.repository===preset.repository);
 const active=!!recommended?.active_commit;
 const agent=enabled.find(row=>row.id===agentId)??(created?.id===agentId&&!agents?.some((row:Agent)=>row.id===agentId)?created:null);
 const assignmentCount=assigned?.length??0;
 function advance(next:Step,nextAgent=agentId){
  setStep(next);setError('');
  keepCheckpoint(storageKey,nextAgent?{agentId:nextAgent,presetId:preset.id,step:next}:null);
  window.requestAnimationFrame(()=>heading.current?.focus());
 }
 function chooseTemplate(value:Preset){
  if (mode==='new' && (name!==preset.agent||instructions!==preset.instructions) && !window.confirm('Replace the agent name and instructions with this template?')) return;
  setPreset(value);setName(value.agent);setInstructions(value.instructions);
 }
 function chooseAgent(value:Agent){
  if(value.id!==agentId)setAssigned(null);
  setAgentId(value.id);setMode('existing');setExisting(value.id);advance(1,value.id);
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
   const saved={id:result.id,name,enabled:true};
   setCreated(saved);chooseAgent(saved);
   refresh();
  } catch(failure){setError((failure as Error).message);}
  finally{setBusy(false);}
 }
 function startAnother(){
  setAgentId('');setCreated(null);setExisting('');setAssigned(null);setMode('new');
  setName(preset.agent);setInstructions(preset.instructions);advance(0,'');
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
   <ol className="setup-steps" aria-label="Agent setup progress">{steps.map((label,index)=><li key={label} aria-current={index===step?'step':undefined} data-complete={index<step}>
    <span className="setup-step-number" aria-hidden="true">{index+1}</span><span>{label}</span>{index<step&&<span className="sr-only"> complete</span>}
   </li>)}</ol>
   <section className="box settings-content setup-card">
    <h2 ref={heading} tabIndex={-1}>{steps[step]}</h2>
    {(error||agentError||(step===1&&catalogError))&&<p className="error" role="alert">{error||agentError||catalogError}</p>}
    {step>0&&!agent&&(Array.isArray(agents)?<div className="stack"><p>This agent is unavailable or disabled. Choose another to continue setup.</p>
     <div className="actions"><button className="primary" onClick={startAnother}>Choose an agent</button><button onClick={()=>go('Agents')}>Manage agents</button></div>
    </div>:<p role="status">Checking your saved agent…</p>)}
    {step===0&&<form onSubmit={saveAgent}>
     <fieldset className="setup-fieldset" disabled={busy}><legend>How do you want to start?</legend>
      <label className="checkbox-label"><input name="agent-start-mode" type="radio" checked={mode==='new'} onChange={()=>setMode('new')}/>Create an agent</label>
      <label className="checkbox-label"><input name="agent-start-mode" type="radio" checked={mode==='existing'} onChange={()=>setMode('existing')}/>Use an existing agent</label>
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
    {step>0&&agent&&<div className="setup-current"><b>{agent.name}</b><span>{preset.title}</span></div>}
    {step>0&&agent&&<div className="setup-skills" hidden={step!==1}>
     <p>Collections give this agent reusable instructions. Add a collection or continue with its saved setup.</p>
     {preset.repository&&<div className="setup-recommendation">
      <div><strong>{preset.title} collection</strong><p>{preset.repository} · {active?'Active':recommended?'Awaiting review':catalog?'Available on GitHub':'Checking catalog…'}</p><p>{preset.skills}</p></div>
      {role==='ADMIN'&&Array.isArray(catalog)&&!active&&<button type="button" onClick={()=>openSkills({repository:preset.repository,collection:recommended})}>{recommended?'Review collection':'Open import form'}</button>}
     </div>}
     {Array.isArray(catalog)&&!active&&preset.repository&&role!=='ADMIN'&&<p>An administrator can import and activate this collection.</p>}
     <AgentCollections key={agent.id} agent={agent.id} rows={rows} tick={tick}
      onSelectionSaved={setAssigned} recommendedCollection={active?recommended?.id:undefined}
      onContinue={()=>advance(2)} onBack={()=>advance(0)} onReview={()=>go('Skills')}/>
    </div>}
    {step===2&&agent&&<>
     <StartWork tick={tick} assignmentCount={assigned===null?null:assignmentCount} go={go} launch={launch}/>
     <div className="actions setup-footer"><button onClick={()=>advance(1)}>Back to skills</button><button onClick={startAnother}>Set up another agent</button></div>
    </>}
   </section>
  </>}
 </section>;
}

function StartWork({tick,assignmentCount,go,launch}:{
 tick:number;assignmentCount:number|null;go:(view:View)=>void;launch:(kind:'chat'|'task')=>void;
}){
 const {data:models,error:modelError}=useResource('models',tick);
 const {data:projects,error:projectError}=useResource('projects',tick);
 const {data:overview,error:overviewError}=useResource('overview',tick);
 const modelCount=models?.available&&Array.isArray(models.models)?models.models.length:0;
 const projectCount=Array.isArray(projects)?projects.filter(project=>!project.archived_at).length:0;
 const workerOnline=overview?.worker?.online===true;
 return <>
  <dl className="setup-readiness">
   <div><dt>Skill collections</dt><dd>{assignmentCount===null?'Checking…':assignmentCount+' assigned'}</dd></div>
   <div><dt>Chat models</dt><dd>{modelError?'Could not check':!models?'Checking…':modelCount?modelCount+' available':models.available?'None available':'Provider offline'}</dd></div>
   <div><dt>Task projects</dt><dd>{projectError?'Could not check':!projects?'Checking…':projectCount?projectCount+' available':'Project required'}</dd></div>
   <div><dt>Task worker</dt><dd>{overviewError?'Could not check':!overview?'Checking…':workerOnline?'Online':'Offline'}</dd></div>
  </dl>
  <div className="setup-route">
   <div><h3>Try in Chat</h3><p>Open a draft with this agent. Add your data, then send when ready.</p></div>
   <div className="actions">{!!models&&!modelCount&&<button onClick={()=>go('Models')}>Open Models</button>}<button className="primary" onClick={()=>launch('chat')}>Open test chat</button></div>
  </div>
  <div className="setup-route">
   <div><h3>Queue a task</h3><p>{projects&&!projectCount?'Create your first project in the task form, then choose a model and queue your work.':'Choose a project and model. The task worker runs your work and records its result.'}</p>
    {overview&&!workerOnline&&<p>Queued tasks wait for the worker to come online.</p>}</div>
   <button onClick={()=>launch('task')}>Open task form</button>
  </div>
 </>;
}
