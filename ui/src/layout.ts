export const views=['Overview','Projects','Agents','Tasks','Knowledge','Artifacts','Models','Tools','Integrations','Operations','Settings'] as const;
export type View=typeof views[number];
export type Layout={version:1;workspace:'Build'|'Research'|'Operations';groups:View[][];active:View[];focus:number;axis:'row'|'column';left:boolean;right:boolean;bottom:boolean;leftWidth:number;rightWidth:number;bottomHeight:number;maximized:boolean};
export const key='core-ai.workstation.layout.v1';
export function defaults():Layout{return {version:1,workspace:'Build',groups:[['Overview']],active:['Overview'],focus:0,axis:'row',left:true,right:false,bottom:true,leftWidth:230,rightWidth:270,bottomHeight:155,maximized:false};}
export function restore(raw:string|null):Layout{
 try{const x=JSON.parse(raw||'null');
  if(!x||x.version!==1||!['Build','Research','Operations'].includes(x.workspace)||!Array.isArray(x.groups)||x.groups.length<1||x.groups.length>4||!Array.isArray(x.active)||x.active.length!==x.groups.length) return defaults();
  if(x.groups.some((g:unknown)=>!Array.isArray(g)||g.length<1||g.length>views.length||new Set(g).size!==g.length||g.some(v=>!views.includes(v)))||x.active.some((v:View,i:number)=>!x.groups[i].includes(v))) return defaults();
  if(!Number.isInteger(x.focus)||x.focus<0||x.focus>=x.groups.length||!['row','column'].includes(x.axis)||['left','right','bottom','maximized'].some(k=>typeof x[k]!=='boolean'))return defaults();
  for(const [k,min,max]of [['leftWidth',160,380],['rightWidth',200,440],['bottomHeight',100,400]] as const)if(!Number.isFinite(x[k])||x[k]<min||x[k]>max)return defaults();
  return x;
 }catch{return defaults();}
}
export function closeTab(x:Layout,v:View,group:number):Layout{
 const groups=x.groups.map(g=>[...g]),active=[...x.active];groups[group]=groups[group].filter(t=>t!==v);
 if(!groups[group].length){if(groups.length===1){groups[0]=['Overview'];active[0]='Overview';}else{groups.splice(group,1);active.splice(group,1);}}
 else if(active[group]===v)active[group]=groups[group][0];
 return {...x,groups,active,focus:Math.min(x.focus,groups.length-1),maximized:false};
}
