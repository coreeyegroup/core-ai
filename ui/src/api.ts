export function newId(){
 if(typeof crypto.randomUUID==='function')return crypto.randomUUID();
 const bytes=crypto.getRandomValues(new Uint8Array(16));
 bytes[6]=(bytes[6]&15)|64;
 bytes[8]=(bytes[8]&63)|128;
 const hex=Array.from(bytes,byte=>byte.toString(16).padStart(2,'0')).join('');
 return [hex.slice(0,8),hex.slice(8,12),hex.slice(12,16),hex.slice(16,20),hex.slice(20)].join('-');
}

let csrf='';
export function setCsrf(value:string){csrf=value;}
export async function api(path:string,method='GET',body?:unknown){
  const res=await fetch('/api/v1/'+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','x-core-ai-csrf':csrf},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  const value=await res.json().catch(()=>({detail:'Invalid server response.'}));
  if(!res.ok){const error=new Error(typeof value.detail==='string'?value.detail:'Request rejected. Check the fields.');Object.assign(error,{status:res.status});throw error;}
  return value;
}

export function uploadFile(file:File,projectId:string|null,onProgress:(n:number)=>void):Promise<any>{
 return new Promise((resolve,reject)=>{
  const xhr=new XMLHttpRequest();xhr.open('POST','/api/v1/files');xhr.setRequestHeader('x-core-ai-csrf',csrf);xhr.timeout=120000;
  xhr.upload.onprogress=e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded/e.total*100));};
  xhr.onerror=()=>reject(new Error('Upload failed. Check your connection.'));
  xhr.ontimeout=()=>reject(new Error('Upload timed out. Check the Files library before retrying.'));
  xhr.onload=()=>{let result:any;try{result=JSON.parse(xhr.responseText);}catch{reject(new Error('Invalid upload response.'));return;}if(xhr.status>=200&&xhr.status<300)resolve(result);else reject(new Error(typeof result.detail==='string'?result.detail:'Upload was rejected.'));};
  const form=new FormData();form.append('file',file);if(projectId)form.append('project_id',projectId);xhr.send(form);
 });
}
