import {useEffect,useRef,useState,type FormEvent} from 'react';
import {Archive,ArrowLeft,ArrowRight,Ellipsis,Folder,MessageSquare,Plus,Search} from 'lucide-react';
import {api} from './api';
import {chatModes} from './appearance';
import {ChatPopover,ConversationDialog,isTextModel} from './ChatPopover';
import Sources from './Sources';
import {ArtifactLibrary,FilesPanel,useResource} from './Workspace';
import {useSession} from './Session';

export type ProjectLocation={id:string;creating:boolean};
export const projectDirectory:ProjectLocation={id:'',creating:false};

type Project={
 id:string;name:string;description:string;instructions:string;default_model:string|null;
 default_mode:string|null;archived_at:string|null;owner_id?:string;member_role?:string;
};
type Chat={id:string;title:string;project_id:string|null;pinned:boolean;archived:boolean;updated_at:string};
const sections=['Chats','Sources','Instructions','Artifacts','Members','Settings'] as const;
const displayDate=(value:string)=>new Date(value).toLocaleString();

export default function Projects({tick,refresh,location,changeLocation}:{tick:number;refresh:()=>void;location:ProjectLocation;changeLocation:(location:ProjectLocation)=>void}){
 const {data,error}=useResource('projects',tick);
 const {id,creating}=location;
 const [archives,setArchives]=useState(false);
 const [busy,setBusy]=useState(false),[problem,setProblem]=useState(''),[query,setQuery]=useState('');
 const {role}=useSession();
 const projects:Project[]=data??[];
 const current=projects.find(project=>project.id===id);
 const directoryHeading=useRef<HTMLHeadingElement>(null),returnFocus=useRef(false);
 useEffect(()=>{
  if(!current&&!creating&&returnFocus.current){
   returnFocus.current=false;
   directoryHeading.current?.focus();
  }
 },[current,creating]);

 async function create(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setBusy(true);setProblem('');
  try{
   const body=Object.fromEntries(new FormData(event.currentTarget));
   const project=await api('projects','POST',body);
   changeLocation({id:project.id,creating:false});setArchives(false);refresh();
  }catch(e){setProblem((e as Error).message);}
  finally{setBusy(false);}
 }

 if(current&&!creating)return <section className="page project-page">
  <div className="project-content">
   <ProjectHome key={current.id} project={current} tick={tick} refresh={refresh}
    back={()=>{returnFocus.current=true;setArchives(!!current.archived_at);changeLocation(projectDirectory);}}/>
  </div>
 </section>;

 const visibleProjects=projects.filter(project=>!!project.archived_at===archives&&
  (project.name+' '+project.description).toLowerCase().includes(query.trim().toLowerCase()));
 return <section className="page project-page">
  <header className="page-head">
   <div><h1 tabIndex={-1} ref={directoryHeading}>Projects</h1><p>Keep related chats, sources, and artifacts together.</p></div>
   {!creating&&<button className="primary" disabled={role==='VIEWER'} onClick={()=>{changeLocation({id,creating:true});setProblem('');}}><Plus size={15}/>New project</button>}
  </header>
  {(problem||error)&&<div className="error" role="alert">{problem||error}</div>}
  {creating?<section className="box project-create">
   <header>New project</header>
   <form className="form" onSubmit={create}>
    <label>Name<input name="name" required maxLength={120} autoFocus/></label>
    <label>Description<textarea name="description" maxLength={4000} rows={2}/></label>
    <div className="actions"><button className="primary" disabled={busy}>Create project</button><button type="button" onClick={()=>{returnFocus.current=true;changeLocation({id,creating:false});}}>Cancel</button></div>
   </form>
  </section>:<>
   <div className="project-toolbar">
    <label className="project-search"><Search size={15} aria-hidden="true"/><input aria-label="Search projects" placeholder="Search projects" value={query} onChange={event=>setQuery(event.target.value)}/></label>
    <button aria-pressed={archives} onClick={()=>setArchives(value=>!value)}><Archive size={14}/>{archives?'Archived':'Active'} projects</button>
   </div>
   {id&&!current?<p className="muted" role="status">Opening project…</p>:<>
    <div className="project-directory">
     {visibleProjects.map(project=><button className="project-card" key={project.id} onClick={()=>{changeLocation({id:project.id,creating:false});setProblem('');}}>
      <Folder size={20} aria-hidden="true"/>
      <span><b>{project.name}</b>{project.description&&<small>{project.description}</small>}</span>
      <ArrowRight size={15} aria-hidden="true"/>
     </button>)}
    </div>
    {data&&!visibleProjects.length&&<div className="box empty">{query?'No matching projects.':archives?'No archived projects.':'Create a project to get started.'}</div>}
    {!data&&!error&&<p role="status">Loading projects…</p>}
   </>}
  </>}
 </section>;
}

