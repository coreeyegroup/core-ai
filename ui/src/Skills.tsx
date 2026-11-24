import {useEffect, useRef, useState, type FormEvent} from 'react';
import {api} from './api';
import {useSession} from './Session';
import {useResource} from './Workspace';
import type {View} from './layout';
import type {AgentHandoff,SkillSetup} from './AgentSetup';
import {collectionTitle,matchesSkill,skillPurpose,skillTitle} from './skillLabels';

export type SkillVersion = {repository: string; commit: string; path: string; name: string; shortened: boolean; customized?: boolean};
export type Collection = {id: string; repository: string; git_ref: string; active_commit: string | null; latest_commit: string; skill_count: number | null;title?:string;description?:string;deleted_at?:string|null};
type Skill = {customized?:boolean;name: string; path: string; description: string; license: string; compatibility: string; 'allowed-tools': string; scripts: boolean; references: string[]};
type RepositoryAgent = {path:string;name:string;description:string};
type Detail = Collection & {
 agent_definitions?:RepositoryAgent[];
 commit: string;
 releases: {commit_sha: string; imported_at: string; skill_count: number}[];
 skills: Skill[];
 excluded: string[];
 changes: {added: string[]; removed: string[]; changed: string[]};
};

const displayCollection=(collection:Collection)=>collection.title||collectionTitle(collection.repository);

const sources = ['obra/superpowers', 'mattpocock/skills', 'anthropics/skills', 'openai/skills'];
function sourceUrl(repository: string, commit: string, path: string) {
 return `https://github.com/${repository}/blob/${commit}/${path.split('/').map(encodeURIComponent).join('/')}`;
}

export function SkillVersions({versions}: {versions?: SkillVersion[]}) {
 if (!versions?.length) return null;
 return <details className="skill-used">
  <summary><strong>Skills used</strong> · {versions.map(skill => skillTitle(skill.name)).join(', ')}</summary>
  <ul>{versions.map(skill => <li key={skill.repository + skill.commit + skill.path}>
   <a href={sourceUrl(skill.repository,skill.commit,skill.path)} target="_blank" rel="noreferrer">{skillTitle(skill.name)} · {skill.commit.slice(0,8)}</a>
   {skill.customized && ' · customized'}{skill.shortened && ' · excerpt'}
  </li>)}</ul>
 </details>;
}

