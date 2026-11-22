import {useEffect, useRef, useState, type FormEvent} from 'react';
import {api} from './api';
import {useSession} from './Session';
import {useResource} from './Workspace';
import type {View} from './layout';

export type SkillVersion = {repository: string; commit: string; path: string; name: string; shortened: boolean};
export type Collection = {id: string; repository: string; git_ref: string; active_commit: string | null; latest_commit: string; skill_count: number | null};
type Skill = {name: string; path: string; description: string; license: string; compatibility: string; 'allowed-tools': string; scripts: boolean; references: string[]};
type Detail = Collection & {
 commit: string;
 releases: {commit_sha: string; imported_at: string; skill_count: number}[];
 skills: Skill[];
 excluded: string[];
 changes: {added: string[]; removed: string[]; changed: string[]};
};

const sources = ['obra/superpowers', 'mattpocock/skills', 'anthropics/skills', 'openai/skills'];
function sourceUrl(repository: string, commit: string, path: string) {
 return `https://github.com/${repository}/blob/${commit}/${path.split('/').map(encodeURIComponent).join('/')}`;
}

export function SkillVersions({versions}: {versions?: SkillVersion[]}) {
 if (!versions?.length) return null;
 return <details className="skill-used">
  <summary><strong>Skills used</strong> · {versions.map(skill => skill.name).join(', ')}</summary>
  <ul>{versions.map(skill => <li key={skill.repository + skill.commit + skill.path}>
   <a href={sourceUrl(skill.repository,skill.commit,skill.path)} target="_blank" rel="noreferrer">{skill.name} · {skill.commit.slice(0,8)}</a>
   {skill.shortened && ' · excerpt'}
  </li>)}</ul>
 </details>;
}

export default function Skills({tick,refreshWorkspace,go}: {tick: number; refreshWorkspace:()=>void; go:(view:View)=>void}) {
 const {role} = useSession();
 const [step,setStep] = useState<'import'|'review'|'assign'|null>(null);
 const [query,setQuery] = useState('');
 const [pendingOnly,setPendingOnly] = useState(false);
 const [repository,setRepository] = useState('');
 const [ref,setRef] = useState('HEAD');
 const [selection,setSelection] = useState<{id: string; commit: string} | null>(null);
 const [revision,refresh] = useState(0);
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 const [scan,setScan] = useState<{count:number;invalid:string[]}|null>(null);
 const {data,error: catalogError} = useResource('skills',tick+revision);
 const rows: Collection[] = Array.isArray(data) ? data : [];
 const canImport = role==='ADMIN';
 const shown = step ?? (canImport && data && !rows.length ? 'import' : 'review');
 const activeCount = rows.filter(row=>row.active_commit).length;
 const pendingCount = rows.filter(row=>row.active_commit!==row.latest_commit).length;
 const filtered = rows.filter(row=>row.repository.toLowerCase().includes(query.trim().toLowerCase()) &&
  (!pendingOnly || row.active_commit!==row.latest_commit));
 async function action(operation: () => Promise<void>) {
  setBusy(true);setError('');
  try {await operation();refresh(value => value+1);}
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
   setScan({count:imported.count,invalid:imported.invalid});
  });
 }
 return <section className="page skills-page">
  <header className="page-head"><div><h1>Skills</h1><p>Import a collection, review its skills, then attach it to an agent.</p></div>
   <button type="button" onClick={()=>go('Agents')}>Open Agents</button>
  </header>
  <nav className="skill-steps" aria-label="Skills workflow">
   {canImport && <button type="button" aria-current={shown==='import'?'step':undefined} disabled={busy} onClick={()=>setStep('import')}>1. Import</button>}
   <button type="button" aria-current={shown==='review'?'step':undefined} disabled={busy} onClick={()=>setStep('review')}>{canImport?'2. ':''}Review collections</button>
   {role!=='VIEWER' && <button type="button" aria-current={shown==='assign'?'step':undefined} disabled={busy} onClick={()=>setStep('assign')}>{canImport?'3. ':''}Assign to an agent</button>}
  </nav>
  {(error || catalogError) && <p role="alert" className="error">{error || catalogError}</p>}
  {scan && shown==='review' && <div className="notice">
   <span role="status">Scanned {scan.count} {scan.count===1?'skill':'skills'}. Review the collection below.</span>
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
    <header>Collections <span>{activeCount} active · {pendingCount} to review</span></header>
    <div className="skill-filters">
     <input type="search" aria-label="Find collections" value={query} onChange={event=>setQuery(event.target.value)} placeholder="Find collection…"/>
     <label><input type="checkbox" checked={pendingOnly} onChange={event=>setPendingOnly(event.target.checked)}/> Needs review</label>
    </div>
    <div className="skill-index">{filtered.map(row => <button type="button" className="record" key={row.id}
     disabled={busy} aria-current={selection?.id===row.id?'true':undefined} onClick={() => {
      setScan(null);setSelection({id:row.id,commit:row.latest_commit});
      setRepository(row.repository);setRef(row.git_ref);
     }}><b>{row.repository}</b><span>{row.active_commit ? `${row.skill_count} active skills` : 'Awaiting approval'}</span>
     {row.active_commit && row.active_commit!==row.latest_commit && <small>Update awaiting review</small>}
    </button>)}</div>
    {filtered.length===0 && <p className="empty">{data ? rows.length ? 'No matching collections.' : 'No collections yet.' : 'Loading collections…'}</p>}
   </section></div>
   {selection ? <CollectionDetail key={selection.id} selection={selection} changeVersion={commit => setSelection({...selection,commit})}
    tick={tick+revision} editable={canImport} busy={busy} action={action} next={role==='VIEWER'?undefined:()=>setStep('assign')}
    rescan={canImport?()=>{setRepository(rows.find(row=>row.id===selection.id)?.repository??repository);setRef(rows.find(row=>row.id===selection.id)?.git_ref??ref);setStep('import');}:undefined}/>
    : <section className="box settings-content"><h2>Review a collection</h2><p>Select a collection to inspect its skills and version. Pending versions become available for use after activation.</p></section>}
  </div>}
  {role!=='VIEWER' && <div hidden={shown!=='assign'}>
   <Assignments rows={rows} tick={tick+revision} refreshWorkspace={refreshWorkspace} go={go}/>
  </div>}
 </section>;
}

