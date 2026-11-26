// Runs the upstream CLI inside a disposable network-none container.
// The only reachable network service is a request-filtered Unix socket relay.
import {createServer,connect} from 'node:net';
import {spawn} from 'node:child_process';
import {mkdirSync,writeFileSync} from 'node:fs';
import {once} from 'node:events';

const config=JSON.parse(process.env.NATIVE_CONFIG);
mkdirSync(process.env.XDG_CONFIG_HOME+'/opencode',{recursive:true});
writeFileSync(process.env.XDG_CONFIG_HOME+'/opencode/opencode.json',JSON.stringify(config));
delete process.env.OPENCODE_CONFIG;
const sockets=new Set();
const server=createServer(client=>{
 const upstream=connect('/relay.sock');
 for(const s of [client,upstream]){
  sockets.add(s);
  s.on('close',()=>sockets.delete(s));
  s.on('error',()=>{client.destroy();upstream.destroy();});
 }
 client.pipe(upstream);upstream.pipe(client);
});
server.listen(11434,'127.0.0.1');
await once(server,'listening');
try{
 const chunks=[];let size=0;
 for await(const chunk of process.stdin){size+=chunk.length;if(size>65536)throw Error('prompt limit');chunks.push(chunk);}
 const child=spawn('/opt/opencode/node_modules/.bin/opencode',
  ['--standalone','run','--format','json','--model','ollama/'+process.env.NATIVE_MODEL],
  {cwd:'/workspace',env:process.env,stdio:['pipe','inherit','inherit']});
 child.stdin.on('error',()=>{});
 child.stdin.end(Buffer.concat(chunks));
 const [code]=await once(child,'exit');
 process.exitCode=code===0?0:1;
}finally{
 for(const s of sockets)s.destroy();
 server.close();
}