export default function Skills({tick,refreshWorkspace,go,setup,openAgents}: {tick: number; refreshWorkspace:()=>void; go:(view:View)=>void; setup?:SkillSetup; openAgents:(handoff:AgentHandoff)=>void}) {
 const {role} = useSession();
 const [step,setStep] = useState<'import'|'review'|null>(null);
 const [query,setQuery] = useState('');
 const [pendingOnly,setPendingOnly] = useState(false);
 const [showDeleted,setShowDeleted]=useState(false);
 const [repository,setRepository] = useState('');
 const [ref,setRef] = useState('HEAD');
 const [selection,setSelection] = useState<{id: string; commit: string} | null>(null);
 const [revision,refresh] = useState(0);
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 const [lifecycleNotice,setLifecycleNotice]=useState('');
 const [scan,setScan] = useState<{count:number;agentCount?:number;invalid:string[]}|null>(null);
 const {data,error: catalogError} = useResource(showDeleted?'skills?include_deleted=true':'skills',tick+revision);
 const rows: Collection[] = Array.isArray(data) ? data : [];
 const canImport = role==='ADMIN';
 const shown = step ?? (canImport && data && !rows.length ? 'import' : 'review');
 const defaultCollection = rows.find(row=>!row.deleted_at&&row.active_commit) ?? rows.find(row=>!row.deleted_at);
 const selectedCollection=selection&&rows.find(row=>row.id===selection.id);
 const opened = (selectedCollection&&(!selectedCollection.deleted_at||showDeleted)?selection:null) ?? (defaultCollection ? {id:defaultCollection.id,commit:defaultCollection.active_commit??defaultCollection.latest_commit} : null);
 const [returnToSetup,setReturnToSetup]=useState(false);
 const [targetAgent,setTargetAgent]=useState('');
 useEffect(()=>{
  if(!setup)return;
  setTargetAgent(setup.agentId??'');
  if(setup.agentId){setStep('review');setReturnToSetup(false);return;}
  if(!setup.repository||!canImport)return;
  setRepository(setup.repository);setRef(setup.collection?.git_ref??'main');
  setReturnToSetup(true);setScan(null);setError('');
  if(setup.collection){
   setSelection({id:setup.collection.id,commit:setup.collection.latest_commit});
   setStep('review');
  }else setStep('import');
 },[setup,canImport]);
 function returnToAgent(collectionId?:string){
  openAgents({collectionId,agentId:targetAgent||undefined});
  setTargetAgent('');
 }
 const activeCount = rows.filter(row=>row.active_commit&&!row.deleted_at).length;
 const pendingCount = rows.filter(row=>!row.deleted_at&&row.active_commit!==row.latest_commit).length;
 const filtered = rows.filter(row=>(showDeleted||!row.deleted_at)&&(displayCollection(row)+' '+row.repository).toLowerCase().includes(query.trim().toLowerCase()) &&
  (!pendingOnly || !row.deleted_at&&row.active_commit!==row.latest_commit));
 async function action(operation: () => Promise<void>) {
  setBusy(true);setError('');
  try {await operation();refresh(value => value+1);refreshWorkspace();}
  catch (err) {setError((err as Error).message);}
  finally {setBusy(false);}
 }
 function importSource(e: FormEvent) {
  e.preventDefault();
  void action(async () => {
   setScan(null);
   const imported = await api('skills/import','POST',{repository,ref},60000);
   setSelection({id:imported.id,commit:imported.commit});
   setStep('review');
   setScan({count:imported.count,agentCount:imported.agent_count,invalid:imported.invalid});
  });
 }
 return <section className="page skills-page">
  <header className="page-head"><div><h1>Skills</h1><p>Browse repositories, attach skills, and import existing agent definitions.</p></div>
   <div className="actions">
    {returnToSetup&&<button type="button" onClick={()=>{setReturnToSetup(false);go('Setup');}}>Back to setup</button>}
    <button type="button" onClick={()=>targetAgent?returnToAgent():go('Agents')}>{targetAgent?'Back to agent':'Open Agents'}</button>
   </div>
  </header>
  <nav className="skill-steps catalog-nav" aria-label="Skills workspace options">
   <button type="button" aria-current={shown==='review'?'step':undefined} disabled={busy} onClick={()=>setStep('review')}>Browse skills</button>
   {canImport && <button type="button" aria-current={shown==='import'?'step':undefined} disabled={busy} onClick={()=>setStep('import')}>Import or update</button>}
  </nav>
  {lifecycleNotice&&shown==='review'&&<p role="status" className="panel-note">{lifecycleNotice}</p>}
  {(error || catalogError) && <p role="alert" className="error">{error || catalogError}</p>}
  {scan && shown==='review' && <div className="notice">
   <span role="status">Scanned {scan.count} {scan.count===1?'skill':'skills'}{scan.agentCount?' and '+scan.agentCount+' agent '+(scan.agentCount===1?'definition':'definitions'):''}. Review the collection below.</span>
   {scan.invalid.length>0 && <details><summary>View {scan.invalid.length} skipped files</summary><ul>{scan.invalid.map(path=><li key={path}>{path}</li>)}</ul></details>}
  </div>}
  {canImport && shown==='import' && <form className="box form" onSubmit={importSource}>
   <header>Import from GitHub</header>
   <p>Scan a public repository or enter a new version of an existing collection. The scan opens the collection for review.</p>
   <div className="skill-import-grid">
    <label>GitHub repository<input required list="skill-repositories" value={repository} onChange={event => setRepository(event.target.value)} placeholder="owner/repository"/></label>
    <datalist id="skill-repositories">{sources.map(source => <option key={source} value={source}/>)}</datalist>
    <label>Branch, tag, or commit<input required value={ref} onChange={event => setRef(event.target.value)}/></label>
    <button className="primary" disabled={busy}>{busy ? 'Working…' : 'Scan GitHub'}</button>
   </div>
  </form>}
  {shown==='review' && <div className="skill-workspace">
   <div className="skill-collection-list"><section className="box">
    <header>Skill collections <span>{activeCount} active · {pendingCount} to review</span></header>
    <div className="skill-filters">
     <input type="search" aria-label="Find collections" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Find collection…"/>
     {canImport&&<label><input type="checkbox" checked={showDeleted} onChange={e=>{setShowDeleted(e.target.checked);if(e.target.checked)setPendingOnly(false);}}/> Show deleted</label>}
     <label><input type="checkbox" checked={pendingOnly} onChange={event=>setPendingOnly(event.target.checked)}/> Needs review</label>
    </div>
    <div className="skill-index">{filtered.map(row => <button type="button" className="record" key={row.id}
     disabled={busy} aria-current={opened?.id===row.id?'true':undefined} onClick={() => {
      setScan(null);setSelection({id:row.id,commit:pendingOnly?row.latest_commit:row.active_commit??row.latest_commit});
      setRepository(row.repository);setRef(row.git_ref);
     }}><b>{displayCollection(row)}</b>{displayCollection(row)!==row.repository && <small>{row.repository}</small>}<span>{row.git_ref} · {row.deleted_at?'Deleted':row.active_commit ? `${row.skill_count} active skills` : 'Awaiting approval'}</span>
     {row.active_commit && row.active_commit!==row.latest_commit && <small>Update awaiting review</small>}
    </button>)}</div>
    {filtered.length===0 && <p className="empty">{data ? rows.length ? 'No matching collections.' : 'No collections yet.' : 'Loading collections…'}</p>}
   </section></div>
   {opened ? <CollectionDetail key={opened.id} selection={opened} changeVersion={commit => setSelection({...opened,commit})}
    tick={tick+revision} editable={canImport} busy={busy} action={action}
    next={role==='VIEWER'?undefined:()=>returnToAgent(opened.id)}
    nextLabel={returnToSetup?'Continue setup':targetAgent?'Attach to current agent':undefined} returnToSetup={returnToSetup?()=>{setReturnToSetup(false);go('Setup');}:undefined}
    onOpenImported={agentId=>{refreshWorkspace();openAgents({agentId,section:'profile'});}}
    canCreateAgent={role!=='VIEWER'}
    onVisibilityChanged={deleted=>{
     setStep('review');setSelection(deleted&&!showDeleted?null:opened);
     setLifecycleNotice(deleted?'Collection deleted. Find it under Show deleted.':'Collection restored.');
    }}
    rescan={canImport?()=>{setRepository(rows.find(row=>row.id===opened.id)?.repository??repository);setRef(rows.find(row=>row.id===opened.id)?.git_ref??ref);setStep('import');}:undefined}/>
    : <section className="box settings-content"><h2>Review a collection</h2><p>Select a collection to inspect its skills and version. Pending versions become available for use after activation.</p></section>}
  </div>}
 </section>;
}

