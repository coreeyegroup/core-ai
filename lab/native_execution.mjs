// Persistent private OpenCode server; only the filtered Ollama relay is reachable.
import {createServer,connect} from 'node:net';
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {once} from 'node:events';
import {randomBytes} from 'node:crypto';
import {setTimeout as delay} from 'node:timers/promises';

const config=JSON.parse(process.env.NATIVE_CONFIG);
const expected=JSON.parse(process.env.NATIVE_EXPECTED);
mkdirSync(process.env.XDG_CONFIG_HOME+'/opencode',{recursive:true});
writeFileSync(process.env.XDG_CONFIG_HOME+'/opencode/opencode.json',JSON.stringify(config));
delete process.env.OPENCODE_CONFIG;
const sockets=new Set();
const relay=createServer(client=>{
 const upstream=connect('/relay.sock');
 for(const s of [client,upstream]){
  sockets.add(s);
  s.on('close',()=>sockets.delete(s));
  s.on('error',()=>{client.destroy();upstream.destroy();});
 }
 client.pipe(upstream);upstream.pipe(client);
});
relay.listen(11434,'127.0.0.1');
await once(relay,'listening');
const password=randomBytes(32).toString('hex');
const env={...process.env,OPENCODE_PASSWORD:password};
const bin='/opt/opencode/node_modules/.bin/opencode';
const host='http://127.0.0.1:4096';
const server=spawn(bin,['serve','--hostname','127.0.0.1','--port','4096'],{cwd:'/workspace',env,stdio:['ignore','ignore','inherit']});
let ended=false;
server.on('error',()=>{ended=true;});
server.on('exit',()=>{ended=true;});
async function read(path){
 const url=new URL(path,host);
 if(path!='/api/info')url.searchParams.set('location[directory]','/workspace');
 const res=await fetch(url,{headers:{Authorization:'Basic '+Buffer.from('opencode:'+password).toString('base64')},redirect:'error',signal:AbortSignal.timeout(2500)});
 if(!res.ok)throw Error('native API unavailable');
 const reader=res.body.getReader();const chunks=[];let size=0;
 try{for(;;){const part=await reader.read();if(part.done)break;size+=part.value.length;if(size>8*1024*1024)throw Error('native API limit');chunks.push(Buffer.from(part.value));}}
 finally{await reader.cancel().catch(()=>{});}
 const result=JSON.parse(Buffer.concat(chunks).toString('utf8'));
 if(path!='/api/info'&&(result?.location?.directory!='/workspace'||!Array.isArray(result.data)))throw Error('native inventory unavailable');
 return result;
}
async function waitReady(){
 const deadline=Date.now()+60000;
 while(Date.now()<deadline&&!ended){
  try{
   const info=await read('/api/info');
   const plugins=(await read('/api/plugin')).data;
   const skills=(await read('/api/skill')).data;
   const models=(await read('/api/model')).data;
   if(info.version===expected.version&&expected.sources.every(x=>plugins.some(p=>p.id===x.profile&&p.state?.status==='active')&&x.expected_skills.every(id=>skills.some(s=>s.id===id)))&&models.some(m=>m.providerID==='ollama'&&m.id===process.env.NATIVE_MODEL))return;
  }catch{}
  await delay(500);
 }
 throw Error('native readiness failed: version, plugin, skill or model inventory');
}
try{
 const chunks=[];let size=0;
 for await(const chunk of process.stdin){size+=chunk.length;if(size>65536)throw Error('prompt limit');chunks.push(chunk);}
 await waitReady();
 const child=spawn(bin,['--server',host,'run','--format','json','--model','ollama/'+process.env.NATIVE_MODEL],
  {cwd:'/workspace',env,stdio:['pipe','inherit','inherit']});
 child.stdin.on('error',()=>{});
 child.stdin.end(Buffer.concat(chunks));
 const [code]=await once(child,'exit');
 process.exitCode=code===0?0:1;
}finally{
 server.kill('SIGTERM');
 for(let i=0;i<20&&!ended;i++)await delay(100);
 if(!ended)server.kill('SIGKILL');
 for(const s of sockets)s.destroy();
 relay.close();
}
