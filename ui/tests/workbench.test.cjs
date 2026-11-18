const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');const {JSDOM}=require('jsdom');
test('custom workbench navigates, splits and opens every implemented module',async()=>{
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://workstation.test/',pretendToBeVisual:true});
 const old={};for(const k of ['window','document','navigator','HTMLElement','Element','Node','CustomEvent','localStorage']){old[k]=Object.getOwnPropertyDescriptor(global,k);Object.defineProperty(global,k,{value:dom.window[k],configurable:true,writable:true});}
 global.IS_REACT_ACT_ENVIRONMENT=true;dom.window.HTMLElement.prototype.scrollIntoView=function(){};
 const fetched=[];const overview={projects:1,agents:1,documents:0,runs:[],worker:{online:true},inference:{endpoint:'http://127.0.0.1:11434',model:'test:latest'},release:'test'};
 const responses={'chat/conversations?archived=false&q=':[],session:{username:'test-admin',csrf:'csrf-test'},overview,projects:[{id:'project',name:'Project one',description:'',created_at:new Date().toISOString()}],agents:[{id:'agent',name:'Analyst',instructions:'Test',version:1,enabled:true}],models:{available:true,models:[{name:'test:latest',size:1000000}],config:overview.inference},runs:[],events:[],documents:[],artifacts:[],files:[],'library/artifacts':[],'access/users':[],capabilities:{features:[]},'operations/metrics':{tasks:[],chat:[],files:[]},tools:[],integrations:{connected:[],policy:'Optional'}};
 const writes=[];const fetchOld=global.fetch;global.fetch=async(path,options={})=>{fetched.push(path);const key=path.replace('/api/v1/','');let result=responses[key]??{};
  if(options.method==='POST'&&key==='chat/conversations'){const b=JSON.parse(options.body);responses['chat/conversations/chat-1']={...b,id:'chat-1',pinned:false,archived:false,updated_at:new Date().toISOString(),messages:[],generation:null};result={id:'chat-1'};}
  if(options.method==='POST'&&key==='chat/conversations/chat-1/messages'){const b=JSON.parse(options.body);writes.push(b);const c=responses['chat/conversations/chat-1'];c.messages=[{id:'q1',role:'user',content:b.content,attachments:[],model:null,status:'COMPLETE',created_at:new Date().toISOString()},{id:'a1',role:'assistant',content:'A **clear** explanation.',attachments:[],model:b.model,status:'COMPLETE',created_at:new Date().toISOString()}];responses['chat/conversations?archived=false&q=']=[c];result={id:'generation-1',conversation_id:'chat-1',assistant_message_id:'a1'};}
  return {ok:true,json:async()=>result};};
 const cache={};function load(name){const file='src/'+name+'.tsx';const fileTs='src/'+name+'.ts';const path=fs.existsSync(file)?file:fileTs;if(cache[path])return cache[path].exports;const m={exports:{}};cache[path]=m;const js=ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInThisContext('(function(require,module,exports){'+js+'\n})', {filename:path})(id=>id.startsWith('./')?load(id.slice(2)):require(id),m,m.exports);return m.exports;}
 const React=require('react');const {act}=React;const {createRoot}=require('react-dom/client');
 const locationOld=Object.getOwnPropertyDescriptor(global,'location');Object.defineProperty(global,'location',{value:dom.window.location,configurable:true});
 const App=load('App').default;const root=createRoot(document.getElementById('root'));
 try{
  await act(async()=>{root.render(React.createElement(App));await new Promise(r=>setTimeout(r,25));});
  assert.match(document.body.textContent,/CORE-AI/);assert.match(document.body.textContent,/test-admin/);assert.match(document.body.textContent,/Worker online/);
  assert.match(document.body.textContent,/How can I help/);
  const toggle=document.querySelector('[aria-label="Hide sidebar"]');
  await act(async()=>{toggle.click();});
  assert.equal(document.querySelector('.explorer'),null);
  await act(async()=>{document.querySelector('[aria-label="Show sidebar"]').click();});
  assert.ok(document.querySelector('.explorer'));
  const starter=[...document.querySelectorAll('.starter-grid button')].find(b=>b.textContent.includes('Understand'));
  await act(async()=>{starter.click();});
  assert.match(document.querySelector('[aria-label="Message CORE-AI"]').value,/Explain a concept/);
  await act(async()=>{document.querySelector('.chat-composer').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,40));});
  assert.equal(writes.length,1);assert.equal(writes[0].model,'test:latest');
  assert.match(document.querySelector('.conversation').textContent,/A clear explanation/);
  assert.equal(document.querySelector('[aria-label="Message CORE-AI"]').value,'');
  await act(async()=>{document.querySelector('.new-chat').click();await new Promise(r=>setTimeout(r,20));});
  assert.match(document.querySelector('.chat-welcome').textContent,/How can I help/);
  await act(async()=>{Object.defineProperty(dom.window,'innerWidth',{value:390,writable:true,configurable:true});dom.window.dispatchEvent(new dom.window.Event('resize'));});
  assert.equal(document.querySelector('.explorer'),null);
  await act(async()=>{document.querySelector('[aria-label="Show sidebar"]').click();});
  assert.ok(document.querySelector('.sidebar-backdrop')&&document.querySelector('.explorer'));
  await act(async()=>{document.querySelector('.sidebar-backdrop').click();});
  assert.equal(document.querySelector('.explorer'),null);
  await act(async()=>{dom.window.innerWidth=1024;dom.window.dispatchEvent(new dom.window.Event('resize'));});
  await act(async()=>{[...document.querySelectorAll('.layout-menu button')].find(b=>b.textContent==='Workbench').click();await new Promise(r=>setTimeout(r,20));});
  await act(async()=>{[...document.querySelectorAll('.nav-group')].find(b=>b.textContent.includes('Build')).click();});
  const taskButton=[...document.querySelectorAll('.nav-item')].find(b=>b.textContent.includes('Tasks'));
  await act(async()=>{taskButton.click();await new Promise(r=>setTimeout(r,20));});
  assert.match(document.querySelector('.view:not([hidden])').textContent,/New task/);
  const split=[...document.querySelectorAll('.workspace-toolbar button')].find(b=>b.textContent==='Split');
  await act(async()=>{split.click();await new Promise(r=>setTimeout(r,20));});
  assert.equal(document.querySelectorAll('.group').length,2);
  const openAll=[...document.querySelectorAll('.layout-menu button')].find(b=>b.textContent==='Open all panels');
  await act(async()=>{openAll.click();await new Promise(r=>setTimeout(r,30));});
  assert.equal(document.querySelectorAll('[role="tab"]').length,16);
  assert.equal(document.querySelectorAll('[role="tabpanel"]').length,16);
  assert.ok(!document.body.textContent.includes('This panel could not render'));
  assert.ok(fetched.includes('/api/v1/projects')&&fetched.includes('/api/v1/integrations'));
 }finally{await act(async()=>root.unmount());global.fetch=fetchOld;delete global.IS_REACT_ACT_ENVIRONMENT;for(const k of Object.keys(old)){if(old[k])Object.defineProperty(global,k,old[k]);else delete global[k];}if(locationOld)Object.defineProperty(global,'location',locationOld);else delete global.location;dom.window.close();}
});