function ProjectHome({project,tick,refresh,back}:{project:Project;tick:number;refresh:()=>void;back:()=>void}){
 const [active,setActive]=useState<typeof sections[number]>('Chats');
 const [fileMode,setFileMode]=useState<'Text sources'|'Files'>('Files');
 const heading=useRef<HTMLHeadingElement>(null);
 useEffect(()=>{heading.current?.focus();},[]);
 const user=useSession();
 const readOnly=user.role==='VIEWER'||(user.role!=='ADMIN'&&project.member_role==='VIEWER')||!!project.archived_at;
 const canChat=user.role!=='VIEWER'&&!project.archived_at;
 const manage=user.role==='ADMIN'||(user.role!=='VIEWER'&&project.owner_id===user.id);
 const start=()=>window.dispatchEvent(new CustomEvent('core-ai-project-chat',{detail:{
  projectId:project.id,model:project.default_model,mode:project.default_mode,
 }}));

 return <>
  <nav className="project-breadcrumb" aria-label="Project navigation">
   <button className="link" onClick={back}><ArrowLeft size={15}/>All projects</button>
  </nav>
  <header className="page-head project-title">
   <div><h1 tabIndex={-1} ref={heading}>{project.name}</h1>
   {(project.description||project.archived_at)&&<p>{project.archived_at?'Archived project':project.description}</p>}</div>
   <div className="actions">
    <button className="primary" disabled={!canChat} onClick={start}><Plus size={15}/>New chat</button>
    <ChatPopover label="Project options" kind="menu" align="end" buttonClass="project-menu-trigger" trigger={<Ellipsis size={18}/>}>
     {dismiss=><>
      <button role="menuitem" onClick={()=>{setActive('Sources');setFileMode('Files');dismiss();}}>{readOnly?'View sources':'Add sources'}</button>
      <button role="menuitem" onClick={()=>{setActive('Instructions');dismiss();}}>{readOnly?'View instructions':'Edit instructions'}</button>
      <button role="menuitem" onClick={()=>{setActive('Settings');dismiss();}}>Project settings</button>
     </>}
    </ChatPopover>
   </div>
  </header>
  <nav className="project-sections" aria-label="Project sections">
   {sections.map(tab=><button key={tab} aria-current={tab===active?'page':undefined} onClick={()=>setActive(tab)}>{tab}</button>)}
  </nav>
  {active==='Chats'&&<ProjectChats project={project} tick={tick} refresh={refresh} start={start} canChat={canChat}/>}
  {active==='Sources'&&<>
   <div className="toolbar-line">{(['Text sources','Files'] as const).map(mode=><button key={mode} aria-pressed={mode===fileMode} onClick={()=>setFileMode(mode)}>{mode}</button>)}</div>
   {fileMode==='Files'?<FilesPanel projectId={project.id} readOnly={readOnly} tick={tick} refresh={refresh}/>:
    <Sources projectId={project.id} readOnly={readOnly} tick={tick} refresh={refresh}/>}
  </>}
  {active==='Instructions'&&<ProjectSettings key="instructions" project={project} tick={tick} refresh={refresh} readOnly={readOnly} instructions/>}
  {active==='Artifacts'&&<ArtifactLibrary projectId={project.id} readOnly={readOnly} tick={tick} refresh={refresh}/>}
  {active==='Members'&&<ProjectMembers project={project} tick={tick} refresh={refresh} manage={manage&&!readOnly}/>}
  {active==='Settings'&&<>
   <ProjectSettings key="settings" project={project} tick={tick} refresh={refresh} readOnly={readOnly} canArchive={manage}/>
   <section className="box">
    <header>Project tools</header>
    <div className="settings-content"><div className="actions">
     {['Agents','Tasks','Integrations'].map(view=><button key={view} onClick={()=>window.dispatchEvent(new CustomEvent('core-ai-goto',{detail:{view}}))}>{view==='Integrations'?'Connections':view}</button>)}
    </div></div>
   </section>
   {user.role==='ADMIN'&&<ProjectConnections id={project.id} tick={tick}/>}
  </>}
 </>;
}

