import {useState} from 'react';

export type Program={id:string;repository:string;commit:string;runtime:string;fields:string|string[];example:unknown[];extensions:string[];output_file:boolean;mode:string;state:string;image?:string;scope?:string|null};
export type Model={name:string;size?:number;capabilities?:string[]|null};
export function generationModel(m:Model){
 return Array.isArray(m.capabilities)?m.capabilities.includes('completion'):!/(embed|bge-m3)/i.test(m.name);
}
export function modelLabel(m:Model){return m.name+(Array.isArray(m.capabilities)?(m.capabilities.includes('tools')?' · tools':''):' · capability unverified');}
export function title(value:string){return value.replaceAll('-',' ').replaceAll('_',' ').replace(/^./,c=>c.toUpperCase());}
export function names(p:Program){
 if(Array.isArray(p.fields)&&p.fields.length===p.example.length)return p.fields;
 if(typeof p.fields==='string'){
  const parts=p.fields.split(',').map(v=>v.trim());
  if(parts.length===p.example.length)return parts;
 }
 return p.example.length===1?[String(p.fields)]:p.example.map((_,i)=>'Value '+(i+1));
}
export function ParameterEditor({program,value,onChange,disabled=false}:{program:Program;value:string;onChange:(v:string)=>void;disabled?:boolean}){
 const [advanced,setAdvanced]=useState(false);
 let parsed:unknown[]|null=null;
 try{const x=JSON.parse(value);if(Array.isArray(x))parsed=x;}catch{}
 const fields=names(program);
 const simple=parsed!==null&&parsed.length===program.example.length&&program.example.every(v=>['number','string','boolean'].includes(typeof v));
 function edit(i:number,raw:unknown){if(!parsed)return;const next=[...parsed];next[i]=raw;onChange(JSON.stringify(next,null,2));}
 return <div className="form">
  {!advanced&&simple?<div className="fields">{fields.map((field,i)=>{
    const kind=typeof program.example[i],v=parsed![i];
    return <label key={i}>{title(field)}{/(risk_pct|win_rate|annual_rate|annual_volatility|dividend_yield|fee_rate|slippage)/.test(field)&&<small>Decimal as in the example (0.01 = 1% for rate fields)</small>}
      {kind==='boolean'?<input type="checkbox" checked={v===true} disabled={disabled} onChange={e=>edit(i,e.target.checked)}/>:kind==='number'?<input type="number" step="any" required value={typeof v==='number'?v:''} disabled={disabled} onChange={e=>edit(i,e.target.value===''?null:e.target.valueAsNumber)}/>:<input required value={typeof v==='string'?v:''} disabled={disabled} onChange={e=>edit(i,e.target.value)}/>}</label>;
  })}</div>:<label>Structured parameters<textarea rows={7} value={value} disabled={disabled} onChange={e=>onChange(e.target.value)} spellCheck={false}/><small>{fields.join(' · ')||'No arguments needed.'} Use the example to preserve parameter order.</small></label>}
  {simple&&<button type="button" onClick={()=>setAdvanced(!advanced)}>{advanced?'Use guided inputs':'Advanced JSON'}</button>}
  <button type="button" disabled={disabled} onClick={()=>onChange(JSON.stringify(program.example,null,2))}>Use qualification example</button>
 </div>;
}
