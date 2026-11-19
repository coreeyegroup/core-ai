export const views=['Chat','Overview','Projects','Files','Agents','Tasks','Knowledge','Artifacts','Models','Tools','Integrations','Operations','Access','Capabilities','Workflows','Settings'] as const;
export type View=typeof views[number];
export type Layout={version:1;workspace:'Build'|'Research'|'Operations';groups:View[][];paneIds:string[];active:View[];focus:number;axis:'row'|'column';left:boolean;right:boolean;bottom:boolean;leftWidth:number;rightWidth:number;bottomHeight:number;maximized:boolean};
export const key='core-ai.workstation.layout.v2';
export function defaults():Layout{return {version:1,workspace:'Build',groups:[['Chat']],paneIds:['primary'],active:['Chat'],focus:0,axis:'row',left:true,right:false,bottom:false,leftWidth:260,rightWidth:400,bottomHeight:155,maximized:false};}
export function restore(raw:string|null):Layout{
 try{const x=JSON.parse(raw||'null');
  if(!x||x.version!==1||!['Build','Research','Operations'].includes(x.workspace)||!Array.isArray(x.groups)||x.groups.length<1||x.groups.length>4||!Array.isArray(x.active)||x.active.length!==x.groups.length) return defaults();
  if(x.groups.some((g:unknown)=>!Array.isArray(g)||g.length<1||g.length>views.length||new Set(g).size!==g.length||g.some(v=>!views.includes(v)))||x.active.some((v:View,i:number)=>!x.groups[i].includes(v))) return defaults();
  if(!Number.isInteger(x.focus)||x.focus<0||x.focus>=x.groups.length||!['row','column'].includes(x.axis)||['left','right','bottom','maximized'].some(k=>typeof x[k]!=='boolean'))return defaults();
  for(const [k,min,max]of [['leftWidth',200,380],['rightWidth',260,1000],['bottomHeight',100,400]] as const)if(!Number.isFinite(x[k])||x[k]<min||x[k]>max)return defaults();
  const validIds=Array.isArray(x.paneIds)&&x.paneIds.length===x.groups.length&&new Set(x.paneIds).size===x.groups.length&&x.paneIds.every((id:unknown)=>typeof id==='string'&&/^[a-z0-9-]{1,48}$/.test(id));
  return {...x,paneIds:validIds?x.paneIds:x.groups.map((_:unknown,index:number)=>index===0?'primary':'legacy-'+index)};
 }catch{return defaults();}
}
export function closeTab(x:Layout,v:View,group:number):Layout{
 const groups=x.groups.map(g=>[...g]),active=[...x.active],paneIds=[...x.paneIds];groups[group]=groups[group].filter(t=>t!==v);
 if(!groups[group].length){if(groups.length===1){groups[0]=['Chat'];active[0]='Chat';}else{groups.splice(group,1);active.splice(group,1);paneIds.splice(group,1);}}
 else if(active[group]===v)active[group]=groups[group][0];
 const focus=groups.length<x.groups.length&&group<x.focus?x.focus-1:x.focus;
 return {...x,groups,active,paneIds,focus:Math.min(focus,groups.length-1),maximized:false};
}