function CollectionDetail({selection,changeVersion,tick,editable,busy,action,next,rescan,nextLabel,returnToSetup,onVisibilityChanged,onOpenImported,canCreateAgent}: {
 selection: {id: string; commit: string}; changeVersion: (commit:string)=>void; tick:number;
 onVisibilityChanged:(deleted:boolean)=>void; onOpenImported:(id:string)=>void; canCreateAgent:boolean; next?:()=>void; nextLabel?:string; returnToSetup?:()=>void; rescan?:()=>void; editable:boolean; busy:boolean; action:(operation:()=>Promise<void>)=>Promise<void>;
}) {
 const {data,error} = useResource(`skills/collections/${selection.id}?commit=${encodeURIComponent(selection.commit)}`,tick);
 const [search,setSearch] = useState('');
 const [preview,setPreview] = useState('');
 const [editing,setEditing] = useState('');
 const [profile,setProfile]=useState<{title:string;description:string}|null>(null);
 const [activated,setActivated] = useState('');
 const previewPanel = useRef<HTMLElement>(null);
 useEffect(() => {if (preview) previewPanel.current?.focus();},[preview]);
 const item: Detail | null = data?.commit===selection.commit ? data : null;
 if (!item) return <section className="box settings-content skill-detail">{error ? <p role="alert">{error}</p> : 'Loading collection…'}</section>;
 const visible = item.skills.filter(skill => matchesSkill(skill,search)||skill.path.toLowerCase().includes(search.trim().toLowerCase()));
 const counts=new Map<string,number>();
 for(const skill of item.skills)counts.set(skill.name,(counts.get(skill.name)??0)+1);
 const activate = () => void action(async () => {
  await api(`skills/collections/${item.id}/activate`,'PUT',{commit:item.commit,expected_commit:item.active_commit});
  setActivated(item.commit);
 });
 return <section className="box skill-detail">
  <header className="catalog-heading">
   <div><strong>{displayCollection(item)}</strong><small>{item.repository} · {item.git_ref} · {item.deleted_at?'Deleted':item.commit===item.active_commit?'Active version':'Review version'}</small></div>
   {editable&&<div className="actions">
    {!item.deleted_at&&<button type="button" disabled={busy} onClick={()=>setProfile({title:item.title??'',description:item.description??''})}>Edit collection</button>}
    <button type="button" disabled={busy} className={item.deleted_at?'':'catalog-danger'} onClick={()=>{
     const restore=!!item.deleted_at;
     if(!restore&&!window.confirm('Delete this collection from use? You can restore it under Show deleted.'))return;
     void action(async()=>{await api(`skills/collections/${item.id}`+(restore?'/restore':''),restore?'POST':'DELETE');setProfile(null);setEditing('');setPreview('');onVisibilityChanged(!restore);});
    }}>{item.deleted_at?'Restore collection':'Delete collection'}</button>
   </div>}
  </header>
  <div className="settings-content">
   {error && <p role="alert">{error}</p>}
   {profile&&<form className="stack catalog-profile" onSubmit={e=>{e.preventDefault();void action(async()=>{
    await api(`skills/collections/${item.id}`,'PUT',profile);setProfile(null);
   });}}>
    <label>Collection name<input maxLength={120} placeholder={collectionTitle(item.repository)} value={profile.title} onChange={e=>setProfile({...profile,title:e.target.value})}/></label>
    <label>Description<textarea rows={3} maxLength={2000} value={profile.description} onChange={e=>setProfile({...profile,description:e.target.value})}/></label>
    <div className="actions"><button className="primary" disabled={busy}>Save collection</button><button type="button" disabled={busy} onClick={()=>setProfile(null)}>Cancel</button></div>
   </form>}
   {!profile&&item.description&&<p>{item.description}</p>}
   {item.deleted_at&&<p role="status">Deleted collections become available to assigned agents when restored.</p>}
   {activated===item.commit && item.commit===item.active_commit && <p role="status">Collection activated. {returnToSetup?'Continue setup to attach it.':'Assign it to an agent when ready.'}</p>}
   <div className="actions skill-import">
    <label>Version<select aria-label="Collection version" value={item.commit} onChange={event => {setPreview('');changeVersion(event.target.value);}}>
     {item.releases.map(release => <option key={release.commit_sha} value={release.commit_sha}>{release.commit_sha.slice(0,8)} · {release.skill_count} skills{item.active_commit===release.commit_sha ? ' · active' : ''}</option>)}
    </select></label>
    {editable && !item.deleted_at && item.commit===item.active_commit && item.latest_commit!==item.active_commit &&
     <button disabled={busy} onClick={()=>{setPreview('');changeVersion(item.latest_commit);}}>Review pending update</button>}
    {rescan && !item.deleted_at && <button disabled={busy} onClick={rescan}>Check for updates</button>}
    {next && !item.deleted_at && item.commit===item.active_commit && <button className="primary" onClick={returnToSetup??next}>{nextLabel??'Assign this collection'}</button>}
    {editable && !item.deleted_at && item.commit!==item.active_commit && <button disabled={busy} className="primary" onClick={activate}>Approve and activate</button>}
   </div>
   {item.commit!==item.active_commit && <details>
    <summary>{item.changes.added.length} added · {item.changes.changed.length} changed · {item.changes.removed.length} removed</summary>
    {Object.entries(item.changes).map(([label,paths]) => paths.length>0 && <p key={label}><b>{label}</b> {paths.join(', ')}</p>)}
   </details>}
   {(item.agent_definitions?.length??0)>0&&!item.deleted_at&&<section className="catalog-profile">
    <h2>Repository agents</h2>
    <p>Review a definition before importing it into Agents.</p>
    {item.agent_definitions?.map(definition=><RepositoryAgentReview key={item.commit+definition.path} item={item}
      definition={definition} tick={tick} canCreate={canCreateAgent} onOpen={onOpenImported}/>)}
   </section>}
   <label>Filter skills<input type="search" value={search} onChange={event=>setSearch(event.target.value)} placeholder="Task, name, or description"/></label>
   <ul className="catalog-records" aria-label="Collection skills">
    {visible.map(skill => {
     const included=!item.excluded.includes(skill.path);
     const title=skillTitle(skill.name);
     return <li key={skill.path}>
      <div className="catalog-record">
       <div className="catalog-record-copy">
        <button className="link" type="button" aria-expanded={preview===skill.path} onClick={()=>{
         setEditing('');setPreview(preview===skill.path?'':skill.path);
        }}>{title}</button>
        <p>{skillPurpose(skill.name,skill.description)}</p>
        <small>{included?skill.customized?'Locally edited':'Available':'Deleted from use'}
         {(skill.scripts||skill['allowed-tools'])?' · Instructions only':''}
         {skill.references.length>0?' · Source resources':''}</small>
        {(counts.get(skill.name)??0)>1&&<small>{skill.path}</small>}
       </div>
       {editable&&!item.deleted_at&&<div className="actions catalog-record-actions">
        <button type="button" disabled={busy} aria-label={'Edit '+title} onClick={()=>{setPreview(skill.path);setEditing(skill.path);}}>Edit</button>
        <button type="button" disabled={busy} aria-label={(included?'Delete ':'Restore ')+title} onClick={()=>{
         if(included&&!window.confirm('Delete this skill from use in the collection? You can restore it here.'))return;
         void action(async()=>{await api(`skills/collections/${item.id}/exclusion`,'PUT',{path:skill.path,excluded:included});});
        }}>{included?'Delete':'Restore'}</button>
       </div>}
      </div>
   {preview===skill.path&&<section className="skill-preview" ref={previewPanel} tabIndex={-1}>
    <h2>{skillTitle(skill.name)}</h2>
    <p>{skill.description}</p>
    <p>Source name <code>{skill.name}</code></p>
    <p><a href={sourceUrl(item.repository,item.commit,skill.path)} target="_blank" rel="noreferrer">View pinned source</a> · License {skill.license || 'check repository'}</p>
    {skill.compatibility && <p>{skill.compatibility}</p>}
    {skill['allowed-tools'] && <p>Declared tools <code>{skill['allowed-tools']}</code></p>}
    <details><summary>Use this version in Tasks</summary><p>Put this on the first line of the task instructions.</p>
    <pre><code>{`/skill ${item.repository}:${skill.name}@${item.commit}:${encodeURIComponent(skill.path)}`}</code></pre>
   </details>
    {skill.references.length>0 && <details><summary>Source resources</summary><ul>{skill.references.map(path => <li key={path}>
     <a href={sourceUrl(item.repository,item.commit,skill.path.replace(/SKILL\.md$/,path))} target="_blank" rel="noreferrer">{path}</a>
    </li>)}</ul></details>}
    {editing===skill.path
     ? <SkillEditor key={item.commit+skill.path} endpoint={skillEndpoint(`skills/collections/${item.id}/skill`,item.commit,skill.path)}
        customized={!!skill.customized} close={()=>setEditing('')} onSaved={()=>void action(async()=>{})}/>
     : <SkillBody key={skill.path} tick={tick} path={skillEndpoint(`skills/collections/${item.id}/skill`,item.commit,skill.path)}/>}
   </section>}
     </li>;
    })}
   </ul>
   {visible.length===0&&<p>No matching skills.</p>}

  </div>
 </section>;
}

