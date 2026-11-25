import {useEffect,useState} from 'react';
import {api} from './api';
import {useSession} from './Session';
type Row={id:string;digest:string;draft:{name:string;instructions:string;tools:string[];program_scope:string[]};agent_id?:string;qualification_version?:number;current_version?:number;reviewer_notes?:string;agent_enabled?:boolean};
export default function AgentFactory({tick}:{tick:number}){
 const readonly=useSession().role==='VIEWER';
 const [rows,setRows]=useState<Row[]>([]),[source,setSource]=useState(''),[selected,setSelected]=useState<Row|null>(null),[test,setTest]=useState(''),[notes,setNotes]=useState(''),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 async function refresh(){const d=await api('agent-factory');if(Array.isArray(d)){setRows(d);setSelected(old=>d.find(r=>r.id===old?.id)||old);}}
 useEffect(()=>{void refresh().catch(()=>{});},[tick]);
 async function action(kind:'draft'|'publish'|'qualify'){setBusy(true);setError('');try{
  if(kind==='draft'){const r=await api('agent-factory/drafts','POST',{run_id:source});setSelected(r);}
  else if(selected&&kind==='publish'){if(!window.confirm('Publish this reviewed exact draft as a disabled agent?'))return;await api('agent-factory/drafts/'+selected.id+'/publish','POST',{digest:selected.digest});}
  else if(selected&&kind==='qualify')await api('agent-factory/drafts/'+selected.id+'/qualify','POST',{run_id:test,notes});
  await refresh();
 }catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 return <details className="box"><summary>Agent factory · reviewed generated agents</summary>
  <p>Run an agent task requesting a JSON draft with name, instructions, runtime_mode, tools and program_scope (exact recipe IDs). Review the draft, publish disabled, enable in Agents, then run a test in the same project.</p>
  {error&&<div className="error" role="alert">{error}</div>}
  <div className="form"><label>Successful source task ID<input value={source} onChange={e=>setSource(e.target.value)} disabled={readonly||busy}/></label><button disabled={readonly||busy||!source.trim()} onClick={()=>void action('draft')}>Review generated draft</button>
  <label>Saved factory record<select value={selected?.id||''} onChange={e=>setSelected(rows.find(r=>r.id===e.target.value)||null)}><option value="">Select draft</option>{rows.map(r=><option key={r.id} value={r.id}>{r.draft.name}</option>)}</select></label>
  {selected&&<><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'20rem',overflow:'auto'}}>{JSON.stringify(selected.draft,null,2)}</pre><small>Review digest: {selected.digest}</small>{!selected.agent_id?<button disabled={readonly||busy} onClick={()=>void action('publish')}>Publish disabled agent</button>:<><p>Agent {selected.agent_id} · {selected.agent_enabled?'Enabled':'Disabled'} · {selected.qualification_version&&selected.qualification_version===selected.current_version?'Current version has reviewed test evidence':'Current version not reviewed'}</p><label>Successful qualification task ID<input value={test} onChange={e=>setTest(e.target.value)}/></label><label>Reviewer notes<textarea rows={3} value={notes} onChange={e=>setNotes(e.target.value)}/></label><button disabled={readonly||busy||!test.trim()||!notes.trim()} onClick={()=>void action('qualify')}>Record reviewed test</button>{selected.reviewer_notes&&<p>{selected.reviewer_notes}</p>}</>}</>}
  </div>
 </details>;
}
