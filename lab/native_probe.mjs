// Persistent, loopback-only native registration probe. No model calls.
import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

const validId=x=>typeof x==='string'&&/^[A-Za-z0-9_.:/@-]{1,160}$/.test(x);
const ids=(d,activeOnly=false)=>{
 if(!Array.isArray(d?.data)||d?.location?.directory!=='/workspace')throw Error('invalid location inventory');
 return d.data.filter(x=>validId(x?.id)&&(!activeOnly||x?.state?.status==='active')).map(x=>x.id).slice(0,300);
};
const diagnostics=x=>['permission denied','cannot find','not a directory','plugin disabled','module not found','failed to load','read-only file system'].filter(k=>String(x).toLowerCase().includes(k));

export async function observe(read,profile,expected,{timeout=60000,interval=500,now=Date.now,sleep=delay,alive=()=>true}={}){
 const deadline=now()+timeout;
 let version=null,plugins=[],skills=[],failed=[],attempts=0,apiStatus={};
 while(now()<deadline&&alive()){
  attempts++;
  try{
   const info=await read('/api/info');
   version=/^\d+\.\d+\.\d+$/.test(info?.version||'')?info.version:null;
   apiStatus.info='ok';
  }catch(e){apiStatus.info=e.status||'unavailable';}
  try{
   const p=await read('/api/plugin');
   plugins=ids(p,true);
   failed=p.data.filter(x=>x?.state?.status==='failed').slice(0,30).map(x=>({id:validId(x.id)?x.id:null,diagnostics:diagnostics(x.state.error)}));
   apiStatus.plugin='ok';
  }catch(e){apiStatus.plugin=e.status||'unavailable';}
  try{
   skills=ids(await read('/api/skill'));
   apiStatus.skill='ok';
  }catch(e){apiStatus.skill=e.status||'unavailable';}
  if(version&&plugins.includes(profile)&&expected.length&&expected.every(s=>skills.includes(s)))break;
  await sleep(interval);
 }
 return {version,plugins,skills,failed,attempts,api_status:apiStatus};
}

export async function main(){
 const profile=process.env.PROFILE_NAME,expected=JSON.parse(process.env.PROFILE_SKILLS);
 // Generated inside the container, never printed, persisted or passed in arguments.
 const password=randomBytes(32).toString('hex');
 const proc=spawn('/opt/opencode/node_modules/.bin/opencode',['serve','--hostname','127.0.0.1','--port','4096'],{
  cwd:'/workspace',env:{...process.env,OPENCODE_PASSWORD:password,OPENCODE_DISABLE_MODELS_FETCH:'1'},stdio:['ignore','pipe','pipe']
 });
 let ended=false,tail='';
 proc.on('error',()=>{ended=true;});
 proc.on('exit',()=>{ended=true;});
 for(const stream of [proc.stdout,proc.stderr])stream.on('data',chunk=>{tail=(tail+chunk.toString()).slice(-16384);});
 const read=async endpoint=>{
  const url=new URL(endpoint,'http://127.0.0.1:4096');
  if(endpoint!=='/api/info')url.searchParams.set('location[directory]','/workspace');
  const res=await fetch(url,{headers:{Authorization:'Basic '+Buffer.from('opencode:'+password).toString('base64')},redirect:'error',signal:AbortSignal.timeout(2500)});
  if(!res.ok){const error=new Error('HTTP error');error.status=res.status;throw error;}
  const reader=res.body.getReader();let length=0;const chunks=[];
  try{for(;;){const r=await reader.read();if(r.done)break;length+=r.value.byteLength;if(length>8*1024*1024)throw Error('response too large');chunks.push(Buffer.from(r.value));}}
  finally{await reader.cancel().catch(()=>{});}
  return JSON.parse(Buffer.concat(chunks).toString('utf8'));
 };
 try{
  const report=await observe(read,profile,expected,{alive:()=>!ended});
  console.log(JSON.stringify({...report,diagnostics:diagnostics(tail)}));
 }finally{
  proc.kill('SIGTERM');
  for(let i=0;i<20&&!ended;i++)await delay(100);
  if(!ended)proc.kill('SIGKILL');
 }
}
