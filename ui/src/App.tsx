import {Component,Fragment,useEffect,useRef,useState,type CSSProperties,type KeyboardEvent as ReactKeyboardEvent,type ReactNode} from 'react';
import {MessageSquare,MessageSquarePlus,Plus,Folder,Files,FileText,Bot,ListTodo,BookOpen,Wrench,Activity,Shield,Settings as SettingsIcon,LayoutDashboard,Plug,Search,Command as CommandIcon,LogOut,PanelRight,Columns2,X,Maximize2,ExternalLink,ChevronDown,Workflow,SlidersHorizontal} from 'lucide-react';
import {api,newId,setCsrf} from './api';
import {views,defaults,restore,closeTab,key,type Layout,type View} from './layout';
import {appearanceKey,defaultAppearance,restoreAppearance,typographyVersion,type Appearance} from './appearance';
import {MenuBar,CommandPalette,ResizeHandle,type Command} from './WorkbenchControls';
import {Module,Inspector,Activity as ActivityPanel,ErrorNote} from './Modules';
import {ChatProvider,ChatPane,ChatHistory,SidebarToggle} from './Chat';
import {SessionProvider,type Session} from './Session';
import {projectDirectory,type ProjectLocation} from './Projects';
import {ArtifactEditor,SourceInspector,useResource} from './Workspace';

type ExplorerProject={id:string;name:string;archived_at?:string|null};
function ProjectNavigation({tick,canCreate,selected,open}:{tick:number;canCreate:boolean;selected?:ProjectLocation;open:(location:ProjectLocation)=>void}){
 const [expanded,setExpanded]=useState(true);
 const {data,error}=useResource('projects',tick);
 const projects:ExplorerProject[]=(Array.isArray(data)?data:[]).filter((project:ExplorerProject)=>!project.archived_at);
 const shown=projects.slice(0,6);
 const current=projects.find(project=>project.id===selected?.id);
 if(current&&!shown.some(project=>project.id===current.id))shown[shown.length-1]=current;
 return <section className="explorer-projects" aria-label="Projects">
  <div className="explorer-project-heading">
   <button className="nav-group" aria-expanded={expanded} aria-controls="explorer-project-list" onClick={()=>setExpanded(value=>!value)}>
    <span>Projects</span><ChevronDown size={13} className={expanded?'':'collapsed'} aria-hidden="true"/>
   </button>
   {canCreate&&<button className="explorer-project-add" aria-label="New project" title="New project" onClick={()=>open({id:'',creating:true})}><Plus size={15} aria-hidden="true"/></button>}
  </div>
  <div id="explorer-project-list" hidden={!expanded}>
   {shown.map(project=><button key={project.id} className={'nav-item '+(selected?.id===project.id&&!selected.creating?'selected':'')}
    aria-current={selected?.id===project.id&&!selected.creating?'page':undefined} title={project.name} onClick={()=>open({id:project.id,creating:false})}>
    <Folder size={15} aria-hidden="true"/><span>{project.name}</span>
   </button>)}
   <button className={'nav-item '+(selected&&!selected.id&&!selected.creating?'selected':'')} aria-current={selected&&!selected.id&&!selected.creating?'page':undefined} onClick={()=>open(projectDirectory)}>
    <Folder size={15} aria-hidden="true"/><span>All projects</span>
   </button>
   {error&&<p className="explorer-project-note" role="status">Could not load projects.</p>}
  </div>
 </section>;
}