function CollectionDetail({selection,changeVersion,tick,editable,busy,action,next,rescan}: {
 selection: {id: string; commit: string}; changeVersion: (commit:string)=>void; tick:number;
 next?:()=>void; rescan?:()=>void; editable:boolean; busy:boolean; action:(operation:()=>Promise<void>)=>Promise<void>;
}) {
 const {data,error} = useResource(`skills/collections/${selection.id}?commit=${encodeURIComponent(selection.commit)}`,tick);
 const [search,setSearch] = useState('');
 const [preview,setPreview] = useState('');
 const [activated,setActivated] = useState('');
 const previewPanel = useRef<HTMLElement>(null);
 useEffect(() => {if (preview) previewPanel.current?.focus();},[preview]);
 const item: Detail | null = data?.commit===selection.commit ? data : null;
 if (!item) return <section className="box settings-content skill-detail">{error ? <p role="alert">{error}</p> : 'Loading collection…'}</section>;
 const visible = item.skills.filter(skill => (skill.name+' '+skill.description).toLowerCase().includes(search.trim().toLowerCase()));
 const activate = () => void action(async () => {
  await api(`skills/collections/${item.id}/activate`,'PUT',{commit:item.commit,expected_commit:item.active_commit});
  setActivated(item.commit);
 });
 return <section className="box skill-detail">
  <header>{item.repository}<span>{item.commit===item.active_commit?'Active version':'Review version'}</span></header>
  <div className="settings-content">
   {error && <p role="alert">{error}</p>}
   {activated===item.commit && item.commit===item.active_commit && <p role="status">Collection activated. Continue to assign it to an agent.</p>}
   <div className="actions skill-import">
    <label>Version<select aria-label="Collection version" value={item.commit} onChange={event => {setPreview('');changeVersion(event.target.value);}}>
     {item.releases.map(release => <option key={release.commit_sha} value={release.commit_sha}>{release.commit_sha.slice(0,8)} · {release.skill_count} skills{item.active_commit===release.commit_sha ? ' · active' : ''}</option>)}
    </select></label>
    {rescan && <button disabled={busy} onClick={rescan}>Check for updates</button>}
    {next && item.commit===item.active_commit && <button className="primary" onClick={next}>Continue to assignment</button>}
    {editable && item.commit!==item.active_commit && <button disabled={busy} className="primary" onClick={activate}>Approve and activate</button>}
   </div>
   {item.commit!==item.active_commit && <details>
    <summary>{item.changes.added.length} added · {item.changes.changed.length} changed · {item.changes.removed.length} removed</summary>
    {Object.entries(item.changes).map(([label,paths]) => paths.length>0 && <p key={label}><b>{label}</b> {paths.join(', ')}</p>)}
   </details>}
   <label>Filter skills<input type="search" value={search} onChange={event=>setSearch(event.target.value)} placeholder="Name or description"/></label>
   <div className="table-scroll skill-table">
    <table><thead><tr><th scope="col">Skill</th><th scope="col">Requirements</th>{editable && <th scope="col">Include</th>}</tr></thead>
    <tbody>{visible.map(skill => {
     const included = !item.excluded.includes(skill.path);
     return <tr key={skill.path}>
      <td><button className="link" aria-expanded={preview===skill.path} onClick={() => setPreview(preview===skill.path?'':skill.path)}>{skill.name}</button><small className="skill-description">{skill.description}</small></td>
      <td>{skill.scripts || skill['allowed-tools'] ? 'Instructions only · external tools or scripts' : 'Instructions'}{skill.references.length>0 && <small className="skill-description"> · source resources</small>}</td>
      {editable && <td><input type="checkbox" aria-label={'Include '+skill.name} checked={included} disabled={busy} onChange={event => {
       const excluded = !event.target.checked;
       void action(async () => {await api(`skills/collections/${item.id}/exclusion`,'PUT',{path:skill.path,excluded});});
      }}/></td>}
     </tr>;
    })}</tbody></table>
   </div>
   {visible.length===0 && <p>No matching skills.</p>}
   {item.skills.filter(skill=>skill.path===preview).map(skill=><section key={skill.path} className="skill-preview" ref={previewPanel} tabIndex={-1}>
    <h2>{skill.name}</h2>
    <p><a href={sourceUrl(item.repository,item.commit,skill.path)} target="_blank" rel="noreferrer">View pinned source</a> · License {skill.license || 'check repository'}</p>
    {skill.compatibility && <p>{skill.compatibility}</p>}
    {skill['allowed-tools'] && <p>Declared tools <code>{skill['allowed-tools']}</code></p>}
    <p>To select explicitly, start your task with <code>/skill {item.repository}:{skill.name}</code>.</p>
    {skill.references.length>0 && <details><summary>Source resources</summary><ul>{skill.references.map(path => <li key={path}>
     <a href={sourceUrl(item.repository,item.commit,skill.path.replace(/SKILL\.md$/,path))} target="_blank" rel="noreferrer">{path}</a>
    </li>)}</ul></details>}
    <SkillBody key={skill.path} path={`skills/collections/${item.id}/skill?commit=${item.commit}&path=${encodeURIComponent(skill.path)}`}/>
   </section>)}
  </div>
 </section>;
}