function RepositoryAgentReview({item,definition,tick,canCreate,onOpen}:{
 item:Detail;definition:RepositoryAgent;tick:number;canCreate:boolean;onOpen:(id:string)=>void;
}){
 const [open,setOpen]=useState(false);
 const [busy,setBusy]=useState(false);
 const [problem,setProblem]=useState('');
 const endpoint=skillEndpoint(`skills/collections/${item.id}/agent`,item.commit,definition.path);
 const {data,error}=useResource(open?endpoint:'',tick);
 async function create(){
  setBusy(true);setProblem('');
  try{const result=await api(endpoint,'POST');onOpen(result.id);}
  catch(failure){setProblem((failure as Error).message);}
  finally{setBusy(false);}
 }
 return <details onToggle={event=>setOpen(event.currentTarget.open)} className="skill-preview">
  <summary>{definition.name}</summary>
  <p>{definition.description}</p>
  {open&&<>
   <p><a href={sourceUrl(item.repository,item.commit,definition.path)} target="_blank" rel="noreferrer">View pinned agent source</a></p>
   {error||problem?<p role="alert">{error||problem}</p>:null}
   <pre>{data?.instructions??(error?'':'Loading agent instructions…')}</pre>
   {canCreate&&<button type="button" disabled={!data||busy} onClick={()=>void create()}>{busy?'Importing…':'Import agent'}</button>}
  </>}
 </details>;
}

