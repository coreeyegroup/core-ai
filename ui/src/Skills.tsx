import {useEffect, useRef, useState, type FormEvent} from 'react';
import {api} from './api';
import {useSession} from './Session';
import {useResource} from './Workspace';

export type SkillVersion = {repository: string; commit: string; path: string; name: string; shortened: boolean};
type Collection = {id: string; repository: string; git_ref: string; active_commit: string | null; latest_commit: string; skill_count: number | null};
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

export default function Skills({tick,refreshWorkspace}: {tick: number; refreshWorkspace:()=>void}) {
 const {role} = useSession();
 const [repository,setRepository] = useState('');
 const [ref,setRef] = useState('HEAD');
 const [selection,setSelection] = useState<{id: string; commit: string} | null>(null);
 const [revision,refresh] = useState(0);
 const [busy,setBusy] = useState(false);
 const [error,setError] = useState('');
 const [notice,setNotice] = useState('');
 const {data,error: catalogError} = useResource('skills',tick+revision);
 const rows: Collection[] = Array.isArray(data) ? data : [];
 async function action(operation: () => Promise<void>) {
  setBusy(true);setError('');setNotice('');
  try {await operation();refresh(value => value+1);}
  catch (err) {setError((err as Error).message);}
  finally {setBusy(false);}
 }
 function importSource(e: FormEvent) {
  e.preventDefault();
  void action(async () => {
   const imported = await api('skills/import','POST',{repository,ref},60000);
   setSelection({id:imported.id,commit:imported.commit});
   setNotice(`Scanned ${imported.count} skills.${imported.invalid.length ? ' Skipped: '+imported.invalid.join(', ') : ''}`);
  });
 }
 return <section className="page skills-page">
  <header className="page-head"><div><h1>Skills</h1><p>Review GitHub collections and assign them to agents.</p></div></header>
  {(error || catalogError) && <p role="alert" className="error">{error || catalogError}</p>}
  {notice && <p role="status" className="notice">{notice}</p>}
  {role === 'ADMIN' && <form className="box form" onSubmit={importSource}>
   <header>Import or check for updates</header>
   <div className="skill-import-grid">
    <label>GitHub repository<input required list="skill-repositories" value={repository} onChange={event => setRepository(event.target.value)} placeholder="owner/repository"/></label>
    <datalist id="skill-repositories">{sources.map(source => <option key={source} value={source}/>)}</datalist>
    <label>Branch, tag, or commit<input required value={ref} onChange={event => setRef(event.target.value)}/></label>
    <button className="primary" disabled={busy}>{busy ? 'Working…' : 'Scan GitHub'}</button>
   </div>
  </form>}
  <div className="skill-workspace" data-inspecting={!!selection}>
   <div className="skill-collection-list">
   <section className="box">
    <header>Collections</header>
    {rows.map(row => <button type="button" className="record" key={row.id} aria-current={selection?.id===row.id?'true':undefined} onClick={() => {
     setSelection({id:row.id,commit:row.active_commit ?? row.latest_commit});
     setRepository(row.repository);setRef(row.git_ref);
    }}><b>{row.repository}</b><span>{row.git_ref} · {row.active_commit ? `${row.skill_count} skills · ${row.active_commit.slice(0,8)}` : 'Awaiting approval'}</span>
     {row.active_commit && row.active_commit!==row.latest_commit && <small>Review available version</small>}
    </button>)}
    {rows.length===0 && <p className="empty">{data ? 'No collections yet.' : 'Loading collections…'}</p>}
   </section>
   </div>
   {selection && <CollectionDetail key={selection.id} selection={selection} changeVersion={commit => setSelection({...selection,commit})}
     tick={tick+revision} editable={role==='ADMIN'} busy={busy} action={action}/>}
   {role!=='VIEWER' && <Assignments rows={rows} tick={tick+revision} refreshWorkspace={refreshWorkspace}/>}
  </div>
 </section>;
}

