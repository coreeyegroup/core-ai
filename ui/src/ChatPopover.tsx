import {useEffect,useId,useLayoutEffect,useRef,useState,type KeyboardEvent,type ReactNode} from 'react';
import {createPortal} from 'react-dom';
import {ChevronDown,Check} from 'lucide-react';

export function ChatPopover({label,children,trigger,kind,align='start',className='',buttonClass=''}:{
 label:string; trigger:ReactNode; kind:'menu'|'dialog'; align?:'start'|'end'; className?:string;buttonClass?:string;
 children:(dismiss:()=>void)=>ReactNode;
}){
 const [open,setOpen]=useState(false),[position,setPosition]=useState({left:0,top:0,maxHeight:0});
 const anchor=useRef<HTMLButtonElement>(null),panel=useRef<HTMLDivElement>(null);
 const id=useId();
 const dismiss=()=>{setOpen(false);anchor.current?.focus();};
 useLayoutEffect(()=>{
  if(!open||!anchor.current||!panel.current)return;
  const place=()=>{
   if(!anchor.current||!panel.current)return;
   const rect=anchor.current.getBoundingClientRect(),width=panel.current.offsetWidth;
   const below=window.innerHeight-rect.bottom-10,above=rect.top-10;
   const flip=below<Math.min(panel.current.scrollHeight,250)&&above>below;
   const maxHeight=Math.max(0,flip?above:below);
   const left=Math.min(Math.max(6,align==='end'?rect.right-width:rect.left),Math.max(6,window.innerWidth-width-6));
   setPosition({left,top:flip?rect.top-Math.min(panel.current.scrollHeight,maxHeight)-4:rect.bottom+4,maxHeight});
  };
  place();
  panel.current.querySelector<HTMLElement>('input,button:not([disabled])')?.focus({preventScroll:true});
  window.addEventListener('resize',place);
  window.addEventListener('scroll',place,true);
  return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);};
 },[open,align]);
 useEffect(()=>{
  if(!open)return;
  const outside=(e:PointerEvent)=>{const target=e.target as Node;if(!anchor.current?.contains(target)&&!panel.current?.contains(target))setOpen(false);};
  document.addEventListener('pointerdown',outside);
  return()=>document.removeEventListener('pointerdown',outside);
 },[open]);
 function keydown(e:KeyboardEvent<HTMLDivElement>){
  if(e.key==='Escape'){e.preventDefault();e.stopPropagation();dismiss();return;}
  if(e.key==='Tab'&&kind==='menu'){dismiss();return;}
  if(!['ArrowDown','ArrowUp','Home','End'].includes(e.key))return;
  if(e.target instanceof HTMLInputElement&&['Home','End'].includes(e.key))return;
  const items=Array.from(panel.current?.querySelectorAll<HTMLButtonElement>('button:not([disabled])')??[]);
  if(!items.length)return;
  const index=items.indexOf(document.activeElement as HTMLButtonElement);
  const next=e.key==='Home'?0:e.key==='End'?items.length-1:e.key==='ArrowDown'?(index+1)%items.length:(index<0?items.length-1:(index-1+items.length)%items.length);
  e.preventDefault();items[next].focus();
 }
 return <>
  <button type="button" className={buttonClass} ref={anchor} aria-label={label} aria-haspopup={kind} aria-expanded={open} aria-controls={open?id:undefined} onClick={()=>setOpen(value=>!value)} onKeyDown={e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();setOpen(true);}}}>{trigger}</button>
  {open&&createPortal(<div id={id} className={'chat-popover '+className} ref={panel} style={position} role={kind} aria-label={label} onKeyDown={keydown}
    onBlur={e=>{if(e.relatedTarget instanceof Node&&!panel.current?.contains(e.relatedTarget)&&!anchor.current?.contains(e.relatedTarget))setOpen(false);}}>
    {children(dismiss)}
  </div>,document.body)}
 </>;
}

export function ChatModelPicker({value,models,available,onChange}:{value:string;models:{name:string;capabilities?:string[]}[];available:boolean;onChange:(model:string)=>void}){
 const [query,setQuery]=useState('');
 const choices=models.filter(model=>model.name.toLowerCase().includes(query.trim().toLowerCase()));
 return <ChatPopover label="Chat model" kind="dialog" className="model-popover" buttonClass="model-picker-trigger" trigger={<><span>{value||'Choose a model'}</span><ChevronDown size={14}/></>}>
  {dismiss=><>
   <input type="search" aria-label="Search models" placeholder="Search models…" value={query} onChange={e=>setQuery(e.target.value)}/>
   {!available?<p>Model host is unavailable.</p>:choices.length===0?<p>No matching chat models.</p>:choices.map(model=><button key={model.name} type="button" aria-pressed={model.name===value} onClick={()=>{onChange(model.name);setQuery('');dismiss();}}>
    <span>{model.name}</span>{model.name===value&&<Check size={14} aria-hidden="true"/>}
   </button>)}
  </>}
 </ChatPopover>;
}


export function ConversationDialog({action,title,dismiss,confirm}:{action:'rename'|'delete';title:string;dismiss:()=>void;confirm:(title:string)=>Promise<void>}){
 const dialog=useRef<HTMLDialogElement>(null),id=useId();
 const [name,setName]=useState(title),[error,setError]=useState(''),[busy,setBusy]=useState(false);
 useLayoutEffect(()=>{
  const node=dialog.current,previous=document.activeElement as HTMLElement|null;
  if(!node)return;
  if(node.showModal)node.showModal();else node.setAttribute('open','');
  node.querySelector<HTMLElement>(action==='rename'?'input':'button')?.focus();
  return()=>{if(node.close)node.close();previous?.focus();};
 },[action]);
 return createPortal(<dialog className="conversation-dialog" ref={dialog} aria-labelledby={id} onCancel={e=>{e.preventDefault();if(!busy)dismiss();}}>
  <form onSubmit={async e=>{
   e.preventDefault();
   if(busy||!name.trim())return;
   setBusy(true);setError('');
   try{await confirm(name.trim());dismiss();}catch(e){setError((e as Error).message);setBusy(false);}
  }}>
   <h2 id={id}>{action==='rename'?'Rename conversation':'Delete conversation?'}</h2>
   {action==='rename'?<label>Conversation title<input maxLength={120} value={name} onChange={e=>setName(e.target.value)} required/></label>:<p>The conversation “{title}” and its messages will be permanently deleted.</p>}
   {error&&<p className="inline-error" role="alert">{error}</p>}
   <div><button type="button" disabled={busy} onClick={dismiss}>Cancel</button>
    <button type="submit" disabled={busy||!name.trim()} className={action==='delete'?'chat-menu-danger':undefined}>{action==='rename'?'Save name':'Delete'}</button>
   </div>
  </form>
 </dialog>,document.body);
}
