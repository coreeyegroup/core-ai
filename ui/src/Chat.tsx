import {createContext,useCallback,useContext,useEffect,useId,useRef,useState,type ReactNode,type FormEvent} from 'react';
import Markdown from 'react-markdown';
import {Ellipsis,MessageSquare,Pin,Search} from 'lucide-react';
import remarkGfm from 'remark-gfm';
import {api,uploadFile} from './api';
import {useSession} from './Session';
import {chatModes,defaultChat,replyTokenOptions,type ChatDefaults} from './appearance';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';

type Attachment={name:string;content:string;file_id?:string;status?:string};
type Message={id:string;role:'user'|'assistant';content:string;attachments:Attachment[];model:string|null;status:string;error:string|null;created_at:string};
type Conversation={id:string;title:string;model:string;mode:ChatDefaults['mode'];instructions:string;project_id:string|null;temperature:number;max_tokens:number;pinned:boolean;archived:boolean;updated_at:string;messages:Message[];generation:{id:string;status:string}|null};
type Preferences=ChatDefaults&{model:string;instructions:string;project_id:string|null;agent_id?:string|null};
type Draft={text:string;attachments:Attachment[];preferences?:Preferences};
type Selection={id:string;newChat:{projectId:string|null}|null};
type ChatStore={
 focusedPane:string;
 revision:number;
 changed:()=>void;
 drafts:React.MutableRefObject<Record<string,Draft>>;
 selections:Record<string,Selection>;
 selectionRef:React.MutableRefObject<Record<string,Selection>>;
 choose:(pane:string,id:string,project?:{projectId:string|null},expected?:Selection)=>void;
};
const blankSelection:Selection={id:'',newChat:null};
const ChatContext=createContext<ChatStore|null>(null);
const PaneContext=createContext<string|null>(null);
const starters={
 general:[
  ['Understand','Explain a concept clearly, with an example.'],
  ['Create','Help me draft a clear, professional document.'],
  ['Develop','Review a technical approach and identify gaps.'],
  ['Analyse','Help me structure an analysis with facts, assumptions and next steps.'],
 ],
 professional:[
  ['Decision brief','Compare the options against clear criteria. Summarize the decision, evidence, trade-offs and open questions.'],
  ['Document review','Review the material I provide. Extract key findings, cite the relevant passages and flag gaps or contradictions.'],
  ['Technical review','Review the design or code I provide. Prioritize findings by impact and propose checks to verify each one.'],
  ['Research plan','Define the research question, evidence required, source criteria and uncertainties to resolve.'],
 ],
 research:[
  ['Evidence review','Summarize the evidence in the supplied material. Cite specific passages and flag unsupported claims.'],
  ['Research plan','Define the research question, evidence required, source criteria and uncertainties to resolve.'],
 ],
 deep:[
  ['Compare alternatives','Compare the options, assumptions and trade-offs. State what evidence would change the recommendation.'],
  ['Assess a decision','Identify likely failure modes and explain how to test the assumptions before committing.'],
 ],
 coding:[
  ['Review code','Review the code I provide for correctness and edge cases. Prioritize findings and suggest regression tests.'],
  ['Plan a change','Propose an implementation plan, tests, and a way to verify the result.'],
 ],
} satisfies Partial<Record<ChatDefaults['mode'],[string,string][]>>;
const emptyDraft={text:'',attachments:[]};
export function ChatProvider({username,focusedPane,persist,children}:{username:string;focusedPane:string;persist:boolean;children:ReactNode}){
 const storageKey='core-ai.chat-panes.'+username;
 const drafts=useRef<Record<string,Draft>>({});
 const [selections,setSelections]=useState<Record<string,Selection>>(()=>{
  if(!persist)return {};
  try{
   const raw=JSON.parse(localStorage.getItem(storageKey)||'null');
   if(raw&&typeof raw==='object')return Object.fromEntries(Object.entries(raw)
    .filter(([key,id])=>/^(Build|Research|Operations):[a-z0-9-]{1,48}$/.test(key)&&typeof id==='string')
    .map(([key,id])=>[key,{id:id as string,newChat:null}]));
   const legacy=localStorage.getItem('core-ai.last-chat.'+username);
   return legacy?{'Build:primary':{id:legacy,newChat:null}}:{};
  }catch{return {};}
 });
 const selectionRef=useRef(selections);
 const [revision,setRevision]=useState(0);
 const choose=useCallback((pane:string,id:string,newChat?:{projectId:string|null},expected?:Selection)=>{
  const current=selectionRef.current[pane]??blankSelection;
  if(expected&&current!==expected)return;
  if(!newChat&&current.id===id&&!current.newChat)return;
  const next={...selectionRef.current,[pane]:{id,newChat:newChat??null}};
  selectionRef.current=next;
  setSelections(next);
  if(persist)try{localStorage.setItem(storageKey,JSON.stringify(Object.fromEntries(Object.entries(next).filter(([,value])=>value.id).map(([key,value])=>[key,value.id]))));}catch{/* browser storage is optional */}
 },[persist,storageKey]);
 const changed=useCallback(()=>setRevision(v=>v+1),[]);
 useEffect(()=>{
  const start=(projectId:string|null)=>{
   const key=focusedPane+'/'+(projectId?'project:'+projectId:'');
   if(drafts.current[key])delete drafts.current[key].preferences;
   choose(focusedPane,'',{projectId});
  };
  const fresh=()=>start(null),open=(e:Event)=>choose(focusedPane,(e as CustomEvent).detail.id);
  const project=(e:Event)=>start((e as CustomEvent).detail.projectId);
  window.addEventListener('core-ai-new-chat',fresh);
  window.addEventListener('core-ai-open-chat',open);
  window.addEventListener('core-ai-project-chat',project);
  return()=>{
   window.removeEventListener('core-ai-new-chat',fresh);
   window.removeEventListener('core-ai-open-chat',open);
   window.removeEventListener('core-ai-project-chat',project);
  };
 },[focusedPane,choose]);
 return <ChatContext.Provider value={{focusedPane,selections,selectionRef,choose,revision,changed,drafts}}>{children}</ChatContext.Provider>;
}
export function ChatPane({name,children}:{name:string;children:ReactNode}){
 return <PaneContext.Provider value={name}>{children}</PaneContext.Provider>;
}
function useChat(){
 const store=useContext(ChatContext),scope=useContext(PaneContext);
 if(!store)throw new Error('Chat workspace is unavailable.');
 const pane=scope??store.focusedPane;
 const selection=store.selections[pane]??blankSelection;
 const {choose,selectionRef,revision,changed,drafts}=store;
 const select=useCallback((id:string,expected?:Selection)=>choose(pane,id,undefined,expected),[choose,pane]);
 return {...selection,selection,select,isCurrent:()=>selection===(selectionRef.current[pane]??blankSelection),revision,changed,drafts,pane};
}
function Icon({kind}:{kind:'sidebar'|'new'|'send'|'stop'|'attach'|'chat'}){
 const paths={sidebar:'M3 4h18v16H3z M9 4v16 M5.5 8h1 M5.5 12h1',new:'M12 5v14 M5 12h14',send:'M12 20V4 M5 11l7-7 7 7',stop:'M6 6h12v12H6z',attach:'M8 12l6-6a4 4 0 016 6l-9 9a6 6 0 01-8-8l9-9 M7 15l9-9',chat:'M4 4h16v13H9l-5 4z M8 8h8 M8 12h5'};
 return <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[kind]}/></svg>;
}
export function SidebarToggle({open,toggle}:{open:boolean;toggle:()=>void}){return <button id="core-ai-explorer-toggle" className="icon-button sidebar-toggle" aria-label={open?'Hide sidebar':'Show sidebar'} title={(open?'Hide':'Show')+' sidebar · Ctrl B'} aria-expanded={open} aria-controls={open?'core-ai-explorer':undefined} onClick={toggle}><Icon kind="sidebar"/></button>;}
export function NewChatButton({open}:{open:()=>void}){return <button className="new-chat" onClick={()=>{window.dispatchEvent(new Event('core-ai-new-chat'));open();}}><Icon kind="new"/>New chat</button>;}
export function ChatHistory({tick,open,navigation}:{tick:number;open:()=>void;navigation:ReactNode}){
 const {id,select,revision,changed}=useChat();
 const [items,setItems]=useState<Conversation[]>([]),[query,setQuery]=useState(''),[archived,setArchived]=useState(false),[error,setError]=useState(''),[search,setSearch]=useState('');
 useEffect(()=>{const t=setTimeout(()=>setSearch(query),250);return()=>clearTimeout(t);},[query]);
 useEffect(()=>{let alive=true;api('chat/conversations?archived='+archived+'&q='+encodeURIComponent(search)).then(x=>{if(alive){setItems(x);setError('');}}).catch(e=>{if(alive)setError(e.message);});return()=>{alive=false;};},[tick,revision,search,archived]);
 async function update(c:Conversation,patch:Record<string,unknown>){try{await api('chat/conversations/'+c.id,'PATCH',patch);changed();}catch(e){setError((e as Error).message);}}
 return <div className="chat-history"><div className="history-actions"><NewChatButton open={open}/><div className="history-search"><Search size={16} aria-hidden="true"/><input aria-label="Search conversations" placeholder="Search conversations…" value={query} onChange={e=>setQuery(e.target.value)}/></div></div><div className="explorer-scroll">{navigation}<div className="history-heading"><span>{archived?'ARCHIVE':'CONVERSATIONS'}</span><button aria-pressed={archived} onClick={()=>setArchived(x=>!x)}>{archived?'Back':'Archive'}</button></div>{error&&<div className="inline-error" role="alert">{error}</div>}<div className="history-scroll">{items.map(c=><div className={'history-item '+(id===c.id?'selected':'')} key={c.id}><button className="history-title" aria-current={id===c.id?'true':undefined} title={c.title} onClick={()=>{select(c.id);open();}}>{c.pinned?<Pin size={16} aria-label="Pinned"/>:<MessageSquare size={16} aria-hidden="true"/>}<span className="history-name">{c.title}</span><small>{new Date(c.updated_at).toLocaleDateString(undefined,{month:'short',day:'numeric'})}</small></button><details className="history-menu"><summary aria-label={'Actions for '+c.title}><Ellipsis size={16} aria-hidden="true"/></summary><div><button onClick={()=>{const title=prompt('Conversation title',c.title);if(title?.trim())void update(c,{title:title.trim()});}}>Rename</button><button onClick={()=>void update(c,{pinned:!c.pinned})}>{c.pinned?'Unpin':'Pin'}</button><button onClick={()=>void update(c,{archived:!c.archived})}>{c.archived?'Restore':'Archive'}</button><button onClick={async()=>{if(!confirm('Delete this conversation and all its messages?'))return;try{await api('chat/conversations/'+c.id,'DELETE');if(id===c.id)select('');changed();}catch(e){setError((e as Error).message);}}}>Delete</button></div></details></div>)}{!items.length&&!error&&<div className="history-empty">{search?'No matching conversations.':archived?'No archived conversations.':'Your saved conversations appear here.'}</div>}</div></div><div className="history-foot">Private to your CORE-AI account · latest 200</div></div>;
}
function CodeBlock({children}:{children?:ReactNode}){const ref=useRef<HTMLPreElement>(null),[copied,setCopied]=useState(false);return <div className="code-block"><header><span>Code</span><button onClick={async()=>{try{await navigator.clipboard.writeText(ref.current?.textContent||'');setCopied(true);setTimeout(()=>setCopied(false),1800);}catch{setCopied(false);}}}>{copied?'Copied':'Copy code'}</button></header><pre ref={ref}>{children}</pre></div>;}
export function MessageMarkdown({text}:{text:string}){return <div className="message-markdown"><Markdown remarkPlugins={[remarkGfm,remarkMath]} rehypePlugins={[[rehypeKatex,{trust:false,maxExpand:1000,maxSize:10}]]} skipHtml urlTransform={url=>/^(https?:\/\/|mailto:|#)/i.test(url)?url:''} components={{pre:({children})=><CodeBlock>{children}</CodeBlock>,a:({children,href})=><a href={href} target={href?.startsWith('#source:')?undefined:'_blank'} rel="noopener noreferrer" onClick={e=>{if(href?.startsWith('#source:')){e.preventDefault();window.dispatchEvent(new CustomEvent('core-ai-source',{detail:{id:href.slice(8)}}));}}}>{children}</a>,img:({alt})=><span className="attachment-reference">[Image reference: {alt||'image'}]</span>}}>{text.replace(/\[([0-9a-f]{8}-[0-9a-f-]{27})\](?!\()/gi,(_,id)=>'[Source '+id.slice(0,8)+'](#source:'+id+')')}</Markdown></div>;}
function exportChat(c:Conversation){const text='# '+c.title+'\n\n'+c.messages.map(m=>'## '+(m.role==='user'?'You':'CORE-AI')+'\n\n'+m.content+(m.attachments.length?'\n\nAttachments: '+m.attachments.map(a=>a.name).join(', '):'')).join('\n\n');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown'}));const a=document.createElement('a');a.href=url;a.download='core-ai-conversation.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
export default function Chat({tick,visible=true,sendKey='Enter',chatDefaults=defaultChat}:{tick:number;visible?:boolean;sendKey?:'Enter'|'CtrlEnter';chatDefaults?:ChatDefaults}){
 const {id,select,revision,changed,drafts,newChat,pane,selection,isCurrent}=useChat();
 const viewer=useSession().role==='VIEWER';
 const draftSlot=pane+'/'+(id||(newChat?.projectId?'project:'+newChat.projectId:''));
 const optionsId=useId(), messageId=useId();
 const [agents,setAgents]=useState<any[]>([]),[library,setLibrary]=useState<any[]>([]),[picker,setPicker]=useState(false),[uploading,setUploading]=useState<number|null>(null),[jump,setJump]=useState(false);
 const [thread,setThread]=useState<Conversation|null>(null),[error,setError]=useState(''),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[stopping,setStopping]=useState(false),[draft,setDraft]=useState(''),[attachments,setAttachments]=useState<Attachment[]>([]),[prefs,setPrefs]=useState<Preferences>({...chatDefaults,model:'',instructions:'',project_id:null}),[settings,setSettings]=useState(false),[modelState,setModelState]=useState<any>(null),[projects,setProjects]=useState<any[]>([]),[edit,setEdit]=useState<Message|null>(null),[copied,setCopied]=useState(''),[notice,setNotice]=useState(''),[modelsBusy,setModelsBusy]=useState(false);
 const fileInput=useRef<HTMLInputElement>(null),scroll=useRef<HTMLDivElement>(null),composer=useRef<HTMLTextAreaElement>(null),hydrated=useRef(''),sequence=useRef(0),alive=useRef(true),request=useRef<{key:string;fingerprint:string}|null>(null),draftKey=useRef(draftSlot),defaultsRef=useRef(chatDefaults),defaultModel=useRef(''),atBottom=useRef(true),sending=useRef(false),prefsRef=useRef(prefs);
 prefsRef.current=prefs;
 defaultsRef.current=chatDefaults;
 const generation=thread?.id===id?thread.generation:null;
 const generating=!!generation;
 const patch=(p:Partial<Preferences>)=>setPrefs(x=>({...x,...p}));
 const refreshModels=useCallback(async()=>{setModelsBusy(true);try{const m=await api('models');if(!alive.current)return;setModelState(m);defaultModel.current=m.config.model;if(!prefsRef.current.model)patch({model:defaultModel.current});}catch(e){if(alive.current)setError((e as Error).message);}finally{if(alive.current)setModelsBusy(false);}},[]);
 useEffect(()=>{alive.current=true;void refreshModels();api('projects').then(p=>{if(alive.current)setProjects(p);}).catch(()=>{});return()=>{alive.current=false;sequence.current++;};},[refreshModels]);
 const load=useCallback(async()=>{if(!id)return;const seq=++sequence.current;try{const c=await api('chat/conversations/'+id);if(alive.current&&seq===sequence.current){setThread(c);if(hydrated.current!==id){hydrated.current=id;setPrefs(drafts.current[draftSlot]?.preferences??{model:c.model,mode:c.mode,instructions:c.instructions,project_id:c.project_id,temperature:c.temperature,max_tokens:c.max_tokens,agent_id:c.agent_id});}setError('');}}catch(e){if(alive.current&&seq===sequence.current){setError((e as Error).message);if((e as any).status===404){select('',selection);changed();}}}finally{if(alive.current&&seq===sequence.current)setLoading(false);}},[id,select,changed,drafts,draftSlot,selection]);
 useEffect(()=>{
  sequence.current++;
  setThread(null);setEdit(null);setError('');setStopping(false);setPicker(false);
  atBottom.current=true;
  const saved:Draft=drafts.current[draftSlot]??emptyDraft;
  setDraft(saved.text);setAttachments(saved.attachments);
  hydrated.current='';
  setLoading(!!id);
  if(id)void load();
  else setPrefs(saved.preferences??{...defaultsRef.current,model:defaultModel.current,instructions:'',project_id:newChat?.projectId??null});
 },[id,load,newChat,drafts,draftSlot]);
 useEffect(()=>{if(draftKey.current===draftSlot&&(!id||hydrated.current===id))drafts.current[draftSlot]={text:draft,attachments,preferences:prefs};},[draft,attachments,prefs,drafts,draftSlot,id]);
 useEffect(()=>{draftKey.current=draftSlot;},[draftSlot]);
 useEffect(()=>{if(visible){api('agents').then(setAgents).catch(()=>{});api('projects').then(setProjects).catch(()=>{});}},[tick,visible]);
 useEffect(()=>{if(!attachments.some(a=>a.file_id&&a.status!=='READY'&&a.status!=='FAILED'))return;const timer=setInterval(async()=>{const pending=attachments.filter(a=>a.file_id&&a.status!=='READY'&&a.status!=='FAILED');const done=await Promise.all(pending.map(a=>api('files/'+a.file_id).catch(()=>null)));if(alive.current&&isCurrent())setAttachments(old=>old.map(a=>{const f=done.find(x=>x?.id===a.file_id);return f?{...a,status:f.status}:a;}));},1500);return()=>clearInterval(timer);},[attachments,selection]);
 useEffect(()=>{if(id&&visible)void load();},[tick,revision,id,visible,load]);
 useEffect(()=>{if(!generating||!visible)return;const timer=setInterval(()=>{if(document.visibilityState!=='hidden')void load();},900);return()=>clearInterval(timer);},[generating,visible,load]);
 useEffect(()=>{if(!generating)setStopping(false);},[generating]);
 const messages=thread?.id===id?thread.messages:[];
 const lastMessage=messages[messages.length-1];
 useEffect(()=>{if(atBottom.current&&scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight;},[id,lastMessage?.content,messages.length]);
 useEffect(()=>{if(composer.current){composer.current.style.height='auto';composer.current.style.height=Math.min(180,Math.max(46,composer.current.scrollHeight))+'px';}},[draft]);
 const textModels=(modelState?.models||[]).filter((m:any)=>!/(embed|bge-m3|nomic-embed)/i.test(m.name));
 async function send(e?:FormEvent){
  e?.preventDefault();
  if(sending.current||generating||loading||(id&&thread?.id!==id)||!draft.trim()||!prefs.model||!modelState?.available||thread?.archived||viewer||uploading!==null||attachments.some(a=>a.file_id&&a.status!=='READY'))return;
  sending.current=true;setBusy(true);setError('');
  let conversationId=id;
  try{
   if(!conversationId){
    const c=await api('chat/conversations','POST',{...prefs,title:'New chat'});
    conversationId=c.id;
   }
   const body={...prefs,content:draft,attachments:attachments.filter(a=>!a.file_id).map(a=>({name:a.name,content:a.content})),file_ids:attachments.filter(a=>a.file_id).map(a=>a.file_id)};
   const fingerprint=JSON.stringify({conversationId,edit:edit?.id,...body});
   if(!request.current||request.current.fingerprint!==fingerprint)request.current={key:crypto.randomUUID(),fingerprint};
   const response=await api('chat/conversations/'+conversationId+(edit?'/fork':'/messages'),'POST',{...body,request_id:request.current.key,...(edit?{message_id:edit.id}:{})});
   request.current=null;
   if(isCurrent()){
    delete drafts.current[draftSlot];
    drafts.current[pane+'/'+response.conversation_id]={text:'',attachments:[],preferences:prefs};
    if(alive.current){setDraft('');setAttachments([]);setEdit(null);atBottom.current=true;setNotice('');}
    if(response.conversation_id!==id)select(response.conversation_id,selection);
   }
   changed();
  }catch(e){
   if(isCurrent()){
    if(conversationId&&!id){
     drafts.current[pane+'/'+conversationId]={text:draft,attachments,preferences:prefs};
     select(conversationId,selection);
    }
    if(alive.current)setError((e as Error).message);
   }
  }finally{sending.current=false;if(alive.current)setBusy(false);}
 }
 async function stop(){if(!id||stopping)return;setStopping(true);try{await api('chat/conversations/'+id+'/stop','POST',{});await load();changed();}catch(e){setError((e as Error).message);setStopping(false);}}
 async function regenerate(){const question=[...messages].reverse().find(m=>m.role==='user');if(!question)return;setBusy(true);setError('');try{const r=await api('chat/conversations/'+id+'/fork','POST',{...prefs,content:question.content,attachments:question.attachments,message_id:question.id,request_id:crypto.randomUUID()});select(r.conversation_id,selection);changed();}catch(e){setError((e as Error).message);}finally{setBusy(false);}}
 async function attach(files:FileList|null){if(!files||viewer)return;try{if(attachments.length+files.length>4)throw new Error('Attach up to four files.');for(const f of Array.from(files)){if(!isCurrent())break;setUploading(0);const result=await uploadFile(f,prefs.project_id,setUploading);if(alive.current&&isCurrent())setAttachments(old=>[...old,{name:result.name,content:'',file_id:result.id,status:result.status}]);}if(isCurrent())setError('');}catch(e){if(isCurrent())setError((e as Error).message);}finally{setUploading(null);if(fileInput.current)fileInput.current.value='';}}
 async function openPicker(){try{const files=await api('files');if(isCurrent()){setLibrary(files);setPicker(x=>!x);}}catch(e){setError((e as Error).message);}}
 async function saveArtifact(m:Message){try{const result=await api('library/artifacts','POST',{title:thread?.title||'Chat document',kind:'markdown',content:m.content,source_message_id:m.id,project_id:prefs.project_id});window.dispatchEvent(new CustomEvent('core-ai-artifact',{detail:{id:result.id}}));setNotice('Saved as a versioned artifact.');}catch(e){setError((e as Error).message);}}

 async function copy(m:Message){try{await navigator.clipboard.writeText(m.content);setCopied(m.id);setTimeout(()=>setCopied(''),1800);}catch{setError('Clipboard access was denied. Select the reply text to copy it.');}}
 return <section className="chat-workspace" aria-label="Chat workspace"><header className="chat-top"><div className="chat-model"><select aria-label="Chat model" value={prefs.model} onChange={e=>patch({model:e.target.value})}><option value="">Choose a model</option>{prefs.model&&!textModels.some((m:any)=>m.name===prefs.model)&&<option value={prefs.model}>{prefs.model}</option>}{textModels.map((m:any)=><option key={m.name}>{m.name}</option>)}</select><span className={'model-connection '+(modelState?.available?'online':'offline')}>{modelState?modelState.available?'Local inference':'Model host offline':'Checking models…'}</span></div><div className="chat-top-actions"><select aria-label="Response style" value={prefs.mode} title={chatModes.find(mode=>mode.value===prefs.mode)?.description} onChange={e=>patch({mode:e.target.value as Preferences['mode']})}>{chatModes.map(({value,label})=><option key={value} value={value}>{label}</option>)}</select><button aria-expanded={settings} aria-controls={optionsId} onClick={()=>setSettings(x=>!x)}>Options</button>{thread&&<button onClick={()=>exportChat(thread)}>Export</button>}<button aria-label="Refresh chat models" disabled={modelsBusy} onClick={()=>void refreshModels()}>↻</button></div></header>
 {settings&&<div className="chat-options" id={optionsId}><label>Project context<select value={prefs.project_id||''} onChange={e=>patch({project_id:e.target.value||null})}><option value="">None · general conversation</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label>Temperature <span>{prefs.temperature.toFixed(1)}</span><input type="range" min="0" max="1.5" step="0.1" value={prefs.temperature} onChange={e=>patch({temperature:+e.target.value})}/></label><label>Agent profile · instructions<select aria-label="Chat agent profile" value={prefs.agent_id||''} onChange={e=>patch({agent_id:e.target.value||null})}><option value="">Default assistant</option>{agents.filter(a=>a.enabled).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label><label>Maximum reply tokens<select value={prefs.max_tokens} onChange={e=>patch({max_tokens:+e.target.value})}>{replyTokenOptions.map(n=><option key={n} value={n}>{n}</option>)}</select></label><label className="instructions-field">Response instructions<textarea aria-label="Chat response instructions" maxLength={4000} rows={2} value={prefs.instructions} onChange={e=>patch({instructions:e.target.value})} placeholder="Preferred tone, format, expertise or constraints…"/></label><small>{chatModes.find(mode=>mode.value===prefs.mode)?.description}. Changes apply to your next message.</small></div>}
 <div className="chat-scroll" ref={scroll} onScroll={e=>{const el=e.currentTarget;atBottom.current=el.scrollHeight-el.scrollTop-el.clientHeight<100;setJump(!atBottom.current);}}>
 {loading&&!messages.length?<div className="chat-loading" role="status">Loading conversation…</div>:!messages.length?<div className="chat-welcome"><div className="welcome-mark">◈</div><h1>How can I help?</h1><p>A clear space for everyday questions and professional work.</p><div className="starter-grid">{(prefs.mode==='quick'?starters.general:starters[prefs.mode]).map(([label,text])=><button key={label} disabled={viewer} onClick={()=>{setDraft(current=>current.trim()?(current+'\n\n'+text).slice(0,16000):text);composer.current?.focus();}}><b>{label}</b><span>{text}</span></button>)}</div></div>:<div className="conversation" role="log" aria-label="Conversation messages" aria-live="off"><div className="conversation-label"><span>{thread?.title}</span>{thread?.pinned&&<small>Pinned</small>}{thread?.archived&&<small>Archived · restore in sidebar to continue</small>}</div>{messages.map((m,index)=><article key={m.id} className={'message '+m.role} aria-label={(m.role==='user'?'Your message':'CORE-AI reply')+' '+(index+1)}><div className="message-meta"><span className="message-avatar">{m.role==='user'?'Y':'◈'}</span><b>{m.role==='user'?'You':'CORE-AI'}</b>{m.role==='assistant'&&<span className="message-model">{m.model}</span>}<time>{new Date(m.created_at).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})}</time></div><div className="message-content">{m.role==='assistant'?<MessageMarkdown text={m.content}/>:<div className="user-text">{m.content}</div>}{m.attachments.length>0&&<div className="message-files">{m.attachments.map((f,i)=><details key={i}><summary>▧ {f.name}</summary><pre>{f.content}</pre></details>)}</div>}{['QUEUED','RUNNING','CANCEL_REQUESTED'].includes(m.status)&&<div className="reply-state" role="status"><i/>{m.status==='QUEUED'?'Queued · waiting for the inference slot':m.status==='CANCEL_REQUESTED'?'Stopping…':'Generating…'}</div>}{m.error&&<div className="inline-error" role="alert">{m.error}</div>}{m.status==='CANCELLED'&&<small className="reply-note">Stopped · partial reply retained</small>}<div className="message-actions">{m.content&&<button onClick={()=>void copy(m)}>{copied===m.id?'Copied':'Copy'}</button>}{m.role==='user'&&!generating&&!busy&&!viewer&&<button onClick={()=>{setEdit(m);setDraft(m.content);setAttachments(m.attachments);composer.current?.focus();}}>Edit & branch</button>}{m.role==='assistant'&&m.content&&!viewer&&<button onClick={()=>void saveArtifact(m)}>Open as artifact</button>}{m.role==='assistant'&&index===messages.length-1&&!generating&&!viewer&&<button disabled={busy} onClick={()=>void regenerate()}>{m.status==='FAILED'?'Retry':'Regenerate'}</button>}</div></div></article>)}</div>}
 </div><div className="composer-area">{jump&&<button className="jump-latest" onClick={()=>{if(scroll.current)scroll.current.scrollTop=scroll.current.scrollHeight;atBottom.current=true;setJump(false);}}>↓ Jump to latest</button>}{uploading!==null&&<div className="upload-progress" role="status">Uploading {uploading}%<progress max={100} value={uploading}/></div>}{viewer&&<div className="connection-note">Read-only account. An editor role is required to send messages.</div>}{error&&<div className="inline-error" role="alert">{error}</div>}{notice&&<div role="status">{notice}</div>}{modelState&&!modelState.available&&<div className="connection-note">The model host is offline. Start the laptop and Ollama, then refresh models.</div>}{edit&&<div className="edit-banner">Editing an earlier message creates a new branch and preserves the original conversation.<button onClick={()=>{setEdit(null);setDraft('');setAttachments([]);}}>Cancel edit</button></div>}<form className={'chat-composer '+(generating?'is-generating':'')} onSubmit={send}><label className="sr-only" htmlFor={messageId}>Message CORE-AI</label><textarea id={messageId} ref={composer} aria-label="Message CORE-AI" value={draft} maxLength={16000} disabled={viewer} placeholder={generating?'You can draft your next message while CORE-AI replies…':'Message CORE-AI…'} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.nativeEvent.isComposing&&(sendKey==='Enter'||e.ctrlKey||e.metaKey)){e.preventDefault();if(!generating)void send();}}}/>{attachments.length>0&&<div className="composer-files">{attachments.map((a,i)=><span key={i}>▧ {a.name}{a.file_id&&<small> · {a.status?.toLowerCase()}</small>}<button type="button" aria-label={'Remove '+a.name} onClick={()=>setAttachments(x=>x.filter((_,j)=>i!==j))}>×</button></span>)}</div>}<div className="composer-controls"><input type="file" ref={fileInput} className="sr-only" multiple accept=".txt,.md,.csv,.json,.pdf,.docx,.xlsx,.py,.js,.ts,.tsx,.jsx,.sql,.yaml,.yml,.log,.html,.css,.xml,.toml,.ini,.sh,.ps1" onChange={e=>void attach(e.target.files)}/><button className="attach-button" type="button" aria-label="Upload supported files" title="Upload text, code, PDF, DOCX or XLSX" disabled={viewer||uploading!==null} onClick={()=>fileInput.current?.click()}><Icon kind="attach"/></button><button type="button" className="library-picker-button" disabled={viewer} aria-pressed={picker} onClick={()=>void openPicker()}>Library</button><button type="button" className="composer-context" aria-label="Conversation context" aria-expanded={settings} aria-controls={optionsId} title={[prefs.project_id?projects.find(p=>p.id===prefs.project_id)?.name||'Project context':'Private conversation',agents.find(a=>a.id===prefs.agent_id)?.name].filter(Boolean).join(' · ')} onClick={()=>setSettings(x=>!x)}>{prefs.project_id?projects.find(p=>p.id===prefs.project_id)?.name||'Project context':'Private conversation'}</button><span className="composer-hint">{sendKey==='Enter'?'Enter':'Ctrl Enter'} to send · Shift Enter for a new line</span>{generating?<button type="button" className="send-button stop-button" aria-label="Stop reply" disabled={stopping} onClick={()=>void stop()}><Icon kind="stop"/></button>:<button type="submit" className="send-button" aria-label="Send message" disabled={viewer||busy||loading||(!!id&&thread?.id!==id)||uploading!==null||attachments.some(a=>a.file_id&&a.status!=='READY')||!draft.trim()||!prefs.model||!modelState?.available||thread?.archived}><Icon kind="send"/></button>}</div>{picker&&<div className="composer-library"><b>Choose a processed file</b><button type="button" aria-label="Close file picker" onClick={()=>setPicker(false)}>×</button>{library.filter(f=>f.status==='READY').map(f=><button key={f.id} type="button" disabled={attachments.some(a=>a.file_id===f.id)||attachments.length>=4} onClick={()=>{setAttachments(a=>[...a,{name:f.name,content:'',file_id:f.id,status:f.status}]);setPicker(false);}}>▧ {f.name}</button>)}{library.filter(f=>f.status==='READY').length===0&&<p>No ready files. Upload a file or check its processing status in Files.</p>}</div>}</form><div className="composer-footnote"><span>CORE-AI can make mistakes. Check important information.</span><span>Self-hosted · {chatModes.find(mode=>mode.value===prefs.mode)?.label} · Text, PDF & Office files</span></div></div></section>;
}
