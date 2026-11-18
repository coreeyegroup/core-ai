const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');const {JSDOM}=require('jsdom');
test('custom workbench navigates, splits and opens every implemented module',async()=>{
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://workstation.test/',pretendToBeVisual:true});
 const old={};for(const k of ['window','document','navigator','HTMLElement','Element','Node','Event','CustomEvent','localStorage']){old[k]=Object.getOwnPropertyDescriptor(global,k);Object.defineProperty(global,k,{value:dom.window[k],configurable:true,writable:true});}
 global.IS_REACT_ACT_ENVIRONMENT=true;dom.window.HTMLElement.prototype.scrollIntoView=function(){};
 const fetched=[];const overview={projects:1,agents:1,documents:0,runs:[],worker:{online:true},inference:{endpoint:'http://127.0.0.1:11434',model:'test:latest'},release:'test'};
 const responses={'chat/conversations?archived=false&q=':[],session:{username:'test-admin',csrf:'csrf-test'},overview,projects:[{id:'project',name:'Project one',description:'',created_at:new Date().toISOString()}],agents:[{id:'agent',name:'Analyst',instructions:'Test',version:1,enabled:true}],models:{available:true,models:[{name:'test:latest',size:1000000}],config:overview.inference},runs:[],events:[],documents:[],artifacts:[],files:[],'library/artifacts':[],'access/users':[],capabilities:{features:[]},'operations/metrics':{tasks:[],chat:[],files:[]},tools:[],integrations:{connected:[],policy:'Optional'}};
 const writes=[];const fetchOld=global.fetch;global.fetch=async(path,options={})=>{fetched.push(path);const key=path.replace('/api/v1/','');let result=responses[key]??{};
  if(options.method==='POST'&&key==='chat/conversations'){const b=JSON.parse(options.body);responses['chat/conversations/chat-1']={...b,id:'chat-1',pinned:false,archived:false,updated_at:new Date().toISOString(),messages:[],generation:null};result={id:'chat-1'};}
  if(options.method==='POST'&&key==='chat/conversations/chat-1/messages'){const b=JSON.parse(options.body);writes.push(b);const c=responses['chat/conversations/chat-1'];c.messages=[{id:'q1',role:'user',content:b.content,attachments:[],model:null,status:'COMPLETE',created_at:new Date().toISOString()},{id:'a1',role:'assistant',content:'A **clear** explanation.',attachments:[],model:b.model,status:'COMPLETE',created_at:new Date().toISOString()}];responses['chat/conversations?archived=false&q=']=[c];result={id:'generation-1',conversation_id:'chat-1',assistant_message_id:'a1'};}
  if(options.method==='POST'&&key==='library/artifacts'){responses['library/artifacts/artifact-1']={id:'artifact-1',title:'Response',content:'Current revision',kind:'markdown',language:'',project_id:null,visibility:'PRIVATE',version:2,selected_version:2,can_edit:true,can_share:true,versions:[{version:2,created_at:new Date().toISOString(),reason:'Edited'},{version:1,created_at:new Date().toISOString(),reason:'Created'}]};result={id:'artifact-1'};}
  if(key==='library/artifacts/artifact-1?version=1')result={...responses['library/artifacts/artifact-1'],content:'Original revision',selected_version:1};
  if(options.method==='PUT'&&key==='library/artifacts/artifact-1'){const b=JSON.parse(options.body);assert.equal(b.expected_version,2);assert.equal(b.content,'Original revision');responses[key]={...responses[key],...b,version:3,selected_version:3};result={id:'artifact-1',version:3};}
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
  await act(async()=>{[...document.querySelectorAll('.message-actions button')].find(b=>b.textContent==='Open as artifact').click();await new Promise(r=>setTimeout(r,25));});
  assert.ok(document.querySelector('.artifact-editor'));
  await act(async()=>{[...document.querySelectorAll('.editor-toolbar button')].find(b=>b.textContent==='Versions').click();});
  const oldRevision=[...document.querySelectorAll('.revision-list>div')].find(e=>e.textContent.includes('Version 1'));
  await act(async()=>{[...oldRevision.querySelectorAll('button')].find(b=>b.textContent==='View').click();await new Promise(r=>setTimeout(r,25));});
  const restore=[...document.querySelectorAll('.editor-toolbar button')].find(b=>b.textContent==='Restore as new version');
  assert.ok(restore&&!restore.disabled,'An unchanged historical revision can be restored as a new version');
  await act(async()=>{restore.click();await new Promise(r=>setTimeout(r,25));});
  assert.match(document.querySelector('.editor-heading').textContent,/v3/);
  await act(async()=>{document.querySelector('[aria-label="Close artifact editor"]').click();});
  await act(async()=>{document.querySelector('.new-chat').click();await new Promise(r=>setTimeout(r,20));});
  assert.match(document.querySelector('.chat-welcome').textContent,/How can I help/);
  assert.equal(document.querySelector('[aria-label="Response style"]').value,'general');
  await act(async()=>{document.querySelector('[aria-label="Open settings"]').click();});
  const selectSetting=(label,value)=>{const input=[...document.querySelectorAll('.settings-page label')].find(l=>l.textContent.startsWith(label)).querySelector('select');input.value=value;input.dispatchEvent(new dom.window.Event('change',{bubbles:true}));};
  await act(async()=>{selectSetting('Default response style','professional');});
  await act(async()=>{selectSetting('Default maximum reply tokens','1024');});
  assert.equal(JSON.parse(localStorage.getItem('core-ai.appearance.v1')).chatDefaults.mode,'professional');
  await act(async()=>{document.querySelector('.new-chat').click();});
  assert.equal(document.querySelector('[aria-label="Response style"]').value,'professional');
  const professional=[...document.querySelectorAll('.starter-grid button')].find(b=>b.textContent.includes('Decision brief'));
  await act(async()=>{professional.click();});
  assert.match(document.querySelector('[aria-label="Message CORE-AI"]').value,/trade-offs/);
  await act(async()=>{document.querySelector('[aria-label="Conversation context"]').click();});
  assert.equal(document.querySelector('[aria-label="Conversation context"]').getAttribute('aria-expanded'),'true');
  assert.equal([...document.querySelectorAll('.chat-options select')].at(-1).value,'1024');
  await act(async()=>{document.querySelector('.history-title').click();});
  assert.equal(document.querySelector('[aria-label="Response style"]').value,'general');
  await act(async()=>{window.dispatchEvent(new CustomEvent('core-ai-project-chat',{detail:{projectId:'project'}}));});
  assert.equal(document.querySelector('[aria-label="Response style"]').value,'professional');
  assert.equal(document.querySelector('.composer-context').textContent,'Project one');
  assert.equal(document.querySelector('[aria-label="Message CORE-AI"]').value,'');
  await act(async()=>{document.querySelector('.new-chat').click();});
  assert.equal(document.querySelector('.composer-context').textContent,'Private conversation');
  assert.match(document.querySelector('[aria-label="Message CORE-AI"]').value,/trade-offs/);

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