function CollectionDetail({selection,changeVersion,tick,editable,busy,action}: {
 selection: {id: string; commit: string}; changeVersion: (commit:string)=>void; tick:number;
 editable:boolean; busy:boolean; action:(operation:()=>Promise<void>)=>Promise<void>;
}) {
 const {data,error} = useResource(`skills/collections/${selection.id}?commit=${encodeURIComponent(selection.commit)}`,tick);
 const [search,setSearch] = useState('');
 const [preview,setPreview] = useState('');
 const previewPanel = useRef<HTMLElement>(null);
 useEffect(() => {if (preview) previewPanel.current?.focus();},[preview]);
 const item: Detail | null = data?.commit===selection.commit ? data : null;
 if (!item) return <section className="box settings-content skill-detail">{error ? <p role="alert">{error}</p> : 'Loading collection…'}</section>;
 const visible = item.skills.filter(skill => (skill.name+' '+skill.description).toLowerCase().includes(search.trim().toLowerCase()));
 const activate = () => void action(async () => {
  await api(`skills/collections/${item.id}/activate`,'PUT',{commit:item.commit,expected_commit:item.active_commit});
 });
 return <section className="box skill-detail">
  <header>{item.repository}</header>
  <div className="settings-content">
   {error && <p role="alert">{error}</p>}
   <div className="actions skill-import">
    <label>Version<select aria-label="Collection version" value={item.commit} onChange={event => {setPreview('');changeVersion(event.target.value);}}>
     {item.releases.map(release => <option key={release.commit_sha} value={release.commit_sha}>{release.commit_sha.slice(0,8)} · {release.skill_count} skills{item.active_commit===release.commit_sha ? ' · active' : ''}</option>)}
    </select></label>
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

function Assignments({rows,tick,refreshWorkspace}: {rows: Collection[];tick: number;refreshWorkspace:()=>void}) {
 const [revision,refresh] = useState(0);
 const {data,error} = useResource('agents',tick+revision);
 const [agent,setAgent] = useState('');
 const [creating,setCreating] = useState(false);
 const [busy,setBusy] = useState(false);
 const [failure,setFailure] = useState('');
 async function create(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  const form = new FormData(event.currentTarget);
  setBusy(true);setFailure('');
  try {
   const result = await api('agents','POST',{name:form.get('name'),instructions:form.get('instructions')});
   setAgent(result.id);setCreating(false);refresh(value=>value+1);refreshWorkspace();
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
  <label>Agent<select value={agent} onChange={event=>setAgent(event.target.value)}>
   <option value="">Select an agent</option>
   {Array.isArray(data) && data.map((item:{id:string;name:string})=><option key={item.id} value={item.id}>{item.name}</option>)}
  </select></label>
  {agent && <AgentCollections key={agent} agent={agent} rows={rows}/>}
 </section>;
}

function AgentCollections({agent,rows}: {agent:string;rows:Collection[]}) {
 const {data,error} = useResource('skills/agents/'+agent,0);
 const [draft,setDraft] = useState<string[] | null>(null);
 const [busy,setBusy] = useState(false);
 const [status,setStatus] = useState('');
 const [failure,setFailure] = useState('');
 useEffect(() => {if (Array.isArray(data)) setDraft(data);},[data]);
 if (!draft) return <p>{error || 'Loading assignments…'}</p>;
 return <form onSubmit={async event => {
  event.preventDefault();setBusy(true);setStatus('');setFailure('');
  try {await api('skills/agents/'+agent,'PUT',{collections:draft});setStatus('Assignments saved.');}
  catch (err) {setFailure((err as Error).message);}
  finally {setBusy(false);}
 }}>
  <fieldset disabled={busy}><legend>Collections</legend>
   <div className="skill-assignment">{rows.map(row => <label key={row.id}>
    <input type="checkbox" checked={draft.includes(row.id)} onChange={event=>{
     setStatus('');setDraft(event.target.checked?[...draft,row.id]:draft.filter(id=>id!==row.id));
    }}/>{row.repository} · {row.git_ref}{!row.active_commit && ' · awaiting approval'}
   </label>)}</div>
  </fieldset>
  <button className="primary" disabled={busy}>Save assignment</button>
  {status && <p role="status">{status}</p>}
  {failure && <p role="alert">{failure}</p>}
 </form>;
}