function SkillBody({path,tick}: {path:string;tick:number}) {
 const {data,error} = useResource(path,tick);
 return error ? <p role="alert">{error}</p> : <pre>{data?.body ?? 'Loading instructions…'}</pre>;
}

function skillEndpoint(base:string,commit:string,path:string,collectionId?:string) {
 const query=new URLSearchParams({commit,path});
 if(collectionId)query.set('collection_id',collectionId);
 return base+'?'+query;
}

function SkillEditor({endpoint,agent=false,customized,close,onSaved}: {
 endpoint:string;agent?:boolean;customized:boolean;close:()=>void;onSaved:()=>void;
}) {
 const {data,error}=useResource(endpoint);
 const [description,setDescription]=useState<string>();
 const [instructions,setInstructions]=useState<string>();
 const [busy,setBusy]=useState(false);
 const [failure,setFailure]=useState('');
 async function save(reset=false) {
  setBusy(true);setFailure('');
  try {
   const edit={description:description??data.description,body:instructions??data.body};
   if(agent)await api(endpoint,'PUT',reset?{action:'reset'}:{action:'edit',edit});
   else if(reset){const [base,query]=endpoint.split('?');await api(base+'/reset?'+query,'POST');}
   else await api(endpoint,'PUT',edit);
   onSaved();close();
  }catch(err){setFailure((err as Error).message);}
  finally{setBusy(false);}
 }
 return <form className="skill-edit-form stack" onSubmit={event=>{event.preventDefault();void save();}}>
  <p>{agent?'These edits apply to this agent.':'These edits apply to agents using this collection version unless they have their own edits.'}</p>
  {error&&<p role="alert">{error}</p>}
  {!data&&!error&&<p role="status">Loading instructions…</p>}
  {data&&<>
   <label>Description<textarea required rows={2} maxLength={1024} value={description??data.description} onChange={event=>setDescription(event.target.value)}/></label>
   <label>Skill instructions<textarea required rows={10} maxLength={64000} value={instructions??data.body} onChange={event=>setInstructions(event.target.value)}/></label>
  </>}
  {failure&&<p className="error" role="alert">{failure}</p>}
  <div className="actions">
   <button className="primary" disabled={!data||busy}>{busy?'Saving…':'Save skill'}</button>
   {customized&&<button type="button" disabled={!data||busy} onClick={()=>void save(true)}>{agent?'Reset to collection':'Reset to imported version'}</button>}
   <button type="button" disabled={busy} onClick={close}>Cancel</button>
  </div>
 </form>;
}

