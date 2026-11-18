import {createContext,useContext,type ReactNode} from 'react';
export type Session={id?:string;username:string;csrf:string;role:'ADMIN'|'EDITOR'|'VIEWER'};
const Context=createContext<Session>({username:'',csrf:'',role:'ADMIN'});
export const useSession=()=>useContext(Context);
export function SessionProvider({session,children}:{session:Session;children:ReactNode}){return <Context.Provider value={session}>{children}</Context.Provider>;}