function ProjectChats({project,tick,refresh,start,canChat}:{project:Project;tick:number;refresh:()=>void;start:()=>void;canChat:boolean}){
 const [archived,setArchived]=useState(false),[query,setQuery]=useState(''),[adding,setAdding]=useState(false);
 const [target,setTarget]=useState(''),[busy,setBusy]=useState(false),[problem,setProblem]=useState('');
 const [rename,setRename]=useState<Chat|null>(null);
 const {data,error}=useResource('chat/conversations?project_id='+project.id+'&archived='+archived+'&q='+encodeURIComponent(query),tick);
 const {data:conversations}=useResource('chat/conversations?all_statuses=true',tick);
 const {role}=useSession();

 async function action(chatId:string,action:'move'|'metadata',body:Record<string,unknown>){
  setBusy(true);setProblem('');
  try{
   await api('chat/conversations/'+chatId+(action==='move'?'/project':''),action==='move'?'PUT':'PATCH',body);
   if(action==='move'){
    window.dispatchEvent(new CustomEvent('core-ai-chat-project-updated',{detail:{chatId,projectId:body.project_id}}));
    setTarget('');setAdding(false);
   }
   refresh();
  }catch(e){setProblem((e as Error).message);}
  finally{setBusy(false);}
 }

 return <section aria-label="Project chats">
  <div className="project-toolbar">
   <label className="project-search"><Search size={15} aria-hidden="true"/><input aria-label="Search project chats" placeholder="Search chats" value={query} onChange={e=>setQuery(e.target.value)}/></label>
   <div className="actions">
    <button aria-pressed={archived} onClick={()=>setArchived(value=>!value)}><Archive size={14}/>{archived?'Archived':'Active'} chats</button>
    <button disabled={!canChat} onClick={()=>setAdding(value=>!value)}>{adding?'Cancel move':'Move existing chat'}</button>
   </div>
  </div>
  {adding&&<form className="box form" onSubmit={event=>{event.preventDefault();void action(target,'move',{project_id:project.id});}}>
   <label>Conversation<select required value={target} onChange={e=>setTarget(e.target.value)}>
    <option value="">Choose a conversation</option>
    {(conversations??[]).filter((chat:Chat)=>chat.project_id!==project.id).map((chat:Chat)=><option value={chat.id} key={chat.id}>{chat.title}</option>)}
   </select></label>
   <button disabled={!target||busy}>Move to this project</button>
  </form>}
  {(error||problem)&&<div className="error" role="alert">{problem||error}</div>}
  {!!data?.length&&<ul className="project-chat-list">{data.map((chat:Chat)=><li className="project-chat-row" key={chat.id}>
   <button className="project-chat-open" onClick={()=>window.dispatchEvent(new CustomEvent('core-ai-open-chat',{detail:{id:chat.id}}))}>
    <MessageSquare size={16} aria-hidden="true"/><strong>{chat.title}</strong>
    <time dateTime={chat.updated_at} title={displayDate(chat.updated_at)}>{new Date(chat.updated_at).toLocaleDateString(undefined,{day:'numeric',month:'short'})}{chat.pinned?' · Pinned':''}</time>
   </button>
   {role!=='VIEWER'&&<ChatPopover label={'Options for '+chat.title} kind="menu" align="end" buttonClass="project-menu-trigger" trigger={<Ellipsis size={18}/>}>
    {dismiss=><>
     <button role="menuitem" disabled={busy} onClick={()=>{dismiss();setRename(chat);}}>Rename</button>
     <button role="menuitem" disabled={busy} onClick={()=>{dismiss();void action(chat.id,'metadata',{pinned:!chat.pinned});}}>{chat.pinned?'Unpin':'Pin'}</button>
     <button role="menuitem" disabled={busy} onClick={()=>{dismiss();void action(chat.id,'metadata',{archived:!chat.archived});}}>{chat.archived?'Restore':'Archive'}</button>
     <button role="menuitem" disabled={busy} onClick={()=>{dismiss();void action(chat.id,'move',{project_id:null});}}>Remove from project</button>
    </>}
   </ChatPopover>}
  </li>)}</ul>}
  {data?.length===0&&<div className="box empty"><b>{query?'No matching chats':archived?'No archived chats':'No conversations yet'}</b>
   {canChat&&!query&&!archived&&<button onClick={start}>Start a project chat</button>}</div>}
  {!data&&!error&&<div className="empty">Loading project chats…</div>}
  {rename&&<ConversationDialog action="rename" title={rename.title} dismiss={()=>setRename(null)} confirm={async title=>{await action(rename.id,'metadata',{title});setRename(null);}}/>}
 </section>;
}

