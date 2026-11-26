import {useEffect,useRef,useState,type FormEvent} from 'react';
import {api,newId} from './api';
import {useSession} from './Session';
import {modelLabel,type Model,type Program} from './CapabilityFields';

type Choice={collection_id:string;commit:string;path:string};
export type SkillSelection={mode:'auto'|'manual'|'off';selected:Choice[]};
type Skill=Choice&{name:string;repository:string;description:string};
type Collection={id:string;repository:string;active_commit:string|null;skill_count:number};
type Member={id:string;name:string;instructions:string;model:string;prompt:string;depends_on:string[];collections:{id:string;commit:string}[];skill_selection:SkillSelection;tools:string[];program_scope:string[]};
const blank=(id:string):Member=>({id,name:'',instructions:'',model:'',prompt:'',depends_on:[],collections:[],skill_selection:{mode:'auto',selected:[]},tools:[],program_scope:[]});
const toolNames=['knowledge.search','project.inspect','artifact.create','program.list','program.run'];
const key=(x:Choice)=>x.collection_id+'@'+x.commit+':'+x.path;
const toggle=(a:string[],v:string,checked:boolean)=>checked?[...a,v]:a.filter(x=>x!==v);
const example=()=>[
 {...blank('research'),name:'Evidence researcher',instructions:'Use supplied and authorized project evidence. Identify gaps, sources and uncertainty. Do not invent data.',prompt:'Collect and summarize evidence for the mission objective.'},
 {...blank('review'),name:'Independent reviewer',instructions:'Check accuracy, assumptions and missing evidence. Separate verified findings from hypotheses.',prompt:'Review the earlier research output against the objective and report any gaps.',depends_on:['research']}
];
export default function AgentTeamBuilder({projects,models,programs,visible,onSaved}:{projects:{id:string;name:string}[];models:Model[];programs:Program[];visible:boolean;onSaved:()=>Promise<void>}){
 const readonly=useSession().role==='VIEWER';
 const [open,setOpen]=useState(false),[collections,setCollections]=useState<Collection[]>([]),[skills,setSkills]=useState<Skill[]>([]),[query,setQuery]=useState('');
 const [project,setProject]=useState(''),[title,setTitle]=useState(''),[objective,setObjective]=useState(''),[members,setMembers]=useState<Member[]>([blank('step-1')]);
 const [busy,setBusy]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState<{mission_id:string;agents:{id:string;name:string}[]}|null>(null);
 const attempt=useRef<{fingerprint:string;id:string}|null>(null);
 useEffect(()=>{if(!open||!visible)return;let live=true;Promise.all([api('skills'),api('skills/chat/preview','POST',{prompt:''})]).then(([c,s])=>{if(live){if(!Array.isArray(c)||!Array.isArray(s?.available))throw new Error('Skill catalog unavailable');setCollections(c.filter(x=>x.active_commit));setSkills(s.available);}}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[open,visible]);
 function edit(i:number,patch:Partial<Member>){setMembers(old=>old.map((m,j)=>i===j?{...m,...patch}:m));setSaved(null);}
 function loadExample(){if(!window.confirm('Replace this unsaved team draft with a research and review example?'))return;setMembers(example());setSaved(null);}
 async function save(e:FormEvent){e.preventDefault();if(busy||readonly)return;setError('');
  if(!window.confirm('Create these new agent profiles, attach the selected collections and save the mission? No task is launched.'))return;
  const body={project_id:project,title,objective,agents:members};const fp=JSON.stringify(body);
  if(attempt.current?.fingerprint!==fp)attempt.current={fingerprint:fp,id:newId()};
  setBusy(true);try{const r=await api('agent-teams','POST',{...body,request_id:attempt.current.id},50000);setSaved(r);await onSaved();}catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <details className="box" open={open} onToggle={e=>setOpen(e.currentTarget.open)}>
  <summary>Build agent team · skills, tools, tasks and mission</summary>
  <p>Configure new agents and their tasks together. Save the entire team as one reusable mission, then review and launch from the Mission workspace. Existing agents are unchanged.</p>
  {error&&<p className="error" role="alert">{error}</p>}
  <form className="form" onSubmit={save}>
   <fieldset disabled={readonly||busy} className="form">
    <div className="fields"><label>Project<select required value={project} onChange={e=>{setProject(e.target.value);setSaved(null);}}><option value="">Select project</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>Mission title<input required maxLength={120} value={title} onChange={e=>{setTitle(e.target.value);setSaved(null);}}/></label></div>
    <label>Objective and acceptance criteria<textarea required maxLength={4000} rows={3} value={objective} onChange={e=>{setObjective(e.target.value);setSaved(null);}}/></label>
    <button type="button" onClick={loadExample}>Use research and reviewer example</button>
    {members.map((m,i)=>{
      const available=skills.filter(s=>m.collections.some(c=>c.id===s.collection_id&&c.commit===s.commit));
      const filtered=available.filter(s=>(s.repository+' '+s.name+' '+s.description).toLowerCase().includes(query.toLowerCase()));
      return <section className="box form" key={m.id}><header>Agent {i+1} · {m.id}<button type="button" disabled={members.length===1} onClick={()=>{setMembers(old=>old.filter((_,j)=>j!==i).map(x=>({...x,depends_on:x.depends_on.filter(d=>d!==m.id)})));setSaved(null);}}>Remove draft agent</button></header>
       <div className="fields"><label>Name<input required maxLength={120} value={m.name} onChange={e=>edit(i,{name:e.target.value})}/></label><label>Model<select required value={m.model} onChange={e=>edit(i,{model:e.target.value})}><option value="">Choose model</option>{models.filter(x=>!m.tools.length||!Array.isArray(x.capabilities)||x.capabilities.includes('tools')).map(x=><option key={x.name} value={x.name}>{modelLabel(x)}</option>)}</select></label></div>
       <label>Agent instructions<textarea required maxLength={16000} rows={3} value={m.instructions} onChange={e=>edit(i,{instructions:e.target.value})}/></label>
       <details><summary>Skill collections ({m.collections.length})</summary>{collections.map(c=><label key={c.id} className="checkbox-label"><input type="checkbox" checked={m.collections.some(x=>x.id===c.id)} onChange={e=>edit(i,{collections:e.target.checked?[...m.collections,{id:c.id,commit:c.active_commit!}]:m.collections.filter(x=>x.id!==c.id),skill_selection:{...m.skill_selection,selected:m.skill_selection.selected.filter(s=>s.collection_id!==c.id)}})}/>{c.repository} · {c.skill_count} skills</label>)}</details>
       <label>Task skill selection<select value={m.skill_selection.mode} onChange={e=>edit(i,{skill_selection:{mode:e.target.value as SkillSelection['mode'],selected:[]}})}><option value="auto">Auto from assigned collections</option><option value="manual">Select exact skills</option><option value="off">No skill guidance</option></select></label>
       {m.skill_selection.mode==='manual'&&<details open><summary>Selected skills ({m.skill_selection.selected.length}/8)</summary><input aria-label="Search skills" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Filter by name or repository"/><div style={{maxHeight:'16rem',overflow:'auto'}}>{filtered.map(s=>{const checked=m.skill_selection.selected.some(x=>key(x)===key(s));return <label className="checkbox-label" key={key(s)}><input type="checkbox" checked={checked} disabled={!checked&&m.skill_selection.selected.length>=8} onChange={e=>edit(i,{skill_selection:{mode:'manual',selected:e.target.checked?[...m.skill_selection.selected,{collection_id:s.collection_id,commit:s.commit,path:s.path}]:m.skill_selection.selected.filter(x=>key(x)!==key(s))}})}/>{s.name} · {s.repository}</label>;})}</div></details>}
       <details><summary>Tools and permissions ({m.tools.length})</summary>{toolNames.map(t=><label className="checkbox-label" key={t}><input type="checkbox" checked={m.tools.includes(t)} onChange={e=>edit(i,{tools:toggle(m.tools,t,e.target.checked),...(t==='program.run'&&!e.target.checked?{program_scope:[]}:{})})}/>{t}</label>)}{m.tools.includes('program.run')&&<div style={{maxHeight:'16rem',overflow:'auto'}}>{programs.map(p=><label className="checkbox-label" key={p.id}><input type="checkbox" checked={m.program_scope.includes(p.id)} onChange={e=>edit(i,{program_scope:toggle(m.program_scope,p.id,e.target.checked)})}/>{p.id} · {p.mode}</label>)}</div>}</details>
       <label>Task instructions / expected output<textarea required maxLength={12000} rows={3} value={m.prompt} onChange={e=>edit(i,{prompt:e.target.value})}/></label>
       {i>0&&<fieldset><legend>Use outputs from earlier tasks</legend>{members.slice(0,i).map(prev=><label className="checkbox-label" key={prev.id}><input type="checkbox" checked={m.depends_on.includes(prev.id)} onChange={e=>edit(i,{depends_on:toggle(m.depends_on,prev.id,e.target.checked)})}/>{prev.name||prev.id}</label>)}</fieldset>}
      </section>;
    })}
    <div className="actions"><button type="button" disabled={members.length>=8} onClick={()=>{let n=members.length+1;while(members.some(m=>m.id==='step-'+n))n++;setMembers(old=>[...old,blank('step-'+n)]);setSaved(null);}}>Add agent and task</button><button type="submit" className="primary" disabled={busy||!!saved}>{busy?'Saving…':'Create team and save mission'}</button></div>
   </fieldset>
  </form>
  {saved&&<p role="status">Saved {saved.agents.length} agents and mission {saved.mission_id}. Select the mission below and launch it explicitly. No task has been queued.</p>}
 </details>;
}
