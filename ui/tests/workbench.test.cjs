const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');const {JSDOM}=require('jsdom');
test('custom workbench navigates, splits and opens every implemented module',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'http://workstation.test/',pretendToBeVisual:true});
 const old={};for(const k of ['window','document','navigator','HTMLElement','Element','Node','localStorage']){old[k]=Object.getOwnPropertyDescriptor(global,k);Object.defineProperty(global,k,{value:dom.window[k],configurable:true,writable:true});}
 global.IS_REACT_ACT_ENVIRONMENT=true;dom.window.HTMLElement.prototype.scrollIntoView=function(){};
 const fetched=[];const overview={projects:1,agents:1,documents:0,runs:[],worker:{online:true},inference:{endpoint:'http://10.203.0.2:11434',model:'test:latest'},release:'test'};
 const responses={session:{username:'test-admin',csrf:'csrf-test'},overview,projects:[{id:'project',name:'Project one',description:'',created_at:new Date().toISOString()}],agents:[{id:'agent',name:'Analyst',instructions:'Test',version:1,enabled:true}],models:{available:true,models:[{name:'test:latest',size:1000000}],config:overview.inference},runs:[],events:[],documents:[],artifacts:[],tools:[],integrations:{connected:[],policy:'Optional'}};
 const fetchOld=global.fetch;global.fetch=async(path)=>{fetched.push(path);const key=path.replace('/api/v1/','');return {ok:true,json:async()=>responses[key]??{}};};
 const cache={};function load(name){const file='src/'+name+'.tsx';const fileTs='src/'+name+'.ts';const path=fs.existsSync(file)?file:fileTs;if(cache[path])return cache[path].exports;const m={exports:{}};cache[path]=m;const js=ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInThisContext('(function(require,module,exports){'+js+'\n})', {filename:path})(id=>id.startsWith('./')?load(id.slice(2)):require(id),m,m.exports);return m.exports;}
 const React=require('react');const {act}=React;const {createRoot}=require('react-dom/client');
 const locationOld=Object.getOwnPropertyDescriptor(global,'location');Object.defineProperty(global,'location',{value:dom.window.location,configurable:true});
 const App=load('App').default;const root=createRoot(document.getElementById('root'));
 try{
  await act(async()=>{root.render(React.createElement(App));await new Promise(r=>setTimeout(r,25));});
  assert.match(document.body.textContent,/CORE-AI/);assert.match(document.body.textContent,/test-admin/);assert.match(document.body.textContent,/Worker online/);
  const taskButton=[...document.querySelectorAll('.tree button')].find(b=>b.textContent.includes('Tasks'));
  await act(async()=>{taskButton.click();await new Promise(r=>setTimeout(r,20));});
  assert.match(document.querySelector('.view:not([hidden])').textContent,/New task/);
  const split=[...document.querySelectorAll('.workspace-toolbar button')].find(b=>b.textContent==='Split');
  await act(async()=>{split.click();await new Promise(r=>setTimeout(r,20));});
  assert.equal(document.querySelectorAll('.group').length,2);
  const openAll=[...document.querySelectorAll('.explorer-tools button')].find(b=>b.textContent==='Open all');
  await act(async()=>{openAll.click();await new Promise(r=>setTimeout(r,30));});
  assert.equal(document.querySelectorAll('[role="tab"]').length,11);
  assert.equal(document.querySelectorAll('[role="tabpanel"]').length,11);
  assert.ok(!document.body.textContent.includes('This panel could not render'));
  assert.ok(fetched.includes('/api/v1/projects')&&fetched.includes('/api/v1/integrations'));
 }finally{await act(async()=>root.unmount());global.fetch=fetchOld;delete global.IS_REACT_ACT_ENVIRONMENT;for(const k of Object.keys(old)){if(old[k])Object.defineProperty(global,k,old[k]);else delete global[k];}if(locationOld)Object.defineProperty(global,'location',locationOld);else delete global.location;dom.window.close();}
});
