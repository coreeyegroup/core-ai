import {useEffect,useState} from 'react';
import {api} from './api';
import type {View} from './layout';

type Row={kind:string;name:string;state:string;version:string;detail:string;view:View};
export default function UnifiedRegistry({tick,go,visible=true}:{tick:number;go:(view:View)=>void;visible?:boolean}){
 const [rows,setRows]=useState<Row[]>([]),[errors,setErrors]=useState<string[]>([]),[query,setQuery]=useState(''),[kind,setKind]=useState('All'),[loading,setLoading]=useState(false),[revision,refresh]=useState(0);
 useEffect(()=>{if(!visible)return;let alive=true;setLoading(true);setErrors([]);
  const sources=[
   {name:'Skills',request:api('skills'),map:(d:any):Row[]=>{if(!Array.isArray(d))throw new Error('Unavailable');return d.filter(x=>!x.deleted_at).map(x=>({kind:'Skills',name:x.repository,state:x.active_commit?'Instructions active':'Review required',version:x.active_commit||x.latest_commit||'—',detail:(x.skill_count??0)+' instruction entries · native execution separate',view:'Skills'}));}},
   {name:'Agents',request:api('agents'),map:(d:any):Row[]=>{if(!Array.isArray(d))throw new Error('Unavailable');return d.filter(x=>!x.deleted_at).map(x=>({kind:'Agents',name:x.name,state:x.enabled?'Enabled profile':'Disabled',version:'v'+x.version,detail:x.runtime_mode+' · '+(x.tools||[]).join(', '),view:'Agents'}));}},
   {name:'Models',request:api('models?catalog=true'),map:(d:any):Row[]=>{if(!Array.isArray(d?.models)||d.available===false)throw new Error('Unavailable');return d.models.map((x:any)=>({kind:'Models',name:x.name,state:Array.isArray(x.capabilities)?x.capabilities.join(', '):'Capability unverified',version:x.digest||'—',detail:'Provider catalog · not a functional benchmark',view:'Models'}));}},
   {name:'Programs and runtimes',request:api('programs','GET',undefined,50000),map:(d:any):Row[]=>{if(!Array.isArray(d?.programs))throw new Error('Unavailable');return [
    ...d.programs.map((x:any)=>({kind:x.mode==='diagnostic'?'Diagnostics':'Programs',name:x.id,state:x.state,version:x.commit,detail:x.repository+' · '+x.mode,view:'Tools' as View})),
    ...(d.native_profiles||[]).map((x:any)=>({kind:'Native profiles',name:x.profile,state:x.registration,version:x.report_id||'—',detail:'Model execution: '+x.model_execution,view:'Tools' as View})),
    ...(d.native_execution||[]).map((x:any)=>({kind:'Native profiles',name:x.profile+' · '+x.model,state:x.state,version:x.report_id||'—',detail:'Native model qualification · '+x.mode,view:'Tools' as View})),
     ...(d.packages||[]).map((x:any)=>({kind:'Package runtimes',name:x.id,state:x.state,version:x.commit,detail:x.scope||x.repo,view:'Tools' as View})),
   ];}},
  ];
  void Promise.all(sources.map(async source=>{try{return {rows:source.map(await source.request),error:null};}catch{return {rows:[],error:source.name};}})).then(result=>{if(alive){setRows(result.flatMap(x=>x.rows));setErrors(result.flatMap(x=>x.error?[x.error]:[]));setLoading(false);}});
  return()=>{alive=false;};
 },[tick,visible,revision]);
 const kinds=['All','Skills','Agents','Models','Programs','Diagnostics','Native profiles','Package runtimes'];
 const shown=rows.filter(r=>(kind==='All'||r.kind===kind)&&[r.name,r.detail,r.state].join(' ').toLowerCase().includes(query.toLowerCase()));
 return <section className="box"><header>Unified capability explorer <span>{shown.length} / {rows.length}</span><button type="button" onClick={()=>refresh(x=>x+1)}>Refresh</button></header>
  <p>Search existing capability records across the platform. Discovery does not confer permission or establish runtime qualification.</p>
  {loading&&<p role="status">Reading capability sources…</p>}{errors.length>0&&<p role="alert">Unavailable sources: {errors.join(', ')}. Other records remain visible.</p>}
  <div className="fields"><label>Type<select value={kind} onChange={e=>setKind(e.target.value)}>{kinds.map(k=><option key={k}>{k}</option>)}</select></label><label>Search<input value={query} onChange={e=>setQuery(e.target.value)}/></label></div>
  <div className="table-scroll"><table><thead><tr><th>Capability</th><th>State</th><th>Version / scope</th><th>Manage</th></tr></thead><tbody>{shown.map((r,i)=><tr key={r.kind+':'+r.name+':'+i}><td><b>{r.name}</b><p>{r.kind}</p></td><td>{r.state}</td><td>{r.version.slice(0,20)}<p>{r.detail}</p></td><td><button type="button" onClick={()=>go(r.view)}>Open {r.view}</button></td></tr>)}</tbody></table></div>
  {!loading&&!shown.length&&<p>No matching records.</p>}
 </section>;
}
