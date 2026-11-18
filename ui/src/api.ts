let csrf='';
export function setCsrf(value:string){csrf=value;}
export async function api(path:string,method='GET',body?:unknown){
  const res=await fetch('/api/v1/'+path,{method,credentials:'same-origin',cache:'no-store',headers:{'Content-Type':'application/json','x-core-ai-csrf':csrf},body:body===undefined?undefined:JSON.stringify(body),signal:AbortSignal.timeout(15000)});
  const value=await res.json().catch(()=>({detail:'Invalid server response.'}));
  if(!res.ok){const error=new Error(typeof value.detail==='string'?value.detail:'Request rejected. Check the fields.');Object.assign(error,{status:res.status});throw error;}
  return value;
}