function SkillBody({path}: {path:string}) {
 const {data,error} = useResource(path);
 return error ? <p role="alert">{error}</p> : <pre>{data?.body ?? 'Loading instructions…'}</pre>;
}

function Assignments({rows,tick,refreshWorkspace,go}: {rows: Collection[];tick: number;refreshWorkspace:()=>void;go:(view:View)=>void}) {
 const [revision,refresh] = useState(0);
 const {data,error} = useResource('agents',tick+revision);
 const [agent,setAgent] = useState('');
 const chosen = Array.isArray(data)?data.find(item=>item.id===agent):undefined;
 const [creating,setCreating] = useState(false);
 const [dirty,setDirty] = useState(false);
 const [busy,setBusy] = useState(false);
 const [failure,setFailure] = useState('');
 async function create(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  if (dirty && !window.confirm('Discard unsaved collection changes?')) return;
  setBusy(true);setFailure('');
  try {
   const result = await api('agents','POST',{name:form.get('name'),instructions:form.get('instructions')});
   setAgent(result.id);setDirty(false);setCreating(false);refresh(value=>value+1);refreshWorkspace();
  } catch (err) {setFailure((err as Error).message);}
  finally {setBusy(false);}
 }
 return <section className="box form skill-assignments">
  <header className="skill-section-heading"><span>Assign collections to an agent</span>
   <button type="button" disabled={busy} aria-expanded={creating} onClick={()=>{setCreating(value=>!value);setFailure('');}}>{creating?'Cancel':'New agent'}</button>
  </header>
  {creating && <form className="skill-agent-form" onSubmit={create}>
   <label>Agent name<input name="name" required maxLength={120} autoFocus/></label>
   <label>Instructions<textarea name="instructions" required maxLength={16000} rows={3}/></label>
   {failure && <p role="alert" className="error">{failure}</p>}
   <button className="primary" disabled={busy}>{busy?'Creating…':'Create agent'}</button>
  </form>}
  {error && <p role="alert">{error}</p>}
  <label>Agent<select value={agent} onChange={event=>{if (!dirty || window.confirm('Discard unsaved collection changes?')) {setAgent(event.target.value);setDirty(false);}}}>
   <option value="">Select an agent</option>
   {Array.isArray(data) && data.map((item:{id:string;name:string})=><option key={item.id} value={item.id}>{item.name}</option>)}
  </select></label>
  {agent && <AgentCollections key={agent} agent={agent} rows={rows} tick={tick} onDirtyChange={setDirty} onSaved={chosen?.enabled?()=>go('Chat'):undefined}/>}
  {!agent && <p className="panel-note">Choose an agent or create one. You can assign an active collection to more than one agent.</p>}
 </section>;
}