class Boundary extends Component<{children:ReactNode},{error:boolean}>{state={error:false};static getDerivedStateFromError(){return {error:true};}render(){return this.state.error?<div className="error">This panel could not render. <button onClick={()=>this.setState({error:false})}>Retry panel</button></div>:this.props.children;}}
function safeGet(k:string){try{return localStorage.getItem(k);}catch{return null;}}
const params=new URLSearchParams(location.search),detached=params.has('view');
function initial(){const l=restore(safeGet(key));const v=params.get('view') as View;return views.includes(v)?{...defaults(),groups:[[v]],active:[v],left:false,bottom:false}:l;}
const icons:Record<View,typeof MessageSquare>={Chat:MessageSquare,Overview:LayoutDashboard,Projects:Folder,Files,Artifacts:FileText,Agents:Bot,Tasks:ListTodo,Knowledge:BookOpen,Tools:Wrench,Models:SlidersHorizontal,Integrations:Plug,Operations:Activity,Settings:SettingsIcon,Access:Shield,Capabilities:Shield,Workflows:Workflow};
const navGroups:{label:string;items:View[]}[]=[{label:'Workspace',items:['Chat','Projects','Files','Artifacts']},{label:'Build & automate',items:['Agents','Tasks','Knowledge','Tools','Workflows']},{label:'Manage',items:['Overview','Models','Integrations','Operations','Access','Capabilities','Settings']}];
const title=(v:View)=>v==='Integrations'?'Connections':v;
type Right={kind:'artifact';id:string}|{kind:'source';id:string;version?:number}|null;
export default function App(){
 const [layout,setLayout]=useState<Layout>(initial),[appearance,setAppearance]=useState<Appearance>(()=>restoreAppearance(safeGet(appearanceKey))),[pinned,setPinned]=useState<View[]>(()=>{try{const a=JSON.parse(safeGet('core-ai.pins.v1')||'[]');return Array.isArray(a)?views.filter(v=>a.includes(v)):[];}catch{return [];}});
 const [session,setSession]=useState<Session|null>(null),[checking,setChecking]=useState(true),[tick,setTick]=useState(0),[palette,setPalette]=useState(false),[error,setError]=useState(''),[health,setHealth]=useState<any>(null),[context,setContext]=useState<{v:View;g:number;x:number;y:number}|null>(null),[bottomTab,setBottomTab]=useState('Activity'),[right,setRight]=useState<Right>(null),[viewport,setViewport]=useState(()=>({width:window.innerWidth,height:window.innerHeight})),[workspaceBounds,setWorkspaceBounds]=useState<{width:number;height:number}|null>(null),[mobileOpen,setMobileOpen]=useState(false),[groupsOpen,setGroupsOpen]=useState<Record<string,boolean>>({'Workspace':true,'Build & automate':false,'Manage':false});
 const [projectLocations,setProjectLocations]=useState<Record<string,ProjectLocation>>({});
 const paneKey=(index:number)=>layout.workspace+':'+layout.paneIds[index];
 const projectKey=(index:number)=>(session?.id??session?.username??'')+'/'+paneKey(index);
 const updateProjectLocation=(index:number,location:ProjectLocation)=>setProjectLocations(current=>({...current,[projectKey(index)]:location}));
 const mobile=viewport.width<1000;
 const active=layout.active[layout.focus],chatFocus=layout.groups.length===1&&active==='Chat';
 const explorer=useRef<HTMLElement>(null),main=useRef<HTMLElement>(null);
 const drawerWasOpen=useRef(false),focusMainOnClose=useRef(false);
 const patch=(p:Partial<Layout>)=>setLayout(x=>({...x,...p}));const refresh=()=>setTick(t=>t+1);const appearancePatch=(p:Partial<Appearance>)=>setAppearance(x=>({...x,...p}));
 const sidebarVisible=!layout.maximized&&(mobile?mobileOpen:layout.left);
 const drawerOpen=mobile&&sidebarVisible;
 const dockedExplorer=sidebarVisible&&!mobile;
 const ribbonVisible=appearance.activity||!sidebarVisible;
 const estimatedWidth=viewport.width-(dockedExplorer?layout.leftWidth:0)-(ribbonVisible?42:0)-(layout.right&&viewport.width>1100&&!layout.maximized?layout.rightWidth+3:0);
 const panelWidth=workspaceBounds?.width??estimatedWidth;
 const panelHeight=workspaceBounds?.height??viewport.height;
 const singlePane=layout.groups.length>1&&!layout.maximized&&(
  viewport.width<600||
  (layout.axis==='row'?panelWidth<layout.groups.length*340:(panelHeight-(layout.bottom?layout.bottomHeight:0)-44)<layout.groups.length*300)
 );
 const leftChrome={'--explorer-width':`${layout.leftWidth}px`} as CSSProperties;
 function closeExplorer(){if(mobile)setMobileOpen(false);else patch({left:false});}
 function trapDrawerFocus(event:ReactKeyboardEvent<HTMLElement>){
  if(!drawerOpen||event.key!=='Tab')return;
  const controls=event.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), summary');
  const visible=Array.from(controls).filter(control=>!control.closest('[hidden]'));
  const first=visible[0],last=visible[visible.length-1];
  if(event.shiftKey&&document.activeElement===first){event.preventDefault();last?.focus();}
  if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first?.focus();}
 }
 function toggleSidebar(){if(mobile){setMobileOpen(!sidebarVisible);patch({maximized:false});}else patch({left:!sidebarVisible,maximized:false});}
 function guardInspector(){return window.dispatchEvent(new Event('core-ai-inspector-close',{cancelable:true}));}
 function closeRight(){setRight(null);patch({right:false});}
 function toggleRight(){if(layout.right){if(guardInspector())closeRight();}else patch({right:true});}
 function open(view:View,group=layout.focus){if(drawerOpen)focusMainOnClose.current=true;setLayout(x=>{const groups=x.groups.map(g=>[...g]),active=[...x.active];if(!groups[group])group=0;if(!groups[group].includes(view))groups[group].push(view);active[group]=view;return {...x,groups,active,focus:group};});setPalette(false);setMobileOpen(false);}
 function revealNavigation(view:View){
  const group=navGroups.find(group=>group.items.includes(view));
  if(group)setGroupsOpen(current=>current[group.label]?current:{...current,[group.label]:true});
 }
 function go(v:View){revealNavigation(v);const at=layout.groups[layout.focus].includes(v)?layout.focus:layout.groups.findIndex(g=>g.includes(v));open(v,at<0?layout.focus:at);}
 function goProject(location:ProjectLocation){
  const existing=layout.groups[layout.focus].includes('Projects')?layout.focus:layout.groups.findIndex(group=>group.includes('Projects'));
  const pane=existing<0?layout.focus:existing;
  updateProjectLocation(pane,location);
  open('Projects',pane);
 }
 function preset(workbench:boolean){setLayout(x=>({...x,groups:[workbench?['Overview','Chat']:['Chat']],paneIds:[x.paneIds[x.focus]],active:[workbench?'Overview':'Chat'],focus:0,bottom:workbench,maximized:false}));}
 function alone(v:View,group=layout.focus){patch({groups:[[v]],paneIds:[layout.paneIds[group]],active:[v],focus:0,maximized:false});}
 function split(axis:Layout['axis']='row',view?:View){
  const id=newId();
  setLayout(x=>{
   if(x.groups.length>=4)return {...x,axis};
   const next=view??x.active[x.focus];
   return {...x,axis,groups:[...x.groups,[next]],paneIds:[...x.paneIds,id],active:[...x.active,next],focus:x.groups.length,maximized:false};
  });
  setPalette(false);
 }
 function addChatPane(){if(layout.groups.length<4){split(layout.axis,'Chat');setMobileOpen(false);}}
 function newChat(){window.dispatchEvent(new Event('core-ai-new-chat'));open('Chat');}
 function resetLayout(){setLayout({...defaults(),workspace:layout.workspace});}
 function detach(v:View){window.open('?view='+encodeURIComponent(v),'_blank','noopener,noreferrer');}
 function pin(v:View){setPinned(x=>x.includes(v)?x.filter(y=>y!==v):[...x,v]);}
 function close(v:View,g:number){if(!pinned.includes(v))setLayout(x=>closeTab(x,v,g));}
 function workspace(w:Layout['workspace']){if(w===layout.workspace)return;try{localStorage.setItem(key+'.'+layout.workspace,JSON.stringify(layout));}catch{setError('Workspace could not be saved.');}setLayout({...restore(safeGet(key+'.'+w)),workspace:w});setPalette(false);setMobileOpen(false);}
 useEffect(()=>{api('session').then(s=>{setCsrf(s.csrf);setSession({...s,role:s.role||'ADMIN'});}).catch(()=>setSession(null)).finally(()=>setChecking(false));},[]);
 useEffect(()=>{const resize=()=>setViewport({width:window.innerWidth,height:window.innerHeight});window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
 useEffect(()=>{
  if(!session||!main.current||typeof ResizeObserver==='undefined')return;
  const observer=new ResizeObserver(([entry])=>setWorkspaceBounds({width:entry.contentRect.width,height:entry.contentRect.height}));
  observer.observe(main.current);
  return()=>observer.disconnect();
 },[session]);
 useEffect(()=>{revealNavigation(active);},[active]);
 useEffect(()=>{
  if(drawerOpen)explorer.current?.querySelector('button')?.focus();
  else if(drawerWasOpen.current&&mobile){
   if(focusMainOnClose.current)main.current?.focus();
   else document.getElementById('core-ai-explorer-toggle')?.focus();
  }
  drawerWasOpen.current=drawerOpen;
  focusMainOnClose.current=false;
 },[drawerOpen,mobile]);
 useEffect(()=>{document.documentElement.dataset.theme=appearance.theme;document.documentElement.dataset.density=appearance.density.toLowerCase();document.documentElement.style.setProperty('--ui-size',appearance.fontSize+'px');document.documentElement.style.setProperty('--reading-size',appearance.readingSize+'px');try{localStorage.setItem(appearanceKey,JSON.stringify({...appearance,typographyVersion}));if(!detached){localStorage.setItem(key,JSON.stringify(layout));localStorage.setItem(key+'.'+layout.workspace,JSON.stringify(layout));}localStorage.setItem('core-ai.pins.v1',JSON.stringify(pinned));}catch{setError('Browser preferences could not be saved.');}},[layout,appearance,pinned]);
 useEffect(()=>{if(!session)return;let alive=true;api('overview').then(d=>{if(alive){setHealth(d);setError('');}}).catch(e=>{if(alive){setError(e.message);setHealth(null);if(e.status===401){setSession(null);setCsrf('');}}});return()=>{alive=false;};},[tick,session]);
 useEffect(()=>{if(!session)return;const id=setInterval(()=>{if(document.visibilityState!=='hidden')refresh();},5000);return()=>clearInterval(id);},[session]);
 useEffect(()=>{const artifact=(e:Event)=>{if(guardInspector()){setRight({kind:'artifact',id:(e as CustomEvent).detail.id});setLayout(x=>({...x,right:true,maximized:false,rightWidth:Math.max(x.rightWidth,560)}));}},source=(e:Event)=>{if(guardInspector()){setRight({kind:'source',id:(e as CustomEvent).detail.id,version:(e as CustomEvent).detail.version});setLayout(x=>({...x,right:true,maximized:false,rightWidth:Math.max(x.rightWidth,420)}));}},chat=()=>open('Chat'),goto=(e:Event)=>{const v=(e as CustomEvent).detail.view;if(views.includes(v))go(v);};
  window.addEventListener('core-ai-artifact',artifact);window.addEventListener('core-ai-source',source);window.addEventListener('core-ai-open-chat',chat);window.addEventListener('core-ai-project-chat',chat);window.addEventListener('core-ai-goto',goto);
  return()=>{window.removeEventListener('core-ai-artifact',artifact);window.removeEventListener('core-ai-source',source);window.removeEventListener('core-ai-open-chat',chat);window.removeEventListener('core-ai-project-chat',chat);window.removeEventListener('core-ai-goto',goto);};});
 const commands:Command[]=[...views.map(v=>({section:'Go to',label:title(v),run:()=>go(v)})),...(['Build','Research','Operations'] as const).map(w=>({section:'Workspace',label:w+' workspace',run:()=>workspace(w)})),
  {section:'Workspace',label:'New chat',shortcut:'Ctrl Shift O',run:newChat},
  ...(layout.groups.length<4?[{section:'Workspace',label:'New split pane',run:addChatPane}]:[]),
  {section:'Workspace',label:'Open all panels',run:()=>patch({groups:[[...views]],paneIds:[layout.paneIds[layout.focus]],active:['Chat'],focus:0,maximized:false})},
  {section:'Workspace',label:'Close all unpinned panels',run:()=>{const tabs=pinned.length?[...pinned]:['Chat' as View];patch({groups:[tabs],paneIds:[layout.paneIds[layout.focus]],active:[tabs[0]],focus:0,maximized:false});}},
  {section:'Workspace',label:'Open active panel alone',run:()=>alone(active)},
  {section:'Workspace',label:'Detach active panel',run:()=>detach(active)},
  {section:'View',label:'Toggle explorer',shortcut:'Ctrl B',run:toggleSidebar},
  {section:'View',label:'Toggle inspector',run:toggleRight},
  {section:'View',label:'Toggle activity panel',shortcut:'Ctrl J',run:()=>patch({bottom:!layout.bottom})},
  {section:'View',label:'Refresh live data',run:refresh},
  {section:'Layout',label:'Chat focus layout',run:()=>preset(false)},
  {section:'Layout',label:'Workbench layout',run:()=>preset(true)},
  {section:'Layout',label:'Split right',shortcut:'Ctrl \\',run:()=>split('row')},
  {section:'Layout',label:'Split down',run:()=>split('column')},
  {section:'Layout',label:'Toggle maximize active group',run:()=>patch({maximized:!layout.maximized})},
  {section:'Layout',label:'Reset workspace layout',run:resetLayout},
  {section:'Appearance',label:'Appearance and reading settings',run:()=>go('Settings')},
  {section:'Navigate',label:'Command palette',shortcut:'Ctrl K',run:()=>setPalette(true)},
  {section:'Help',label:'Capabilities and implementation status',run:()=>go('Capabilities')}];
 useEffect(()=>{const on=(e:KeyboardEvent)=>{const mod=e.ctrlKey||e.metaKey;if(e.key==='Escape'){setPalette(false);setContext(null);setMobileOpen(false);}if(mod&&e.key.toLowerCase()==='k'){e.preventDefault();setPalette(x=>!x);return;}if(mod&&e.shiftKey&&e.key.toLowerCase()==='o'){e.preventDefault();newChat();return;}if(e.target instanceof Element&&e.target.closest('input,textarea,select,[contenteditable]'))return;if(mod&&e.key.toLowerCase()==='b'){e.preventDefault();toggleSidebar();}if(mod&&e.key.toLowerCase()==='j'){e.preventDefault();patch({bottom:!layout.bottom});}if(mod&&e.key==='\\'){e.preventDefault();split();}if(mod&&['1','2','3','4'].includes(e.key)){e.preventDefault();const focus=+e.key-1;if(focus<layout.groups.length)patch({focus});}};window.addEventListener('keydown',on);return()=>window.removeEventListener('keydown',on);},[layout,mobile,mobileOpen]);
 if(checking)return <div className="login"><div className="login-loading">Connecting to CORE-AI…</div></div>;
 if(!session)return <Login done={s=>{setCsrf(s.csrf);setSession({...s,role:s.role||'ADMIN'});refresh();}}/>;
 const worker=health?.worker?.online;
 const navigation=<nav className="workspace-navigation" aria-label="Workspace navigation">
  {navGroups.map(group=>{
   const expanded=groupsOpen[group.label],current=active!=='Projects'&&group.items.includes(active);
   const groupId='explorer-'+group.items[0].toLowerCase();
   return <Fragment key={group.label}><section>
    <button className="nav-group" aria-expanded={expanded} aria-controls={groupId} onClick={()=>setGroupsOpen(x=>({...x,[group.label]:!x[group.label]}))}>
     <span>{group.label}</span>{current&&!expanded&&<small>{title(active)}</small>}<ChevronDown size={12} className={expanded?'':'collapsed'} aria-hidden="true"/>
    </button>
    <div id={groupId} hidden={!expanded}>{expanded&&group.items.filter(v=>v!=='Projects').map(v=>{
     const Icon=icons[v];
     return <button key={v} className={'nav-item '+(active===v?'selected':'')} aria-current={active===v?'page':undefined} onClick={()=>go(v)}>
      <Icon size={15} aria-hidden="true"/><span>{title(v)}</span>{v==='Workflows'&&<small>Planned</small>}
     </button>;
    })}</div>
   </section>
   {group.label==='Workspace'&&<ProjectNavigation tick={tick} canCreate={session.role!=='VIEWER'}
    selected={active==='Projects'?projectLocations[projectKey(layout.focus)]??projectDirectory:undefined} open={goProject}/>}
   </Fragment>;
  })}
 </nav>;
 return <SessionProvider session={session}><ChatProvider key={session.username} username={session.username} tick={tick} focusedPane={paneKey(layout.focus)} persist={!detached}><div className={'app '+(chatFocus?'chat-focused ':'')+(appearance.wrapTabs?'wrap-tabs ':'')+(appearance.status?'':'without-status')} data-explorer={dockedExplorer} data-drawer={mobile} data-ribbon={ribbonVisible} style={leftChrome}>
  <header className="top"><div className="top-leading"><SidebarToggle open={sidebarVisible} toggle={toggleSidebar}/><div className="brand"><svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="1.4"/><circle cx="12" cy="12" r="5" stroke="currentColor" strokeWidth="1.4"/><circle cx="12" cy="12" r="1.6" fill="currentColor"/></svg><b>CORE-AI</b><span>WORKSPACE</span></div></div><span className="header-context">{title(active)}</span><button className="command" onClick={()=>setPalette(true)}><Search size={13}/><span>Search or run a command</span><kbd>Ctrl K</kbd></button><div className="header-health"><i className={'dot '+(worker?'ready':'')}/><span>{worker?'Worker online':'Worker unavailable'}</span></div><div className="header-actions"><button className="primary-new-chat" aria-label="New chat" title="New chat · Ctrl Shift O" onClick={newChat}><Plus size={16}/><span>New chat</span></button><button className="new-chat-pane" aria-label="New split pane" title={layout.groups.length>=4?'Four panes open per workspace':'Open an independent chat pane'} disabled={layout.groups.length>=4} onClick={addChatPane}><MessageSquarePlus size={16}/></button><button aria-label="Toggle inspector" title="Inspector" onClick={toggleRight}><PanelRight size={15}/></button><details className="layout-menu"><summary aria-label="Layout controls"><Columns2 size={15}/></summary><div><button onClick={addChatPane} disabled={layout.groups.length>=4}>New split pane</button><button onClick={()=>preset(false)}>Chat</button><button onClick={()=>preset(true)}>Workbench</button><button onClick={()=>split()}>Split workspace</button><button onClick={()=>patch({groups:[[...views]],paneIds:[layout.paneIds[layout.focus]],active:['Chat'],focus:0,maximized:false})}>Open all panels</button><button onClick={()=>patch({bottom:!layout.bottom})}>Output panel</button><button onClick={resetLayout}>Reset layout</button></div></details><button className="profile-button" title={session.username+' · '+session.role} onClick={()=>go('Settings')}>{session.username.slice(0,1).toUpperCase()}</button><button aria-label="Sign out" title="Sign out" onClick={async()=>{if(!guardInspector())return;try{await api('session','DELETE');setSession(null);setCsrf('');setHealth(null);}catch(e){setError((e as Error).message);}}}><LogOut size={15}/></button></div></header>
  <ErrorNote error={error}/>
  <div className="shell">
   {ribbonVisible&&<nav className="activity" aria-label="Activity ribbon">
    {navGroups.map(group=><div className="activity-group" key={group.label} role="group" aria-label={group.label}>
     {group.items.map(v=>{const Icon=icons[v];return <button key={v} title={title(v)} aria-label={title(v)} aria-current={active===v?'page':undefined} onClick={()=>go(v)}><Icon size={18} aria-hidden="true"/></button>;})}
    </div>)}
   </nav>}
   {sidebarVisible&&<>
    {mobile&&<button className="sidebar-backdrop" tabIndex={-1} aria-label="Close sidebar" onClick={closeExplorer}/>}
    <aside className="explorer sidebar" id="core-ai-explorer" ref={explorer} role={mobile?'dialog':undefined} aria-modal={mobile||undefined} aria-labelledby="core-ai-explorer-title" onKeyDown={trapDrawerFocus}>
     <div className="sidebar-heading"><span id="core-ai-explorer-title">Explorer</span><select className="workspace-picker" aria-label="Switch workspace" value={layout.workspace} onChange={e=>workspace(e.target.value as Layout['workspace'])}>{(['Build','Research','Operations'] as const).map(name=><option key={name}>{name}</option>)}</select><button aria-label="Hide explorer" onClick={closeExplorer}><X size={14}/></button></div>
     <ChatHistory tick={tick} open={()=>open('Chat')} navigation={navigation}/>
     <div className="sidebar-account"><span className="avatar">{session.username.slice(0,1).toUpperCase()}</span><div><b>{session.username}</b><small>{session.role.toLowerCase()} · Private workspace</small></div><button aria-label="Open settings" onClick={()=>go('Settings')}><SettingsIcon size={15}/></button></div>
    </aside>
    {!mobile&&<ResizeHandle label="Explorer width" value={layout.leftWidth} min={200} max={380} change={leftWidth=>patch({leftWidth})}/>}
   </>}
  <main className="workspace-main" ref={main} tabIndex={-1}>{(!chatFocus||layout.groups[0].length>1)&&<div className="workspace-toolbar"><span>{layout.workspace} <span className="muted">/ {title(active)}</span></span><MenuBar commands={commands}/><div className="actions"><button onClick={()=>split()}>Split</button><button onClick={toggleRight}>Inspector</button><button onClick={()=>patch({bottom:!layout.bottom})}>Activity</button><button onClick={refresh}>Refresh</button></div></div>}{singlePane&&<div className="mobile-pane-switch"><label>Pane<select aria-label="Switch chat pane" value={layout.focus} onChange={e=>patch({focus:+e.target.value})}>{layout.active.map((view,index)=><option key={layout.paneIds[index]} value={index}>{index+1} · {title(view)}</option>)}</select></label></div>}<div className="groups" style={{flexDirection:singlePane?'column':layout.axis}}>{layout.groups.map((group,g)=>layout.maximized&&g!==layout.focus?null:<section className={'group '+(g===layout.focus?'focused':'')} hidden={singlePane&&g!==layout.focus} key={paneKey(g)} onFocusCapture={()=>{if(g!==layout.focus)patch({focus:g});}} onPointerDown={()=>{if(g!==layout.focus)patch({focus:g});}}>{(group.length>1||layout.groups.length>1)&&<div className="tabs" role="tablist" aria-label={'Group '+(g+1)}>{group.map(v=><div className={'tab '+(layout.active[g]===v?'active':'')} key={v} onContextMenu={e=>{e.preventDefault();setContext({v,g,x:Math.min(e.clientX,window.innerWidth-245),y:Math.min(e.clientY,window.innerHeight-255)});}}><button role="tab" id={'tab-'+g+'-'+v} aria-controls={'panel-'+g+'-'+v} aria-selected={layout.active[g]===v} onClick={()=>open(v,g)}>{pinned.includes(v)?'◆ ':''}{v==='Chat'&&layout.groups.length>1?'Chat '+(g+1):title(v)}</button><button aria-label={(pinned.includes(v)?'Unpin ':'Close ')+title(v)} onClick={()=>pinned.includes(v)?pin(v):close(v,g)}><X size={11}/></button></div>)}<div className="tab-tools"><button aria-label="Maximize group" onClick={()=>patch({focus:g,maximized:!layout.maximized})}><Maximize2 size={12}/></button><button aria-label="Detach active panel" onClick={()=>detach(layout.active[g])}><ExternalLink size={12}/></button></div></div>}{group.map(v=><div className="view" id={'panel-'+g+'-'+v} role="tabpanel" aria-label={title(v)} hidden={v!==layout.active[g]} key={v}><Boundary><ChatPane name={paneKey(g)} enabled={v==='Chat'}><Module projectLocation={projectLocations[projectKey(g)]??projectDirectory} changeProjectLocation={location=>updateProjectLocation(g,location)} view={v} visible={v===layout.active[g]&&(!singlePane||g===layout.focus)} tick={tick} refresh={refresh} go={go} appearance={appearance} changeAppearance={appearancePatch}/></ChatPane></Boundary></div>)}</section>)}</div>{layout.bottom&&!layout.maximized&&<><ResizeHandle label="Activity height" value={layout.bottomHeight} min={100} max={400} horizontal reverse change={bottomHeight=>patch({bottomHeight})}/><section className="bottom" style={{height:layout.bottomHeight}}><div className="bottom-tabs">{['Activity','Runtime'].map(t=><button key={t} className={bottomTab===t?'active':''} onClick={()=>setBottomTab(t)}>{t}</button>)}<button className="push" aria-label="Close activity" onClick={()=>patch({bottom:false})}><X size={12}/></button></div>{bottomTab==='Activity'?<ActivityPanel tick={tick}/>:<div className="runtime-log"><p>API: {health?'Connected':'Unavailable'} · Worker: {worker?'Online':'Unavailable'}</p><p>Provider: {health?.inference.endpoint??'—'} · Default model: {health?.inference.model??'—'}</p><p>Independent CORE-AI services · diagnostics: ./core-ai doctor</p></div>}</section></>}</main>
  {layout.right&&!layout.maximized&&<><ResizeHandle label="Inspector width" value={layout.rightWidth} min={300} max={1000} reverse change={rightWidth=>patch({rightWidth})}/><aside className={'inspector '+(right?'editor-inspector':'')} style={{width:layout.rightWidth}}>{right?.kind==='artifact'?<ArtifactEditor key={right.id} id={right.id} close={closeRight} changed={refresh}/>:right?.kind==='source'?<SourceInspector key={right.id+':'+right.version} id={right.id} initialVersion={right.version} close={closeRight}/>:<><div className="editor-heading"><b>Context</b><button aria-label="Close inspector" onClick={closeRight}><X size={14}/></button></div><Inspector view={active} tick={tick}/></>}</aside></>}</div>
  {appearance.status&&<footer className="status-bar"><span>CORE-AI</span><span>{layout.workspace}</span><span>{health?'Connected':'Connection unavailable'}</span><span>{worker?'Local worker online':'Worker offline'}</span><span className="push">{health?.release??'—'} · Self-hosted</span><button onClick={()=>go('Settings')}>{appearance.theme}</button></footer>}
  {palette&&<CommandPalette commands={commands} dismiss={()=>setPalette(false)}/>}{context&&<div className="context-overlay" onPointerDown={()=>setContext(null)}><div className="tab-context" style={{left:context.x,top:context.y}} onPointerDown={e=>e.stopPropagation()}>{[[pinned.includes(context.v)?'Unpin':'Pin',()=>pin(context.v)],['Open alone',()=>alone(context.v,context.g)],['Open in new window',()=>detach(context.v)],['Close',()=>close(context.v,context.g)]].map(([label,run])=><button key={label as string} onClick={()=>{(run as ()=>void)();setContext(null);}}>{label as string}</button>)}</div></div>}
 </div></ChatProvider></SessionProvider>;
}
function Login({done}:{done:(s:Session)=>void}){const [error,setError]=useState(''),[busy,setBusy]=useState(false);return <main className="login"><form onSubmit={async e=>{e.preventDefault();const f=new FormData(e.currentTarget);setBusy(true);try{done(await api('session','POST',Object.fromEntries(f)));}catch(e){setError((e as Error).message);}finally{setBusy(false);}}}><div className="login-brand"><MessageSquare size={24}/><b>CORE-AI</b></div><h1>Your private AI workspace</h1><p>Conversations, knowledge and professional work in one place.</p><ErrorNote error={error}/><label>Username<input name="username" autoComplete="username" required maxLength={64}/></label><label>Password<input name="password" type="password" autoComplete="current-password" required maxLength={256}/></label><button className="primary" disabled={busy}>{busy?'Signing in…':'Sign in'}</button><small>Self-hosted · Independent by design</small></form></main>;}