type AssignedSkill = {collection_id:string;commit:string;path:string;name:string;description:string;repository:string;
 collection_removed:boolean;agent_removed:boolean;agent_customized:boolean};
function AssignedSkills({agent,tick,readonly}: {agent:string;tick:number;readonly:boolean}) {
 const [revision,refresh]=useState(0);
 const {data,error}=useResource(`skills/agents/${agent}/skills`,tick+revision);
 const [query,setQuery]=useState('');
 const [edit,setEdit]=useState<AssignedSkill>();
 const [pending,setPending]=useState(false);
 const [failure,setFailure]=useState('');
 const [status,setStatus]=useState('');
 const endpoint=(skill:AssignedSkill)=>skillEndpoint(`skills/agents/${agent}/skill`,skill.commit,skill.path,skill.collection_id);
 const rows:AssignedSkill[]=Array.isArray(data)?data:[];
 const visible=rows.filter(skill=>matchesSkill(skill,query)||skill.repository.toLowerCase().includes(query.trim().toLowerCase()));
 async function change(skill:AssignedSkill) {
  if(!skill.agent_removed&&!window.confirm('Delete this skill from this agent? You can restore it here.'))return;
  setPending(true);setFailure('');setStatus('');
  try {
   await api(endpoint(skill),'PUT',{action:skill.agent_removed?'restore':'remove'});
   setStatus(skill.agent_removed?'Skill restored for this agent.':'Skill deleted from this agent.');
   refresh(value=>value+1);
  }catch(err){setFailure((err as Error).message);}
  finally{setPending(false);}
 }
 return <section className="skill-preview">
  <h2>Individual agent skills</h2>
  {error&&<p role="alert">{error}</p>}
  {!data&&!error&&<p role="status">Loading agent skills…</p>}
  {data&&rows.length===0&&<p>Assign an active collection to manage its skills here.</p>}
  {rows.length>0&&<label>Find agent skill<input type="search" value={query} onChange={event=>setQuery(event.target.value)}/></label>}
  {rows.length>0&&visible.length===0&&<p>No matching skills.</p>}
  {visible.length>0&&<ul className="catalog-records" aria-label="Individual agent skills">
   {visible.map(skill=>{
    const id=endpoint(skill);
    const title=skillTitle(skill.name);
    return <li key={id}>
     <div className="catalog-record">
      <div className="catalog-record-copy"><strong>{title}</strong>
       <p>{skill.description}</p>
       <small>{skill.repository} · {skill.agent_removed?'Deleted for agent':skill.collection_removed?'Deleted in collection':skill.agent_customized?'Edited for agent':'Available'}</small>
      </div>
      {!readonly&&<div className="actions catalog-record-actions">
       <button type="button" disabled={pending||!!edit||skill.collection_removed} aria-label={'Edit '+title} onClick={()=>{setStatus('');setEdit(skill);}}>Edit</button>
       <button type="button" disabled={pending||!!edit||(!skill.agent_removed&&skill.collection_removed)} aria-label={(skill.agent_removed?'Restore ':'Delete ')+title}
        onClick={()=>void change(skill)}>{skill.agent_removed?'Restore':'Delete'}</button>
      </div>}
     </div>
     {edit&&endpoint(edit)===id&&<div className="catalog-inline-editor"><h3>Edit {title}</h3><SkillEditor endpoint={id} agent
      customized={edit.agent_customized} close={()=>setEdit(undefined)} onSaved={()=>{setStatus('Agent skill saved.');refresh(value=>value+1);}}/></div>}
    </li>;
   })}
  </ul>}
  {failure&&<p role="alert" className="error">{failure}</p>}
  {status&&<p role="status">{status}</p>}
 </section>;
}