export function AgentCollections({agent,rows,tick,readonly=false,onDirtyChange,onSaved,onReview}: {
 agent:string;rows:Collection[];tick:number;readonly?:boolean;onDirtyChange:(dirty:boolean)=>void;onSaved?:()=>void;onReview?:()=>void;
}) {
 const {data,error} = useResource('skills/agents/'+agent,tick);
 const [saved,setSaved] = useState<string[] | null>(null);
 const [draft,setDraft] = useState<string[] | null>(null);
 const [filter,setFilter] = useState('');
 const [busy,setBusy] = useState(false);
 const [status,setStatus] = useState('');
 const [failure,setFailure] = useState('');
 useEffect(() => {if (Array.isArray(data)) setSaved(data);},[data]);
 const selected = draft??saved;
 if (!selected) return <p role={error?'alert':undefined}>{error || 'Loading assignments…'}</p>;
 const active = rows.filter(row=>readonly?selected.includes(row.id):row.active_commit || selected.includes(row.id) || saved?.includes(row.id));
 const available = active.filter(row=>row.repository.toLowerCase().includes(filter.trim().toLowerCase()))
  .sort((a,b)=>Number(saved?.includes(b.id))-Number(saved?.includes(a.id)));
 return <form className="collection-assignment-form" onSubmit={async event => {
  event.preventDefault();
  if (readonly || !draft) return;
  setBusy(true);setStatus('');setFailure('');
  try {
   await api('skills/agents/'+agent,'PUT',{collections:draft});
   setSaved(draft);setDraft(null);onDirtyChange(false);setStatus('Assignments saved.');
  } catch (err) {setFailure((err as Error).message);}
  finally {setBusy(false);}
 }}>
  <fieldset className="tool-permissions" disabled={busy}><legend>Collections · {selected.length} selected</legend>
   {active.length>0 && <input type="search" aria-label="Find assignable collections" placeholder="Find collection…" value={filter} onChange={event=>setFilter(event.target.value)}/>}
   {!available.length && <p>{active.length?'No matching collections.':readonly?'No collections assigned.':'Activate a collection in Skills before assigning it.'}</p>}
   <div className="skill-assignment">{available.map(row => <label key={row.id}>
    <input type="checkbox" disabled={readonly} checked={selected.includes(row.id)} onChange={event=>{
     const next = event.target.checked?[...selected,row.id]:selected.filter(id=>id!==row.id);
     const changed = next.length!==saved?.length || next.some(id=>!saved?.includes(id));
     setStatus('');setDraft(changed?next:null);onDirtyChange(changed);
    }}/><span>{row.repository}<small>{row.git_ref}{!row.active_commit && ' · awaiting approval'}</small></span>
   </label>)}</div>
  </fieldset>
  {!readonly && <div className="actions">
   {active.length>0 && <button className="primary" disabled={busy||!draft}>{busy?'Saving…':'Save assignment'}</button>}
   {onReview && <button type="button" onClick={onReview}>Review collections in Skills</button>}
  </div>}
  {status && <div className="actions"><p role="status">{status}{onSaved&&' Select this agent in Chat → Advanced.'}</p>
   {onSaved && <button type="button" onClick={onSaved}>Open Chat</button>}</div>}
  {(failure||error) && <p className="error" role="alert">{failure||error}</p>}
 </form>;
}
