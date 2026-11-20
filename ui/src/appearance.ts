export const themes = ['Standard', 'Black', 'Dark Blue', 'White', 'COREI Orbit'] as const;
export type Theme = typeof themes[number];
export const replyTokenOptions = [256, 512, 1024, 2048, 4096] as const;
export const chatModes = [
  {value:'general',label:'General',description:'Balanced answers for everyday work'},
  {value:'quick',label:'Quick',description:'A direct answer with essential context'},
  {value:'professional',label:'Professional',description:'Structured, decision-ready responses'},
  {value:'deep',label:'Deep analysis',description:'Assumptions, alternatives, and trade-offs'},
  {value:'research',label:'Research',description:'Evidence, source attribution, and open questions'},
  {value:'coding',label:'Coding',description:'Implementation, tests, and edge cases'},
] as const;
export type ChatDefaults = {mode:typeof chatModes[number]['value'];temperature:number;max_tokens:number};
export const defaultChat: ChatDefaults = {mode:'general',temperature:.4,max_tokens:2048};
export type Appearance = { theme: Theme; fontSize: number; density: 'Compact' | 'Comfortable'; activity: boolean; status: boolean; wrapTabs: boolean; readingSize:number;sendKey:'Enter'|'CtrlEnter'; chatDefaults:ChatDefaults };
export const typographyVersion = 2;
export const appearanceKey = 'core-ai.appearance.v1';
export const defaultAppearance: Appearance = {theme:'Standard',fontSize:14,density:'Compact',activity:false,status:true,wrapTabs:false,readingSize:17,sendKey:'Enter',chatDefaults:defaultChat};
export function restoreAppearance(raw:string|null):Appearance {
  try {
    const x=JSON.parse(raw||'null');
    if(!x || !themes.includes(x.theme) || !Number.isInteger(x.fontSize) || x.fontSize<11 || x.fontSize>18 || !['Compact','Comfortable'].includes(x.density) || ['activity','status','wrapTabs'].some(k=>typeof x[k]!=='boolean')) return {...defaultAppearance};
    const chat=x.chatDefaults;
    const chatDefaults:ChatDefaults={
      mode:chatModes.find(mode=>mode.value===chat?.mode)?.value??defaultChat.mode,
      temperature:typeof chat?.temperature==='number'&&chat.temperature>=0&&chat.temperature<=1.5?chat.temperature:defaultChat.temperature,
      max_tokens:replyTokenOptions.includes(chat?.max_tokens)?chat.max_tokens:defaultChat.max_tokens,
    };
    const legacy=x.typographyVersion!==typographyVersion;
    const fontSize=legacy&&x.fontSize===12?defaultAppearance.fontSize:x.fontSize;
    const savedReading=Number.isInteger(x.readingSize)&&x.readingSize>=12&&x.readingSize<=22?x.readingSize:defaultAppearance.readingSize;
    const readingSize=legacy&&savedReading===14?defaultAppearance.readingSize:savedReading;
    return {theme:x.theme,fontSize,density:x.density,activity:x.activity,status:x.status,wrapTabs:x.wrapTabs,readingSize,sendKey:x.sendKey==='CtrlEnter'?'CtrlEnter':'Enter',chatDefaults};
  } catch {return {...defaultAppearance};}
}

