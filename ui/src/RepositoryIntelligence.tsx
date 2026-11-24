import {useState,type FormEvent} from 'react';
import {api} from './api';
import {useResource} from './Workspace';

type FileEntry={path:string;kind:string;size:number;has_excerpt:boolean};
type Capability={
 name:string;kind:string;decision:string;reason:string;sources:string[];prerequisites:string[];
 permissions:string[];license_notes:string;steps:{instruction:string;command:string;source:string}[];
 test_input:string;expected_result:string;
};
type Check={capability_index:number;state:string;evidence:string;checked_at:string};
type Assessment={
 id:string;model:string;commit_sha:string;evidence_paths:{path:string;truncated:boolean}[];
 report:{summary:string;capabilities:Capability[];open_questions:string[]};verification:Check[];
};
const pageSize=40;

export default function RepositoryIntelligence({collection,repository,commit,tick,manage,rescan}:{
 collection:string;repository:string;commit:string;tick:number;manage:boolean;rescan?:()=>void;
}){
 const [open,setOpen]=useState(false);
 return <details className="catalog-profile repo-intelligence" onToggle={event=>setOpen(event.currentTarget.open)}>
  <summary>Repository Intelligence</summary>
  {open&&<IntelligencePanel collection={collection} repository={repository} commit={commit} tick={tick} manage={manage} rescan={rescan}/>}
 </details>;
}

function IntelligencePanel({collection,repository,commit,tick,manage,rescan}:{
 collection:string;repository:string;commit:string;tick:number;manage:boolean;rescan?:()=>void;
}){
 const [query,setQuery]=useState(''),[kind,setKind]=useState(''),[page,setPage]=useState(0);
 const [picked,setPicked]=useState<string[]>([]),[file,setFile]=useState('');
 const [focus,setFocus]=useState(''),[model,setModel]=useState(''),[reportId,setReportId]=useState('');
 const [busy,setBusy]=useState(false),[failure,setFailure]=useState(''),[revision,refresh]=useState(0);
 const root=`skills/collections/${collection}/intelligence`;
 const queryString=new URLSearchParams({commit,q:query,kind,offset:String(page*pageSize),limit:String(pageSize)});
 const {data,error}=useResource(root+'?'+queryString,tick+revision);
 const {data:fileDetail,error:fileError}=useResource(file?root+'/file?'+new URLSearchParams({commit,path:file}):'',tick);
 const current=reportId||data?.reports?.[0]?.id;
 const {data:assessment,error:reportError}=useResource(current?root+'/reports/'+current:'',tick+revision);
 const report:Assessment|undefined=assessment?.id===current?assessment:undefined;
 const source=(path:string)=>`https://github.com/${repository}/blob/${commit}/${path.split('/').map(encodeURIComponent).join('/')}`;
 async function analyse(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setBusy(true);setFailure('');
  try{
   const result=await api(root+'/analyse?'+new URLSearchParams({commit}),'POST',{focus,model:model||undefined,paths:picked},130_000);
   setReportId(result.id);refresh(n=>n+1);
  }catch(err){setFailure((err as Error).message);}
  finally{setBusy(false);}
 }
 return <div className="stack">
  {(failure||error||reportError)&&<p role="alert" className="error">{failure||error||reportError}</p>}
  {!data&&!error&&<p role="status">Loading repository inventory…</p>}
  {data&&!data.available&&<p>This version predates inventory capture. {rescan&&<button type="button" onClick={rescan}>Rescan this commit</button>}</p>}
  {data?.available&&<>
   <p>{data.file_count} files · Commit <code>{commit}</code></p>
   <div className="fields">
    <label>Find files<input type="search" value={query} onChange={event=>{setQuery(event.target.value);setPage(0);}}/></label>
    <label>File type<select value={kind} onChange={event=>{setKind(event.target.value);setPage(0);}}>
     <option value="">All types</option>{data.kinds.map((value:string)=><option key={value}>{value}</option>)}
    </select></label>
   </div>
   <ul className="catalog-records" aria-label="Repository inventory">
    {(data.files as FileEntry[]).map(entry=><li key={entry.path} className="catalog-record">
     <div className="catalog-record-copy">
      <button type="button" className="link" aria-expanded={file===entry.path} onClick={()=>setFile(file===entry.path?'':entry.path)}>{entry.path}</button>
      <small>{entry.kind} · {entry.size} bytes{entry.has_excerpt?' · text excerpt':''}</small>
     </div>
     {manage&&entry.has_excerpt&&<label className="checkbox-label"><input type="checkbox" checked={picked.includes(entry.path)}
      disabled={busy||(!picked.includes(entry.path)&&picked.length>=12)}
      onChange={event=>setPicked(event.target.checked?[...picked,entry.path]:picked.filter(path=>path!==entry.path))}/> Use as evidence</label>}
    </li>)}
   </ul>
   {data.total===0&&<p>No matching files.</p>}
   {data.total>pageSize&&<div className="actions">
    <button type="button" disabled={page===0} onClick={()=>setPage(page-1)}>Previous files</button>
    <span>Page {page+1} of {Math.ceil(data.total/pageSize)}</span>
    <button type="button" disabled={(page+1)*pageSize>=data.total} onClick={()=>setPage(page+1)}>Next files</button>
   </div>}
   {file&&<section className="catalog-inline-editor">
    <h3>{file}</h3><a href={source(file)} target="_blank" rel="noreferrer">View pinned source</a>
    {fileError&&<p role="alert">{fileError}</p>}
    {fileDetail?.path===file?<><pre>{fileDetail.text||'No stored text excerpt for this file.'}</pre>
     {fileDetail.truncated&&<p>Excerpt shortened. Use the pinned source for the complete file.</p>}</>:!fileError&&<p>Loading preview…</p>}
   </section>}
   {manage&&<form className="stack catalog-inline-editor" onSubmit={analyse}>
    <h3>Repository Integration Analyst</h3>
    <label>Analysis focus (optional)<textarea rows={2} maxLength={2000} value={focus} onChange={event=>setFocus(event.target.value)} disabled={busy}/></label>
    <label>Model (optional)<input maxLength={120} placeholder="Workspace default" value={model} onChange={event=>setModel(event.target.value)} disabled={busy}/></label>
    <p>{picked.length?picked.length+' of 12 evidence files selected.':'Core AI will choose evidence files from the inventory.'}</p>
    <div className="actions"><button className="primary" disabled={busy}>{busy?'Analysing…':'Analyse repository'}</button>
     {picked.length>0&&<button type="button" disabled={busy} onClick={()=>setPicked([])}>Clear evidence selection</button>}</div>
   </form>}
  </>}
  {!!data?.reports?.length&&<label>Saved assessment<select value={current??''} onChange={event=>setReportId(event.target.value)}>
   {data.reports.map((item:{id:string;focus:string;model:string;created_at:string})=><option key={item.id} value={item.id}>
    {new Date(item.created_at).toLocaleString()} · {item.focus||item.model}
   </option>)}
  </select></label>}
  {current&&!report&&!reportError&&<p role="status">Loading assessment…</p>}
  {report&&<section className="stack">
   <h3>Capability assessment</h3>
   <p>{report.report.summary}</p>
   <p>Model {report.model}. Proposed commands are unrun.</p>
   <details><summary>Evidence used ({report.evidence_paths.length})</summary><ul>{report.evidence_paths.map(item=><li key={item.path}>
    <a href={source(item.path)} target="_blank" rel="noreferrer">{item.path}</a>{item.truncated?' · excerpt shortened':''}
   </li>)}</ul></details>
   {report.report.capabilities.map((item,index)=><article className="catalog-inline-editor stack" key={report.id+':'+index}>
    <h3>{item.name}</h3><strong>{item.decision} · {item.kind}</strong><p>{item.reason}</p>
    <ul>{item.sources.map(path=><li key={path}><a href={source(path)} target="_blank" rel="noreferrer">{path}</a></li>)}</ul>
    <p>Prerequisites {item.prerequisites.join(' · ')||'None documented'}</p>
    <p>Permissions {item.permissions.join(' · ')||'None documented'}</p>
    {item.license_notes&&<p>{item.license_notes}</p>}
    {item.steps.length>0&&<ol>{item.steps.map((step,i)=><li key={i}>{step.instruction}
     {step.command&&<pre>{step.command}</pre>}
     <a href={source(step.source)} target="_blank" rel="noreferrer">{step.source}</a>
    </li>)}</ol>}
    <dl><dt>Test input</dt><dd>{item.test_input}</dd><dt>Expected result</dt><dd>{item.expected_result}</dd></dl>
    <Verification root={root+'/reports/'+report.id+'/verify/'+index}
     saved={report.verification.find(check=>check.capability_index===index)} manage={manage} refresh={()=>refresh(n=>n+1)}/>
   </article>)}
   {report.report.open_questions.length>0&&<div><h3>Open questions</h3><ul>{report.report.open_questions.map((question,index)=><li key={index}>{question}</li>)}</ul></div>}
  </section>}
 </div>;
}