function ProjectSettings({project,tick,refresh,readOnly,instructions=false,canArchive=false}:{project:Project;tick:number;refresh:()=>void;readOnly:boolean;instructions?:boolean;canArchive?:boolean}){
 const [busy,setBusy]=useState(false),[problem,setProblem]=useState(''),[saved,setSaved]=useState(false);
 const {data:catalog}=useResource('models?catalog=true',tick);
 const modelNames=[...new Set<string>([...(catalog?.models??[]).filter(isTextModel).map((model:{name:string})=>model.name),...(project.default_model?[project.default_model]:[])])];
 async function save(event:FormEvent<HTMLFormElement>){
  event.preventDefault();setBusy(true);setProblem('');setSaved(false);
  const fields=Object.fromEntries(new FormData(event.currentTarget));
  try{
   await api('projects/'+project.id+(instructions?'/instructions':''),'PUT',instructions?{
    instructions:fields.instructions,default_model:fields.default_model||null,default_mode:fields.default_mode||null,
   }:{name:fields.name,description:fields.description});
   refresh();setSaved(true);
  }catch(e){setProblem((e as Error).message);}
  finally{setBusy(false);}
 }
 async function archive(){
  setBusy(true);setProblem('');
  try{await api('projects/'+project.id+'/archive','PUT',{archived:!project.archived_at});refresh();}
  catch(e){setProblem((e as Error).message);}
  finally{setBusy(false);}
 }
 return <section className="box">
  <header>{instructions?'Project instructions':'Project settings'}</header>
  <form className="form" onSubmit={save} onChange={()=>setSaved(false)}>
   {instructions?<>
    <p className="panel-note">These instructions apply to new replies when the conversation uses this project.</p>
    <label>Instructions<textarea name="instructions" rows={6} maxLength={8000} defaultValue={project.instructions} disabled={readOnly}/></label>
    <div className="fields">
     <label>Default model<select name="default_model" defaultValue={project.default_model??''} disabled={readOnly}><option value="">Use workspace default</option>{modelNames.map(name=><option key={name}>{name}</option>)}</select></label>
     <label>Default response style<select name="default_mode" defaultValue={project.default_mode??''} disabled={readOnly}><option value="">Use workspace default</option>{chatModes.map(({value,label})=><option value={value} key={value}>{label}</option>)}</select></label>
    </div>
   </>:<>
    <label>Name<input name="name" required maxLength={120} defaultValue={project.name} disabled={readOnly}/></label>
    <label>Description<textarea name="description" rows={3} maxLength={4000} defaultValue={project.description} disabled={readOnly}/></label>
   </>}
   {problem&&<div className="error" role="alert">{problem}</div>}
   {saved&&<p role="status">Saved.</p>}
   <div className="actions"><button className="primary" disabled={readOnly||busy}>{instructions?'Save instructions':'Save project'}</button>
    {!instructions&&canArchive&&<button type="button" disabled={busy} onClick={()=>void archive()}>{project.archived_at?'Restore project':'Archive project'}</button>}
   </div>
  </form>
 </section>;
}

function ProjectMembers({project,tick,refresh,manage}:{project:Project;tick:number;refresh:()=>void;manage:boolean}){
 const path='projects/'+project.id+'/members';
 const {data,error}=useResource(path,tick);
 const [problem,setProblem]=useState(''),[busy,setBusy]=useState(false);
 async function change(method:string,body?:unknown,id?:string){
  setBusy(true);setProblem('');
  try{await api(path+(id?'/'+id:''),method,body);refresh();return true;}
  catch(e){setProblem((e as Error).message);return false;}
  finally{setBusy(false);}
 }
 return <section className="box">
  <header>Members</header>
  <p className="panel-note">Project sources and shared artifacts follow membership. Each member’s conversations stay private.</p>
  {(error||problem)&&<div className="error" role="alert">{problem||error}</div>}
  {(data??[]).map((member:{user_id:string;username:string;role:string})=><div className="document-row" key={member.user_id}>
   <span>{member.username} · {member.role}</span>
   {manage&&member.role!=='OWNER'&&<button disabled={busy} onClick={()=>{if(confirm('Remove this member’s project access?'))void change('DELETE',undefined,member.user_id);}}>Remove</button>}
  </div>)}
  {manage&&<form className="form" onSubmit={async event=>{
   event.preventDefault();const form=event.currentTarget;if(await change('PUT',Object.fromEntries(new FormData(form))))form.reset();
  }}>
   <div className="fields"><label>Existing account<input name="username" required maxLength={64}/></label><label>Project role<select name="role"><option>EDITOR</option><option>VIEWER</option></select></label></div>
   <button disabled={busy}>Add or update member</button>
  </form>}
 </section>;
}

function ProjectConnections({id,tick}:{id:string;tick:number}){
 const {data,error}=useResource('projects/'+id+'/connections',tick);
 return <section className="box">
  <header>Connections using this project</header>
  {error&&<div className="error" role="alert">{error}</div>}
  {(data??[]).map((item:{id:string;name:string;model:string|null;paused:boolean;revoked_at:string|null})=>
   <div className="document-row" key={item.id}><span>{item.name} · {item.model??'Caller selects model'}</span><small>{item.revoked_at?'Revoked':item.paused?'Paused':'Enabled'}</small></div>)}
  {data?.length===0&&<div className="empty">No connections use this project.</div>}
 </section>;
}
