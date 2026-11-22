import {useEffect,useState} from 'react';
import {api} from './api';
import {ChatPopover} from './ChatPopover';
import {collectionTitle,matchesSkill,skillPurpose,skillTitle} from './skillLabels';

export type SkillChoice = {collection_id:string;commit:string;path:string;name:string;repository:string};
export type SkillSelection = {mode:'auto'|'manual'|'off';selected:SkillChoice[]};
type AvailableSkill = SkillChoice & {description:string};
type Preview = {available:AvailableSkill[];automatic:AvailableSkill[];error:string};
const sameSkill = (a:SkillChoice,b:SkillChoice) =>
 a.collection_id===b.collection_id && a.commit===b.commit && a.path===b.path;

export function ChatSkills({agent,prompt,value,change,disabled}: {
 agent?:string|null;prompt:string;value:SkillSelection;change:(value:SkillSelection)=>void;disabled:boolean;
}) {
 const label = value.mode==='manual' ? 'Selected ('+value.selected.length+')' : value.mode==='auto' ? 'Automatic' : 'Off';
 return <ChatPopover label={'Skills · '+label} kind="dialog" className="chat-skills-popover" buttonClass="chat-skills-trigger" disabled={disabled}
  trigger={<span>Skills · {label}</span>} align="start">
  {()=> <SkillPicker key={agent??'default'} agent={agent} prompt={prompt} value={value} change={change}/>}
 </ChatPopover>;
}

function SkillPicker({agent,prompt,value,change}: {
 agent?:string|null;prompt:string;value:SkillSelection;change:(value:SkillSelection)=>void;
}) {
 const [preview,setPreview] = useState<Preview|null>(null);
 const [error,setError] = useState('');
 const [filter,setFilter] = useState('');
 const [revision,refresh] = useState(0);
 useEffect(()=>{
  let active = true;
  setPreview(null);setError('');
  if(value.mode==='off')return;
  const timer = window.setTimeout(()=>{
   void api('skills/chat/preview','POST',{agent_id:agent||null,prompt: value.mode==='auto'?prompt:''})
    .then(result=>{if(active)setPreview(result);})
    .catch(err=>{if(active)setError(err.message);});
  },200);
  return()=>{active=false;window.clearTimeout(timer);};
 },[agent,prompt,value.mode,revision]);
 const options = (preview?.available??[]).filter(skill =>
  matchesSkill(skill,filter));
 const stale = preview && value.selected.filter(skill=>!preview.available.some(item=>sameSkill(item,skill)));
 return <div className="chat-skills-picker">
  <label>Skill selection<select value={value.mode} onChange={event=>change({...value,mode:event.target.value as SkillSelection['mode']})}>
   <option value="auto">Automatic matching</option><option value="manual">Choose specific skills</option><option value="off">Use no skills</option>
  </select></label>
  <p>{value.mode==='auto'?'Core AI matches skills to the message you write.':value.mode==='manual'?'Pick skills to apply to your next message.':'Your message will use the current agent and chat settings.'}</p>
  <p>{agent?'Skills assigned to this agent.':'Skills from all approved collections.'}</p>
  {value.mode!=='off' && <button type="button" onClick={()=>refresh(n=>n+1)}>Refresh skills</button>}
  {error && <p role="alert">{error}</p>}
  {value.mode!=='off' && !preview && !error && <p role="status">Checking available skills…</p>}
  {value.mode==='auto' && preview && <div aria-live="polite">
   <strong>Preview for this draft</strong>
   {preview.error ? <p>{preview.error}</p> : preview.automatic.length ?
    <ul>{preview.automatic.map(skill=><li key={skill.collection_id+skill.path}>{skillTitle(skill.name)} · {collectionTitle(skill.repository)} · {skill.commit.slice(0,8)}</li>)}</ul> :
    <p>{prompt.trim()?'No matching skills.':'Type a message to see matching skills.'}</p>}
   <small>The reply records the final selection.</small>
  </div>}
  {value.mode==='manual' && <div>
   {value.selected.length>0 && <ul className="chat-skill-selections">{value.selected.map(skill=><li key={skill.collection_id+skill.path}>
    {skillTitle(skill.name)} · {skill.commit.slice(0,8)} {stale?.some(item=>sameSkill(item,skill)) && ' · unavailable'}
    {' '}<button type="button" aria-label={'Remove skill '+skillTitle(skill.name)} onClick={()=>change({...value,selected:value.selected.filter(item=>!sameSkill(item,skill))})}>×</button>
   </li>)}</ul>}
   <label>Find skills<input type="search" value={filter} onChange={event=>setFilter(event.target.value)} placeholder="Task, name, or collection"/></label>
   <div className="chat-skill-options">{options.map(skill=>{
    const selected = value.selected.some(item=>sameSkill(skill,item));
    return <label key={skill.collection_id+skill.path} title={skill.description}>
     <input type="checkbox" checked={selected} disabled={!selected&&value.selected.length>=8} onChange={()=>change({
      ...value,selected:selected?value.selected.filter(item=>!sameSkill(skill,item)):[...value.selected,skill]
     })}/><span><strong>{skillTitle(skill.name)}</strong><small>{skillPurpose(skill.name,skill.description)}</small><small>{collectionTitle(skill.repository)} · {skill.commit.slice(0,8)}</small></span>
    </label>;
   })}</div>
   {preview && options.length===0 && <p>{preview.available.length?'No skills match this search.':agent?'This agent has no available skills. In Agents, assign an active skill collection.':'Activate a skill collection in Skills to make it available here.'}</p>}
  </div>}
 </div>;
}
