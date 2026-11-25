import {useEffect,useState,type FormEvent} from 'react';
import {api} from './api';
import {useSession} from './Session';

type Program={id:string;repository:string;commit:string;runtime:string;fields:string|string[];example:unknown[];extensions:string[];output_file:boolean;mode:string;state:string;image?:string};
type Repo={repository:string;commit:string;source_present:boolean;recipes:string[];coverage:string;inventory_counts?:Record<string,number>;file_count?:number};
type Catalog={schema:number;programs:Program[];repositories:Repo[]};
type Result={id:string;recipe:string;state:string;commit:string;image:string;provenance:string;result:unknown;file?:{name:string;data:string}|null};

function encode(file:File):Promise<string>{
 return new Promise((resolve,reject)=>{
  const reader=new FileReader();
  reader.onerror=()=>reject(new Error('Unable to read file.'));
  reader.onload=()=>{const text=String(reader.result);resolve(text.slice(text.indexOf(',')+1));};
  reader.readAsDataURL(file);
 });
}
function save(name:string,data:string){
 const bytes=atob(data),buffer=new ArrayBuffer(bytes.length),view=new Uint8Array(buffer);
 for(let i=0;i<bytes.length;i++)view[i]=bytes.charCodeAt(i);
 const url=URL.createObjectURL(new Blob([buffer],{type:'application/octet-stream'}));
 const a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
export default function ProgramsPanel({tick}:{tick:number}){
 const readonly=useSession().role==='VIEWER';
 const [catalog,setCatalog]=useState<Catalog|null>(null),[loadError,setLoadError]=useState(''),[refresh,setRefresh]=useState(0);
 const [query,setQuery]=useState(''),[selected,setSelected]=useState(''),[values,setValues]=useState('[]'),[file,setFile]=useState<File|null>(null);
 const [result,setResult]=useState<Result|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useEffect(()=>{let active=true;setLoadError('');api('programs','GET',undefined,50000).then((d:Catalog)=>{if(!d||d.schema!==1||!Array.isArray(d.programs)||!Array.isArray(d.repositories)||!d.programs.every(r=>r&&typeof r.id==='string'&&typeof r.repository==='string'&&typeof r.runtime==='string'&&Array.isArray(r.example)&&Array.isArray(r.extensions)))throw new Error('Invalid program catalog response.');if(active){setCatalog(d);setLoadError('');}}).catch(e=>{if(active){setCatalog(null);setLoadError(e.message);}});return()=>{active=false;};},[tick,refresh]);
 const current=catalog?.programs.find(p=>p.id===selected);
 const qualified=catalog?.programs.filter(p=>p.state==='qualified-receipt').length??0;
 function select(p:Program){setSelected(p.id);setValues(JSON.stringify(p.example,null,2));setFile(null);setResult(null);setError('');}
 async function run(e:FormEvent){
  e.preventDefault();if(!current||busy||readonly||current.state!=='qualified-receipt')return;
  setBusy(true);setError('');setResult(null);
  try{
   const params=JSON.parse(values);
   if(!Array.isArray(params))throw new Error('Enter a JSON array of parameters.');
   let extension:null|string=null,file_data:null|string=null;
   if(current.extensions.length){
    if(!file||file.size>4*1024*1024||file.size===0)throw new Error('Choose a file of at most 4 MiB.');
    extension='.'+file.name.split('.').pop()?.toLowerCase();
    if(!current.extensions.includes(extension))throw new Error('Unsupported file type.');
    file_data=await encode(file);
   }
   setResult(await api('programs/run','POST',{recipe:current.id,values:params,extension,file_data},240000));
  }catch(e){setError((e as Error).message);}finally{setBusy(false);}
 }
 return <section className="box">
  <header>Independent executable programs <span>{catalog?qualified+' / '+catalog.programs.length+' qualified':'—'}</span><button type="button" disabled={busy} onClick={()=>setRefresh(n=>n+1)}>Refresh catalog</button></header>
  {loadError?<div className="error" role="alert">{loadError} · Check the independent gateway service.</div>:!catalog?<p role="status">Checking runtime qualification records…</p>:<>
   <p className="panel-note">Runs actual pinned software, independently of the language model. Mock research is not live evidence. No broker orders, host commands or public runtime access.</p>
   <div className="fields"><label>Filter programs<input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Name, repository or runtime"/></label></div>
   <div className="table-scroll"><table><thead><tr><th>Program</th><th>Runtime</th><th>Qualification</th><th>Action</th></tr></thead><tbody>
    {catalog.programs.filter(p=>(p.id+' '+p.repository+' '+p.runtime).toLowerCase().includes(query.toLowerCase())).map(p=><tr key={p.id}><td><b>{p.id}</b><p>{p.repository}</p></td><td>{p.runtime}</td><td>{p.mode==='mock'?'Mock · ':''}{p.state}</td><td><button disabled={busy} onClick={()=>select(p)} aria-pressed={selected===p.id}>Inspect / run</button></td></tr>)}
   </tbody></table></div>
   {current&&<form className="form" onSubmit={run} key={current.id}>
    <header>{current.id}</header><p>Source: {current.commit} · {current.state}</p>
    <p>Parameters: {Array.isArray(current.fields)?current.fields.join(', '):current.fields}</p>
    {current.extensions.length>0?<label>Document ({current.extensions.join(', ')}, max 4 MiB)<input type="file" accept={current.extensions.join(',')} disabled={busy||readonly} onChange={e=>setFile(e.target.files?.[0]??null)}/></label>:<label>JSON parameter array<textarea rows={7} value={values} disabled={busy||readonly} onChange={e=>setValues(e.target.value)} spellCheck={false}/></label>}
    <button type="button" disabled={busy} onClick={()=>setValues(JSON.stringify(current.example,null,2))}>Use qualification example</button>
    <button type="submit" className="primary" disabled={busy||readonly||current.state!=='qualified-receipt'}>{busy?'Executing…':'Run qualified program'}</button>
    {readonly&&<p>Read-only account: execution is unavailable.</p>}
   </form>}
   {error&&<div className="error" role="alert">{error}</div>}
   {busy&&<p role="status">Execution in progress. Do not submit again.</p>}
   {result&&<section className="box"><header>Execution result · {result.state}</header><p>{result.recipe} · {result.provenance} · ID {result.id}</p><pre style={{whiteSpace:'pre-wrap',overflowWrap:'anywhere',maxHeight:'30rem',overflow:'auto'}}>{JSON.stringify(result.result,null,2)}</pre>{result.file&&<button onClick={()=>save(result.file!.name,result.file!.data)}>Download new file</button>}</section>}
   <details><summary>Repository coverage ({catalog.repositories.length})</summary><div className="table-scroll"><table><thead><tr><th>Repository</th><th>Source</th><th>Source inventory</th><th>Reviewed recipes</th></tr></thead><tbody>{catalog.repositories.map(r=><tr key={r.repository}><td>{r.repository}</td><td>{r.source_present?'Verified':'Unavailable'}</td><td>{r.file_count===undefined?'—':r.file_count+' files'}{r.inventory_counts&&<p>{['program','hook','manifest','skill','agent-candidate'].map(k=>k+': '+(r.inventory_counts?.[k]??0)).join(' · ')}</p>}</td><td>{r.recipes.length} · {r.coverage}</td></tr>)}</tbody></table></div></details>
   <p className="panel-note">For agent execution, enable Tools mode and assign program.list and program.run in Agents, then launch a project task. In Chat, select the permitted agent and explicitly enable Use programs.</p>
  </>}
 </section>;
}