function Verification({root,saved,manage,refresh}:{root:string;saved?:Check;manage:boolean;refresh:()=>void}){
 const [state,setState]=useState(saved?.state??'Untested'),[evidence,setEvidence]=useState(saved?.evidence??'');
 const [busy,setBusy]=useState(false),[failure,setFailure]=useState('');
 return <div className="stack">
  <p>Verification <strong>{saved?.state??'Untested'}</strong>{saved&&' · '+new Date(saved.checked_at).toLocaleString()}</p>
  {saved?.evidence&&<p>{saved.evidence}</p>}
  {manage&&<form className="stack" onSubmit={async event=>{
   event.preventDefault();setBusy(true);setFailure('');
   try{await api(root,'POST',{state,evidence});refresh();}
   catch(err){setFailure((err as Error).message);}
   finally{setBusy(false);}
  }}>
   <label>Test result<select value={state} onChange={event=>setState(event.target.value)} disabled={busy}>
    <option>Untested</option><option>Verified</option><option>Failed</option>
   </select></label>
   <label>Observed test evidence<textarea rows={2} maxLength={4000} value={evidence} onChange={event=>setEvidence(event.target.value)} disabled={busy}/></label>
   {failure&&<p role="alert">{failure}</p>}
   <div><button disabled={busy||(state!=='Untested'&&!evidence.trim())}>Record verification</button></div>
  </form>}
 </div>;
}