export function AgentCollections({agent,rows,tick,readonly=false,onDirtyChange,onReview,onSelectionSaved,onAssignmentSaved,recommendedCollection,onContinue,onBack}: {
 agent:string;rows:Collection[];tick:number;readonly?:boolean;onSelectionSaved?:(ids:string[])=>void;onAssignmentSaved?:(ids:string[])=>void;onDirtyChange?:(dirty:boolean)=>void;onReview?:()=>void;
 recommendedCollection?:string;onContinue?:()=>void;onBack?:()=>void;
}) {
 const [revision,refresh]=useState(0);
 const {data,error} = useResource('skills/agents/'+agent,tick+revision);
 const [saved,setSaved] = useState<string[] | null>(null);
 const [draft,setDraft] = useState<string[] | null>(null);
 const [filter,setFilter] = useState('');
 const [busy,setBusy] = useState(false);
 const [status,setStatus] = useState('');
 const [failure,setFailure] = useState('');
 useEffect(() => {
  if (!Array.isArray(data)) return;
  setSaved(data);onSelectionSaved?.(data);
 },[data,onSelectionSaved]);
 const selected = draft??saved;
 if (!selected) return <div className="stack">
  <p role={error?'alert':'status'}>{error || 'Loading assignments…'}</p>
  <div className="actions">{onBack&&<button type="button" onClick={onBack}>Back</button>}
   {error&&<button type="button" onClick={()=>refresh(value=>value+1)}>Retry assignments</button>}</div>
 </div>;
 const active = rows.filter(row=>readonly?selected.includes(row.id):row.active_commit || selected.includes(row.id) || saved?.includes(row.id));
 const available = active.filter(row=>(displayCollection(row)+' '+row.repository).toLowerCase().includes(filter.trim().toLowerCase()))
  .sort((a,b)=>Number(saved?.includes(b.id))-Number(saved?.includes(a.id)));
 function changeSelection(next:string[]){
  const changed=next.length!==saved?.length||next.some(id=>!saved?.includes(id));
  setStatus('');setDraft(changed?next:null);onDirtyChange?.(changed);
 }
 function back(){
  if(draft&&!window.confirm('Discard unsaved collection selections?'))return;
  if(draft){setDraft(null);onDirtyChange?.(false);}
  onBack?.();
 }
 return <><form className="collection-assignment-form" onSubmit={async event => {
  event.preventDefault();
  if(readonly||busy)return;
  if(!draft){onContinue?.();return;}
  setBusy(true);setStatus('');setFailure('');
  try {
   await api('skills/agents/'+agent,'PUT',{collections:draft});
   setSaved(draft);setDraft(null);onDirtyChange?.(false);onSelectionSaved?.(draft);onAssignmentSaved?.(draft);setStatus('Assignments saved.');
   refresh(value=>value+1);
   onContinue?.();
  } catch (err) {setFailure((err as Error).message);}
  finally {setBusy(false);}
 }}>
  <fieldset className="tool-permissions" disabled={busy}><legend>Collections · {selected.length} selected</legend>
   {active.length>0 && <div className="actions collection-filters">
    <input type="search" aria-label="Find assignable collections" placeholder="Find collection…" value={filter} onChange={event=>setFilter(event.target.value)}/>
    {recommendedCollection&&!selected.includes(recommendedCollection)&&!readonly&&<button type="button" onClick={()=>{
     setFilter('');changeSelection([...selected,recommendedCollection]);
    }}>Add recommended collection</button>}
   </div>}
   {!available.length && <p>{active.length?'No matching collections.':readonly?'No collections assigned.':'Activate a collection in Skills before assigning it.'}</p>}
   <div className="skill-assignment">{available.map(row => <label key={row.id}>
    <input type="checkbox" disabled={readonly} checked={selected.includes(row.id)} onChange={event=>
     changeSelection(event.target.checked?[...selected,row.id]:selected.filter(id=>id!==row.id))}/><span>{displayCollection(row)}<small>{row.repository} · {row.git_ref}{!row.active_commit && ' · awaiting approval'}</small></span>
   </label>)}</div>
  </fieldset>
  {onContinue&&!readonly?<div className="actions setup-footer">
   <div className="actions"><button type="button" disabled={busy} onClick={back}>Back</button>
    {onReview&&<button type="button" disabled={busy} onClick={onReview}>Browse skills catalog</button>}</div>
   <button className="primary" disabled={busy}>{busy?'Saving…':draft?'Save and continue':selected.length?'Continue with saved skills':'Continue without skills'}</button>
  </div>:!readonly && <div className="actions">
   {active.length>0 && <button className="primary" disabled={busy||!draft}>{busy?'Saving…':'Save assignment'}</button>}
   {onReview && <button type="button" onClick={onReview}>Review collections in Skills</button>}
  </div>}
  {status && !onContinue && <p role="status">{status}</p>}
  {(failure||error) && <p className="error" role="alert">{failure||error}</p>}
 </form>
 {!onContinue&&<AssignedSkills agent={agent} tick={tick+revision} readonly={readonly}/>}
 </>;
}
