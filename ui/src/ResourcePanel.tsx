import {useEffect,useState} from 'react';
import {api} from './api';
import {useSession} from './Session';
const gib=(v:unknown)=>typeof v==='number'?(v/1024**3).toFixed(2)+' GiB':'Unavailable';
export default function ResourcePanel({tick}:{tick:number}){
 const admin=useSession().role==='ADMIN';
 const [data,setData]=useState<any>(null),[error,setError]=useState('');
 useEffect(()=>{if(!admin)return;let live=true;api('resources').then(d=>{if(live&&d?.server)setData(d);}).catch(e=>{if(live)setError(e.message);});return()=>{live=false;};},[tick,admin]);
 if(!admin)return null;
 return <section className="box"><header>Resource observations</header>{error&&<p role="alert">{error}</p>}{data?<><div className="fields"><div>Server available RAM <b>{gib(data.server.memory?.available_bytes)}</b></div><div>Server disk free <b>{gib(data.server.disk?.free_bytes)}</b></div><div>CPU threads <b>{data.server.cpu_logical??'—'}</b></div><div>1-minute load <b>{data.server.load_1m??'—'}</b></div></div><p>Observed {data.server.observed_at}. Server resources do not describe the remote laptop.</p><header>Ollama loaded models · {data.provider.available?'Available':'Unavailable'}</header><div className="table-scroll"><table><thead><tr><th>Model</th><th>Reported size</th><th>Reported VRAM allocation</th></tr></thead><tbody>{data.provider.models.map((m:any)=><tr key={m.name}><td>{m.name}</td><td>{gib(m.size)}</td><td>{gib(m.size_vram)}</td></tr>)}</tbody></table></div><p>Provider free RAM and VRAM are not reported by this endpoint. Automatic hardware admission remains separate from the configured model-size cap.</p></>:<p>Resource observations unavailable or not loaded.</p>}</section>;
}
