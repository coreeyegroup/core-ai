const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const vm=require('node:vm');const ts=require('typescript');const {JSDOM}=require('jsdom');
test('custom workbench navigates, splits and opens every implemented module',async()=>{
 const dom=new JSDOM('<!doctype html><div id="root"></div>',{url:'http://workstation.test/',pretendToBeVisual:true});
 const old={};for(const k of ['window','document','navigator','HTMLElement','HTMLInputElement','Element','Node','Event','CustomEvent','FormData','localStorage']){old[k]=Object.getOwnPropertyDescriptor(global,k);Object.defineProperty(global,k,{value:dom.window[k],configurable:true,writable:true});}
 global.IS_REACT_ACT_ENVIRONMENT=true;dom.window.HTMLElement.prototype.scrollIntoView=function(){};
 const fetched=[];const overview={projects:1,agents:1,documents:0,runs:[],worker:{online:true},inference:{endpoint:'http://127.0.0.1:11434',model:'test:latest'},release:'test'};
 const responses={'chat/conversations?archived=false&q=':[],session:{username:'test-admin',role:'ADMIN',csrf:'csrf-test'},overview,projects:[{id:'project',name:'Project one',description:'',created_at:new Date().toISOString()}],agents:[{id:'agent',name:'Analyst',instructions:'Test',version:1,enabled:true}],models:{available:true,models:[{name:'test:latest',size:1000000},{name:'editor:latest',size:1000000}],config:overview.inference},runs:[],events:[],documents:[],artifacts:[],files:[],'library/artifacts':[],'access/users':[],capabilities:{features:[]},'operations/metrics':{tasks:[],chat:[],files:[]},tools:[],connections:[],'connections/webhook-destinations':[],'connections/key-storage':{available:true}};
  const catalogCommit='a'.repeat(40);
  const catalogRow={id:'collection',repository:'example/skills',git_ref:'HEAD',active_commit:null,latest_commit:catalogCommit,skill_count:1};
  responses.missions={templates:[],runs:[]};
  responses['programs/jobs']=[];
  responses.programs={schema:1,programs:[{id:'position-sizing',repository:'example/trading',commit:catalogCommit,runtime:'python:3.12-slim',fields:['account','risk_pct','entry','stop','fee_rate','slippage'],example:[10000,.01,100,95,0,0],extensions:[],output_file:false,mode:'offline',state:'qualified-receipt'}],repositories:[{repository:'example/trading',commit:catalogCommit,source_present:true,recipes:['position-sizing'],coverage:'partial-reviewed-recipes'}]};
  responses.skills=[catalogRow];
  responses['skills/collections/collection?commit='+catalogCommit]={
   ...catalogRow,commit:catalogCommit,releases:[{commit_sha:catalogCommit,skill_count:1}],
   skills:[{name:'systematic-debugging',description:'Review evidence',path:'systematic-debugging/SKILL.md',references:[]}],
   excluded:[],changes:{added:['systematic-debugging/SKILL.md'],removed:[],changed:[]}
  };
  responses['skills/agents/agent']=[];
  responses['projects/first-research-project/connections']=[];
  const chatSkill={name:'systematic-debugging',description:'Review evidence',repository:'example/skills',collection_id:'collection',commit:catalogCommit,path:'systematic-debugging/SKILL.md'};
  responses['skills/chat/preview']={available:[chatSkill,
   {...chatSkill,collection_id:'duplicate-ref',git_ref:'HEAD'},
   {...chatSkill,collection_id:'alternate-source',repository:'other/skills',path:'alternate/SKILL.md'}],
   automatic:[chatSkill],error:''};
  responses['skills/agents/new-agent']=[];
  const forexCommit='b'.repeat(40);
  const forexCollection={...catalogRow,id:'forex',repository:'marian2js/trading-skills',git_ref:'main',latest_commit:forexCommit};
  responses['skills/collections/forex?commit='+forexCommit]={
   ...forexCollection,commit:forexCommit,releases:[{commit_sha:forexCommit,skill_count:1}],
   skills:[{name:'macro-event-analysis',description:'Explain macro events',path:'macro-event-analysis/SKILL.md',references:[]}],
   excluded:[],changes:{added:['macro-event-analysis/SKILL.md'],removed:[],changed:[]}
  };
 let conversationCount=0,agentCount=0;const writes=[],connectionWrites=[],researchWrites=[],assignmentWrites=[];const fetchOld=global.fetch;global.fetch=async(path,options={})=>{fetched.push(path);const key=path.replace('/api/v1/','');let result=responses[key==='models?catalog=true'?'models':key]??{};
  if(options.method==='POST'&&key==='programs/jobs'){
   const payload=JSON.parse(options.body);assert.ok(payload.request_id);delete payload.request_id;
   assert.deepEqual(payload,{recipe:'position-sizing',values:[10000,.01,100,95,0,0],extension:null,file_data:null});
   const job={id:'job-test',recipe:'position-sizing',status:'SUCCEEDED',created_at:new Date().toISOString(),result:{id:'execution-test',recipe:'position-sizing',state:'succeeded',commit:catalogCommit,image:'sha256:'+'a'.repeat(64),provenance:'offline-program',result:{units:20}}};
   responses['programs/jobs']=[job];responses['programs/jobs/job-test']=job;result={id:job.id};
  }
  if(options.method==='POST'&&key==='agents'){
   result={id:['new-agent','studio-agent','guided-agent'][agentCount++]};
   responses['skills/agents/'+result.id]=[];
   responses.agents=[...responses.agents,{...JSON.parse(options.body),id:result.id,enabled:true,version:1}];
  }
  if(options.method==='POST'&&key==='projects'){
   const body=JSON.parse(options.body);
   assert.equal(body.name,'First Research Project');
   const project={...body,id:'first-research-project',description:'',created_at:new Date().toISOString()};
   responses.projects=[...responses.projects,project];
   result={id:project.id};
  }
  if(options.method==='DELETE'&&key==='projects/first-research-project'){
   assert.deepEqual(JSON.parse(options.body),{name:'First Research Project'});
   const deleted=responses.projects.find(project=>project.id==='first-research-project');
   responses.projects=responses.projects.filter(project=>project.id!==deleted.id);
   responses['projects?deleted=true']=[{...deleted,deleted_at:new Date().toISOString()}];
  }
  if(options.method==='POST'&&key==='projects/first-research-project/restore'){
   responses.projects=responses['projects?deleted=true'].map(project=>({...project,deleted_at:null}));
   responses['projects?deleted=true']=[];
  }
  if(options.method==='POST'&&key.startsWith('skills/collections/collection/intelligence/analyse?')){
   assert.deepEqual(JSON.parse(options.body).paths,['README.md']);
   const inventory=responses['skills/collections/collection/intelligence?'+new URLSearchParams({commit:catalogCommit,q:'',kind:'',offset:'0',limit:'40'})];
   inventory.reports=[{id:'assessment-1',model:'test:latest',focus:'',created_at:new Date().toISOString()}];
   result={id:'assessment-1'};
  }
  if(options.method==='POST'&&key.endsWith('/reports/assessment-1/verify/0')){
   const report=responses['skills/collections/collection/intelligence/reports/assessment-1'];
   report.verification=[{capability_index:0,...JSON.parse(options.body),checked_at:new Date().toISOString()}];
  }
  if(options.method==='POST'&&key.startsWith('skills/collections/collection/agent?')){
   responses.agents.push({id:'repository-agent',name:'Repository Reviewer',instructions:'Review with evidence',
    enabled:false,version:1,runtime_mode:'analysis',tools:[]});
   responses['skills/agents/repository-agent']=[];
   result={id:'repository-agent',created:true};
  }
  if(options.method==='POST'&&key==='skills/import'){
   const body=JSON.parse(options.body);
   if(body.repository===forexCollection.repository){
    assert.equal(body.ref,'main');
    responses.skills=[...responses.skills,forexCollection];
    result={id:'forex',commit:forexCommit,count:1,invalid:[]};
   }else{
    assert.deepEqual(body,{repository:'example/skills',ref:'HEAD'});
    result={id:'collection',commit:catalogCommit,count:1,invalid:['draft/SKILL.md']};
   }
  }
  if(options.method==='PUT'&&key==='skills/collections/collection/activate'){
   assert.deepEqual(JSON.parse(options.body),{commit:catalogCommit,expected_commit:null});
   catalogRow.active_commit=catalogCommit;
   responses['skills/collections/collection?commit='+catalogCommit].active_commit=catalogCommit;
  }
  if(options.method==='PUT'&&key==='skills/collections/forex/activate'){
   forexCollection.active_commit=forexCommit;
   responses['skills/collections/forex?commit='+forexCommit].active_commit=forexCommit;
  }
  if(options.method==='PUT'&&key.startsWith('skills/agents/')){
   const body=JSON.parse(options.body);
   assignmentWrites.push(body.collections);
   responses[key]=body.collections;
  }
  if(options.method==='POST'&&key==='runs'&&!JSON.parse(options.body).research){
   const body=JSON.parse(options.body),id='guided-task';
   responses['runs/'+id]={...body,id,status:'QUEUED',agent_version:1,events:[]};
   responses.runs=[responses['runs/'+id],...responses.runs];
   result={id};
  }
  if(options.method==='POST'&&key==='runs'&&JSON.parse(options.body).research){
   const body=JSON.parse(options.body),id='research-1';
   researchWrites.push(body);
   const draft='# Evidence report';
   responses['runs/'+id]={...body,id,status:'WAITING_REVIEW',research_phase:'COMPLETE',agent_version:1,events:[],research:{specification:body.research,phase:'COMPLETE',draft,review_digest:'a'.repeat(64),plan:{queries:body.research.queries}}};
   responses.runs=[responses['runs/'+id]];
   result={id};
  }
  if(options.method==='POST'&&key==='runs/research-1/review'){
   assert.deepEqual(JSON.parse(options.body),{digest:'a'.repeat(64),decision:'approve'});
   const run=responses['runs/research-1'];
   run.status='SUCCEEDED';run.output=run.research.draft;run.research.artifact_id='artifact-1';
   result={status:run.status};
  }
  if(options.method==='POST'&&key==='connections'){
   connectionWrites.push(JSON.parse(options.body));
   result={id:'fixture-connection',token:'fixture-only'};
   responses.connections=[{...connectionWrites.at(-1),id:result.id,allowed_models:[],scope_available:true}];
  }
  if(options.method==='POST'&&key==='connections/fixture-connection/revoke'){
   responses.connections=responses.connections.map(row=>({...row,revoked_at:new Date().toISOString()}));
  }
  if(options.method==='POST'&&key==='chat/conversations'){
   const b=JSON.parse(options.body),id='chat-'+(++conversationCount);
   responses['chat/conversations/'+id]={...b,id,pinned:false,archived:false,updated_at:new Date().toISOString(),messages:[],generation:null};
   result={id};
  }
  if(options.method==='POST'&&/^chat\/conversations\/chat-\d+\/messages$/.test(key)){
   const b=JSON.parse(options.body),c=responses[key.replace('/messages','')];
   writes.push({...b,conversation:c.id});
   c.model=b.model;c.mode=b.mode;
   c.messages=[{id:'q1',role:'user',content:b.content,attachments:[],model:null,status:'COMPLETE',created_at:new Date().toISOString()},{id:'a1',role:'assistant',content:'A **clear** explanation.',attachments:[],model:b.model,status:'COMPLETE',created_at:new Date().toISOString()}];
   const historyKey='chat/conversations?archived=false&q=';
   responses[historyKey]=[c,...responses[historyKey].filter(item=>item.id!==c.id)];
   result={id:'generation-1',conversation_id:c.id,assistant_message_id:'a1'};
  }
  if(options.method==='POST'&&key==='library/artifacts'){responses['library/artifacts/artifact-1']={id:'artifact-1',title:'Response',content:'Current revision',kind:'markdown',language:'',project_id:null,visibility:'PRIVATE',version:2,selected_version:2,can_edit:true,can_share:true,versions:[{version:2,created_at:new Date().toISOString(),reason:'Edited'},{version:1,created_at:new Date().toISOString(),reason:'Created'}]};result={id:'artifact-1'};}
  if(key==='library/artifacts/artifact-1?version=1')result={...responses['library/artifacts/artifact-1'],content:'Original revision',selected_version:1};
  if(options.method==='PUT'&&key==='library/artifacts/artifact-1'){const b=JSON.parse(options.body);assert.equal(b.expected_version,2);assert.equal(b.content,'Original revision');responses[key]={...responses[key],...b,version:3,selected_version:3};result={id:'artifact-1',version:3};}
  return {ok:true,json:async()=>result};};
 const cache={};function load(name){const file='src/'+name+'.tsx';const fileTs='src/'+name+'.ts';const path=fs.existsSync(file)?file:fileTs;if(cache[path])return cache[path].exports;const m={exports:{}};cache[path]=m;const js=ts.transpileModule(fs.readFileSync(path,'utf8'),{compilerOptions:{jsx:ts.JsxEmit.ReactJSX,module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;vm.runInThisContext('(function(require,module,exports){'+js+'\n})', {filename:path})(id=>id.startsWith('./')?load(id.slice(2)):require(id),m,m.exports);return m.exports;}
 const React=require('react');const {act}=React;const {createRoot}=require('react-dom/client');
 const locationOld=Object.getOwnPropertyDescriptor(global,'location');Object.defineProperty(global,'location',{value:dom.window.location,configurable:true});
 const {appearanceKey,defaultAppearance}=load('appearance');
 localStorage.setItem(appearanceKey,JSON.stringify({...defaultAppearance,activity:true}));
 const App=load('App').default;const root=createRoot(document.getElementById('root'));
 try{
  await act(async()=>{root.render(React.createElement(App));await new Promise(r=>setTimeout(r,25));});
  assert.match(document.body.textContent,/CORE-AI/);assert.match(document.body.textContent,/test-admin/);assert.match(document.body.textContent,/Worker online/);
  assert.match(document.body.textContent,/How can I help/);
  const surface=document.querySelector('.composer-input-surface');
  const model=document.querySelector('.model-picker-trigger');
  assert.ok(surface.contains(document.querySelector('[aria-label="Message CORE-AI"]')));
  assert.ok(!surface.contains(document.querySelector('[aria-label="Response style"]')));
  assert.ok(!surface.contains(document.querySelector('.library-picker-button')));
  assert.equal(model.nextElementSibling.getAttribute('aria-label'),'Send message');
  const ribbon=document.querySelector('[aria-label="Activity ribbon"]');
  assert.equal(ribbon.querySelectorAll('button').length,18);
  assert.equal(ribbon.querySelector('[aria-current="page"]').getAttribute('aria-label'),'Chat');
  assert.ok(document.querySelector('.explorer-scroll .workspace-navigation'));
  assert.ok(document.querySelector('.explorer-scroll .history-scroll'));
  await act(async()=>{ribbon.querySelector('[aria-label="Models"]').click();});
  assert.equal(document.querySelector('.workspace-navigation [aria-current="page"]').textContent,'Models');
  const manage=[...document.querySelectorAll('.nav-group')].find(button=>button.textContent.includes('Manage'));
  await act(async()=>{manage.click();});
  assert.equal(manage.getAttribute('aria-expanded'),'false');
  await act(async()=>{ribbon.querySelector('[aria-label="Models"]').click();});
  assert.equal(manage.getAttribute('aria-expanded'),'true');
  assert.equal(document.querySelector('.workspace-navigation [aria-current="page"]').textContent,'Models');
  assert.equal(document.querySelector('.app').dataset.explorer,'true');
  const resize=document.querySelector('[aria-label="Explorer width"]');
  await act(async()=>{resize.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'End',bubbles:true}));});
  assert.equal(document.querySelector('.app').style.getPropertyValue('--explorer-width'),'380px');
  await act(async()=>{ribbon.querySelector('[aria-label="Chat"]').click();});

  const toggle=document.querySelector('[aria-label="Hide sidebar"]');
  await act(async()=>{toggle.click();});
  assert.equal(document.querySelector('.explorer'),null);
  assert.equal(document.querySelector('[aria-label="Activity ribbon"]'),ribbon);
  await act(async()=>{ribbon.querySelector('[aria-label="Models"]').click();});
  assert.ok(document.querySelector('.view:not([hidden])[aria-label="Models"]'));
  assert.equal(document.querySelector('.explorer'),null);
  await act(async()=>{ribbon.querySelector('[aria-label="Chat"]').click();});
  await act(async()=>{document.querySelector('[aria-label="Show sidebar"]').click();});
  assert.ok(document.querySelector('.explorer'));
  const starter=[...document.querySelectorAll('.starter-grid button')].find(b=>b.textContent.includes('Understand'));
  await act(async()=>{starter.click();});
  assert.match(document.querySelector('[aria-label="Message CORE-AI"]').value,/Explain a concept/);
  await act(async()=>{document.querySelector('.new-chat').click();await new Promise(r=>setTimeout(r,25));});
  assert.equal(document.querySelector('[aria-label="Message CORE-AI"]').value,'','New chat must start with an empty composer');
  assert.equal(document.activeElement.getAttribute('aria-label'),'Message CORE-AI');
  await act(async()=>{starter.click();});
  await act(async()=>{document.querySelector('.chat-composer').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await new Promise(r=>setTimeout(r,40));});
  assert.equal(writes.length,1);assert.equal(writes[0].model,'test:latest');
  assert.match(document.querySelector('.conversation').textContent,/A clear explanation/);
  const userMessage=document.querySelector('.message.user');
  const assistantMessage=document.querySelector('.message.assistant');
  await act(async()=>{userMessage.querySelector('.message-fold').click();});
  assert.equal(userMessage.querySelector('.message-content').hidden,true);
  assert.equal(assistantMessage.querySelector('.message-content').hidden,false);
  assert.match(userMessage.querySelector('.message-preview').textContent,/Explain a concept/);
  await act(async()=>{assistantMessage.querySelector('.message-fold').click();});
  assert.equal(assistantMessage.querySelector('.message-content').hidden,true);
  assert.equal(document.querySelector('.fold-all').textContent,'Expand all');
  await act(async()=>{document.querySelector('.fold-all').click();});
  assert.equal(userMessage.querySelector('.message-content').hidden,false);
  assert.equal(assistantMessage.querySelector('.message-content').hidden,false);
  assert.equal(document.querySelector('[aria-label="Message CORE-AI"]').value,'');
  const menuTrigger=document.querySelector('.history-item [aria-haspopup="menu"]');
  await act(async()=>{menuTrigger.click();});
  const menu=document.querySelector('[role="menu"]');
  assert.deepEqual([...menu.querySelectorAll('[role="menuitem"]')].map(item=>item.textContent),['Rename','Pin','Archive','Delete']);
  assert.equal(menu.closest('.history-item'),null);
  await act(async()=>{menu.querySelector('button').dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));});
  assert.equal(document.querySelector('[role="menu"]'),null);
  assert.equal(document.activeElement,menuTrigger);

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
  assert.equal(document.querySelector('.composer-context').textContent,'Private');
  assert.equal(document.querySelector('[aria-label="Message CORE-AI"]').value,'');

  await act(async()=>{Object.defineProperty(dom.window,'innerWidth',{value:390,writable:true,configurable:true});dom.window.dispatchEvent(new dom.window.Event('resize'));});
  assert.equal(document.querySelector('.explorer'),null);
  await act(async()=>{document.querySelector('[aria-label="Show sidebar"]').click();});
  const drawer=document.querySelector('.explorer[role="dialog"]');
  assert.ok(document.querySelector('.sidebar-backdrop')&&drawer);
  assert.equal(document.activeElement.getAttribute('aria-label'),'Hide explorer');
  assert.equal(document.querySelector('[aria-label="Explorer width"]'),null);
  drawer.querySelector('select').focus();
  document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}));
  assert.equal(document.activeElement.getAttribute('aria-label'),'Open settings');
  await act(async()=>{document.activeElement.dispatchEvent(new dom.window.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));});
  assert.equal(document.querySelector('.explorer'),null);
  assert.equal(document.activeElement.getAttribute('aria-label'),'Show sidebar');
  await act(async()=>{document.activeElement.click();});
  await act(async()=>{document.querySelector('.explorer [aria-label="Open settings"]').click();});
  assert.equal(document.querySelector('.explorer'),null);
  assert.equal(document.activeElement.className,'workspace-main');
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
  assert.equal(document.querySelectorAll('[role="tab"]').length,18);
  assert.equal(document.querySelectorAll('[role="tabpanel"]').length,18);
  assert.ok(!document.body.textContent.includes('This panel could not render'));
  assert.ok(fetched.includes('/api/v1/projects')&&fetched.includes('/api/v1/connections'));
  const panes=()=>[...document.querySelectorAll('.group .chat-workspace')];
  const change=(element,value)=>{element.value=value;element.dispatchEvent(new dom.window.Event('change',{bubbles:true}));};
  const submit=panel=>panel.querySelector('form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));
  const wait=()=>new Promise(r=>setTimeout(r,35));
  const tabs=()=>[...document.querySelectorAll('.chat-pane-list [data-chat-tab]')];
  const tab=async index=>act(async()=>{tabs()[index].click();await wait();});
  const chat=()=>panes().find(panel=>!panel.closest('[hidden]'));
  const setChat=async(model,mode)=>{
   await act(async()=>{chat().querySelector('[aria-label="Chat model"]').click();});
   const option=[...document.querySelectorAll('.model-popover button')].find(button=>button.textContent===model);
   assert.ok(option);
   await act(async()=>{option.click();change(chat().querySelector('[aria-label="Response style"]'),mode);});
  };
  const draft=async()=>act(async()=>{chat().querySelector('.starter-grid button').click();});
  const send=async()=>act(async()=>{submit(chat());await wait();});
  const initialTabs=tabs().length;
  const add=async()=>act(async()=>{document.querySelector('[aria-label="Add chat sub-workspace"]').click();await wait();});
  await add();
  assert.equal(tabs().length,initialTabs+1);
  assert.equal(document.querySelectorAll('.group').length,1);
  assert.equal(document.querySelectorAll('[role="tab"]').length,18);
  assert.ok(document.querySelector('#panel-0-Chat .chat-pane-strip'));
  await setChat('test:latest','research');
  await draft();
  await add();
  await setChat('editor:latest','coding');
  await draft();
  assert.match(chat().querySelector('textarea').value,/code/i);
  await tab(initialTabs);
  assert.match(chat().querySelector('textarea').value,/evidence/i);
  await send();
  await tab(initialTabs+1);
  assert.match(chat().querySelector('textarea').value,/code/i);
  await send();
  assert.deepEqual(writes.slice(-2).map(({conversation,model,mode})=>[conversation,model,mode]),[
   ['chat-2','test:latest','research'],['chat-3','editor:latest','coding']
  ]);
  await act(async()=>{change(document.querySelector('[aria-label="Switch workspace"]'),'Research');await wait();});
  assert.equal(tabs().length,1);
  assert.equal(chat().querySelector('.conversation'),null);
  await act(async()=>{change(document.querySelector('[aria-label="Switch workspace"]'),'Build');await wait();});
  assert.equal(tabs().length,initialTabs+2);
  assert.equal(chat().querySelector('[aria-label="Chat model"]').textContent,'editor:latest');
  await act(async()=>{dom.window.innerWidth=375;dom.window.dispatchEvent(new dom.window.Event('resize'));});
  await tab(initialTabs);
  assert.match(chat().querySelector('.user-text').textContent,/evidence/i);
  const newChat=document.querySelector('.header-actions [aria-label="New chat"]');
  await act(async()=>{newChat.click();await wait();});
  assert.equal(tabs().length,initialTabs+3);
  assert.equal(chat().querySelector('.conversation'),null);
  await act(async()=>{document.querySelector('.chat-pane-tab[data-current="true"] .chat-tab-close').click();await wait();});
  assert.equal(tabs().length,initialTabs+2);
  assert.equal(chat().querySelector('[aria-label="Chat model"]').textContent,'editor:latest');
  await act(async()=>{dom.window.innerWidth=1440;dom.window.dispatchEvent(new dom.window.Event('resize'));await wait();});
  const projectsNav=document.querySelector('.explorer-projects');
  const projectShortcut=[...projectsNav.querySelectorAll('button')].find(button=>button.textContent==='Project one');
  await act(async()=>{projectShortcut.click();await new Promise(r=>setTimeout(r,25));});
  assert.equal(projectShortcut.getAttribute('aria-current'),'page');
  assert.equal(document.querySelector('.view:not([hidden]) .project-title h1').textContent,'Project one');
  await act(async()=>{projectsNav.querySelector('[aria-label="New project"]').click();});
  assert.ok(document.querySelector('.view:not([hidden]) .project-create'));
  await act(async()=>{window.dispatchEvent(new CustomEvent('core-ai-goto',{detail:{view:'Integrations'}}));await wait();});
  const connections=()=>document.querySelector('.view:not([hidden]) .connections-page');
  await act(async()=>{[...connections().querySelectorAll('button')].find(button=>button.textContent==='New connection').click();await wait();});
  const editor=connections().querySelector('.connection-editor');
  const scope=[...editor.querySelectorAll('select')].find(select=>[...select.options].some(option=>option.value==='all'));
  await act(async()=>{change(scope,'all');});
  const blocked=editor.querySelector('[aria-label="test:latest"]');
  assert.ok(blocked.checked);
  await act(async()=>{blocked.click();editor.querySelector('[name=can_embed]').click();});
  assert.ok(!blocked.checked);
  editor.querySelector('[name=name]').value='Usage test';
  await act(async()=>{submit(connections());await wait();});
  assert.equal(connectionWrites.length,1);
  assert.equal(connectionWrites[0].model_access,'all');
  assert.equal(connectionWrites[0].can_embed,true);
  assert.deepEqual(connectionWrites[0].model_policies,{'test:latest':{enabled:false}});
  const deleteKey=connections().querySelector('[aria-label="Delete API key for Usage test"]');
  dom.window.confirm=()=>false;
  await act(async()=>{deleteKey.click();});
  assert.ok(!fetched.includes('/api/v1/connections/fixture-connection/revoke'));
  dom.window.confirm=()=>true;
  await act(async()=>{deleteKey.click();await wait();});
  assert.ok(fetched.includes('/api/v1/connections/fixture-connection/revoke'));
  assert.ok(!connections().querySelector('.connection-name'));
  assert.ok(!connections().querySelector('[aria-label="Connection key"]'));
  await act(async()=>{connections().querySelector('.connection-list input[type="checkbox"]').click();});
  assert.equal(connections().querySelector('.connection-status').dataset.status,'Revoked');
  await act(async()=>{window.dispatchEvent(new CustomEvent('core-ai-goto',{detail:{view:'Skills'}}));await wait();});
  const skillsPanel=document.querySelector('.view:not([hidden]) .skills-page');
  const button=(panel,label)=>[...panel.querySelectorAll('button')].find(control=>control.textContent===label);
  const input=(element,value)=>{
   const proto=Object.getPrototypeOf(element);
   Object.getOwnPropertyDescriptor(proto,'value').set.call(element,value);
   element.dispatchEvent(new dom.window.Event('input',{bubbles:true}));
  };
  assert.match(skillsPanel.querySelector('[aria-current=step]').textContent,/Browse skills/);
  await act(async()=>{button(skillsPanel,'Import or update').click();});
  assert.ok(!skillsPanel.querySelector('.skill-workspace'));
  await act(async()=>{input(skillsPanel.querySelector('.skill-import-grid input'),'example/skills');});
  await act(async()=>{submit(skillsPanel);await wait();});
  assert.match(skillsPanel.querySelector('.notice').textContent,/Scanned 1 skill.*1 skipped files/);
  assert.match(skillsPanel.querySelector('[aria-current=step]').textContent,/Browse skills/);
  assert.match(skillsPanel.querySelector('.skill-detail').textContent,/Example Skills.*Find the Root Cause.*Reproduce a bug/s);
  await act(async()=>{input(skillsPanel.querySelector('.skill-detail input[type=search]'),'root cause');});
  assert.ok(button(skillsPanel,'Find the Root Cause'));
  await act(async()=>{input(skillsPanel.querySelector('.skill-detail input[type=search]'),'systematic-debugging');});
  assert.ok(button(skillsPanel,'Find the Root Cause'));
  const approve=button(skillsPanel,'Approve and activate');
  assert.ok(approve);
  await act(async()=>{approve.click();await wait();});
  assert.ok(fetched.includes('/api/v1/skills/collections/collection/activate'));
  await act(async()=>{button(skillsPanel,'Assign this collection').click();await wait();});
  const agentsPanel=document.querySelector('.view:not([hidden]) .agents-page');
  assert.match(agentsPanel.querySelector('.agent-handoff').textContent,/example\/skills/);
  assert.ok(!skillsPanel.querySelector('.skill-assignments'));
  await act(async()=>{agentsPanel.querySelector('.record').click();await wait();});
  assert.match(agentsPanel.querySelector('[aria-current=step]').textContent,/Attach skills/);
  assert.ok(!agentsPanel.querySelector('.skill-assignment input').checked);
  await act(async()=>{button(agentsPanel,'Add recommended collection').click();});
  assert.deepEqual(assignmentWrites,[]);
  await act(async()=>{agentsPanel.querySelector('.collection-assignment-form').dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await wait();});
  assert.deepEqual(assignmentWrites,[['collection']]);
  await act(async()=>{button(agentsPanel,'Review collections in Skills').click();await wait();});
  assert.ok(button(skillsPanel,'Back to agent'));
  await act(async()=>{button(skillsPanel,'Attach to current agent').click();await wait();});
  assert.match(agentsPanel.querySelector('.agent-detail > header').textContent,/Analyst/);
  const agentAssignment=agentsPanel.querySelector('.collection-assignment-form');
  assert.ok(agentAssignment.querySelector('.skill-assignment input').checked);
  await act(async()=>{agentAssignment.querySelector('.skill-assignment input').click();});
  await act(async()=>{button(agentsPanel,'1. Profile').click();button(agentsPanel,'2. Attach skills').click();});
  assert.ok(!agentAssignment.querySelector('.skill-assignment input').checked);
  await act(async()=>{agentAssignment.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await wait();});
  assert.deepEqual(assignmentWrites,[['collection'],[]]);
  await act(async()=>{button(agentsPanel,'Clear collection').click();});
  await act(async()=>{button(agentsPanel,'New agent').click();});
  await act(async()=>{
   input(agentsPanel.querySelector('.agent-profile input'),'Evidence Reviewer');
   input(agentsPanel.querySelector('.agent-profile textarea'),'Review evidence.');
  });
  await act(async()=>{submit(agentsPanel);await wait();});
  assert.match(agentsPanel.querySelector('.agent-detail > header').textContent,/Evidence Reviewer/);
  await act(async()=>{button(agentsPanel,'New agent').click();});
  await act(async()=>{
   input(agentsPanel.querySelector('.agent-profile input'),'Studio Agent');
   input(agentsPanel.querySelector('.agent-profile textarea'),'Explain the evidence.');
  });
  await act(async()=>{submit(agentsPanel);await wait();});
  assert.match(agentsPanel.querySelector('.agent-detail > header').textContent,/Studio Agent.*Version 1/);
  assert.match(agentsPanel.querySelector('[aria-current=step]').textContent,/Attach skills/);
  await act(async()=>{button(agentsPanel,'3. Run agent').click();await wait();});
  await act(async()=>{button(agentsPanel,'Open agent in Chat').click();await wait();});
  assert.equal(chat().querySelector('[aria-label="Chat agent profile"]').value,'studio-agent');
  await act(async()=>{chat().querySelector('.chat-skills-trigger').click();});
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,230));});
  const skillPicker=document.querySelector('.chat-skills-picker');
  assert.ok(chat().querySelector('.composer-tools [aria-label="Chat agent profile"]'));
  assert.deepEqual([...skillPicker.querySelector('select').options].map(option=>option.textContent),
   ['Automatic matching','Choose specific skills','Use no skills']);
  assert.match(skillPicker.textContent,/Preview for this draft.*Find the Root Cause/);
  await act(async()=>{change(skillPicker.querySelector('select'),'manual');});
  await act(async()=>{await new Promise(resolve=>setTimeout(resolve,230));});
  await act(async()=>{input(skillPicker.querySelector('input[type=search]'),'root cause');});
  assert.match(skillPicker.querySelector('.chat-skill-options').textContent,/Find the Root Cause.*Reproduce a bug/);
  const duplicates=skillPicker.querySelector('.chat-skill-variants');
  assert.match(duplicates.querySelector('summary').textContent,/Find the Root Cause.*2 sources or versions/);
  assert.equal(duplicates.querySelectorAll('input').length,2);
  await act(async()=>{duplicates.querySelector('summary').click();duplicates.querySelector('input').click();});
  assert.match(chat().querySelector('.chat-skills-trigger').textContent,/Selected \(1\)/);
  await act(async()=>{window.dispatchEvent(new CustomEvent('core-ai-goto',{detail:{view:'Workflows'}}));await wait();});
  const workflow=()=>document.querySelector('.view:not([hidden])');
  const researchForm=workflow().querySelector('.research-form');
  for(const [name,value] of Object.entries({project_id:'project',agent_id:'agent',model:'test:latest',prompt:'Explain liquidity',criteria:'Use source citations',queries:'liquidity'})){
   researchForm.elements.namedItem(name).value=value;
  }
  await act(async()=>{researchForm.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await wait();});
  assert.equal(researchWrites.length,1);
  assert.deepEqual(researchWrites[0].research.queries,['liquidity']);
  assert.equal(researchWrites[0].research.require_review,true);
  assert.match(workflow().querySelector('.research-review').textContent,/Evidence report/);
  await act(async()=>{[...workflow().querySelectorAll('button')].find(button=>button.textContent==='Approve and save').click();await wait();});
  assert.ok([...workflow().querySelectorAll('button')].some(button=>button.textContent==='Open saved artifact'));
  const navigate=async view=>act(async()=>{window.dispatchEvent(new CustomEvent('core-ai-goto',{detail:{view}}));await wait();});
  await navigate('Setup');
  const setup=()=>document.querySelector('.view:not([hidden]) .setup-page');
  const task=()=>document.querySelector('.view:not([hidden]) [aria-label=Tasks], .view:not([hidden]):is([aria-label=Tasks])');
  assert.match(setup().querySelector('[aria-current=step]').textContent,/Choose an agent/);
  const template=setup().querySelector('select');
  assert.deepEqual([...template.options].map(option=>option.textContent),['International Forex','India F&O','Strategy validation','Custom agent']);
  await act(async()=>{change(template,'india');});
  assert.match(setup().querySelector('textarea').value,/Indian F&O/);
  await act(async()=>{change(template,'forex');submit(setup());await wait();});
  assert.match(setup().querySelector('[aria-current=step]').textContent,/Attach skills/);
  await act(async()=>{button(setup(),'Open import form').click();await wait();});
  assert.equal(skillsPanel.querySelector('.skill-import-grid input').value,'marian2js/trading-skills');
  await act(async()=>{submit(skillsPanel);await wait();});
  await act(async()=>{button(skillsPanel,'Approve and activate').click();await wait();});
  await act(async()=>{button(skillsPanel,'Continue setup').click();await wait();});
  const assignment=setup().querySelector('.collection-assignment-form');
  const forexCheckbox=()=>[...assignment.querySelectorAll('label')].find(label=>label.textContent.includes('marian2js/trading-skills')).querySelector('input');
  assert.ok(!forexCheckbox().checked);
  const oldAssignments=assignmentWrites.length;
  await act(async()=>{button(setup(),'Continue without skills').click();await wait();});
  assert.equal(assignmentWrites.length,oldAssignments);
  assert.match(setup().querySelector('.setup-readiness').textContent,/0 assigned/);
  await act(async()=>{button(setup(),'Back to skills').click();});
  await act(async()=>{button(setup(),'Add recommended collection').click();});
  assert.ok(forexCheckbox().checked);
  await act(async()=>{button(setup(),'Save and continue').click();await wait();});
  assert.deepEqual(assignmentWrites.at(-1),['forex']);
  assert.match(setup().querySelector('[aria-current=step]').textContent,/Start work/);
  assert.match(setup().querySelector('.setup-readiness').textContent,/1 assigned/);
  const closeGuide=[...document.querySelectorAll('button[aria-label="Close Get started"]')].find(control=>!control.closest('[hidden]'));
  await act(async()=>{closeGuide.click();await wait();});
  await navigate('Setup');
  assert.match(setup().querySelector('[aria-current=step]').textContent,/Start work/);
  assert.match(setup().querySelector('.setup-current').textContent,/International Forex Research/);
  const oldWrites=writes.length;
  await act(async()=>{button(setup(),'Open test chat').click();await wait();});
  assert.equal(chat().querySelector('[aria-label="Chat agent profile"]').value,'guided-agent');
  assert.match(chat().querySelector('[aria-label="Message CORE-AI"]').value,/EURUSD and USDJPY/);
  assert.equal(writes.length,oldWrites);
  responses.projects=[];
  await act(async()=>{button(document,'Refresh').click();await wait();});
  await navigate('Tasks');
  const taskPrompt=()=>task().querySelector('textarea[name=prompt]');
  taskPrompt().value='Keep this unfinished task';
  await navigate('Setup');
  await act(async()=>{button(setup(),'Open task form').click();await wait();});
  assert.equal(taskPrompt().value,'Keep this unfinished task');
  await act(async()=>{button(task(),'Use setup draft').click();});
  assert.equal(task().querySelector('select[name=agent_id]').value,'guided-agent');
  assert.match(taskPrompt().value,/EURUSD and USDJPY/);
  await act(async()=>{button(task(),'Create first project').click();});
  const firstProject=task().querySelector('.task-project form');
  firstProject.elements.namedItem('project_name').value='First Research Project';
  await act(async()=>{firstProject.dispatchEvent(new dom.window.Event('submit',{bubbles:true,cancelable:true}));await wait();});
  assert.equal(taskPrompt().value.includes('EURUSD'),true);
  assert.equal(task().querySelector('select[name=project_id]').value,'first-research-project');
  change(task().querySelector('select[name=model]'),'test:latest');
  await act(async()=>{submit(task());await wait();});
  assert.equal(responses['runs/guided-task'].project_id,'first-research-project');
  assert.equal(responses['runs/guided-task'].agent_id,'guided-agent');
  assert.match(task().querySelector('.result').textContent,/Task result.*QUEUED/);
  await navigate('Projects');
  const directory=()=>document.querySelector('.view:not([hidden]) .project-page');
  await act(async()=>{button(document.querySelector('.explorer-projects'),'First Research Project').click();await wait();});
  await act(async()=>{button(directory(),'Settings').click();await wait();});
  await act(async()=>{button(directory(),'Delete project').click();});
  const deletion=document.querySelector('dialog');
  assert.ok(button(deletion,'Delete').disabled);
  await act(async()=>{input(deletion.querySelector('input'),'First Research Project');});
  assert.ok(!button(deletion,'Delete').disabled);
  await act(async()=>{submit(deletion);await wait();});
  assert.match(directory().textContent,/Project moved to Deleted projects/);
  await act(async()=>{button(directory(),'Restore project').click();await wait();});
  assert.match(directory().textContent,/Project restored to Active projects/);
  await act(async()=>{button(directory(),'Active projects').click();});
  assert.match(directory().querySelector('.project-card').textContent,/First Research Project/);

  await navigate('Tools');
  assert.equal(new URL(window.location.href).searchParams.get('view'),'Tools');
  await navigate('Skills');
  assert.equal(new URL(window.location.href).searchParams.get('view'),'Skills');
  await act(async()=>{window.history.pushState(null,'','/?view=Tools#repository-coverage');window.dispatchEvent(new window.PopStateEvent('popstate'));await wait();});
  assert.equal(document.querySelector('.view:not([hidden])').getAttribute('aria-label'),'Tools');
  assert.ok(document.querySelector('.view:not([hidden]) details[data-repository-coverage]').open);
  assert.match(document.querySelector('.view:not([hidden])').textContent,/Source repositories: 1\/1 verified/);

  const toolsView=document.querySelector('.view:not([hidden])');
  assert.match(toolsView.textContent,/1 \/ 1 qualified/);
  await act(async()=>{button(toolsView,'Inspect / run').click();});
  await act(async()=>{button(toolsView,'Run qualified program').click();await wait();});
  assert.match(toolsView.textContent,/execution-test/);
  assert.match(toolsView.textContent,/"units": 20/);
  const importedDefinition={name:'Repository Reviewer',path:'.github/agents/reviewer.agent.md',description:'Review changes'};
  responses['skills/collections/collection?commit='+catalogCommit].agent_definitions=[importedDefinition];
  const agentQuery=new URLSearchParams({commit:catalogCommit,path:importedDefinition.path});
  responses['skills/collections/collection/agent?'+agentQuery]={...importedDefinition,instructions:'Review with evidence'};
  await navigate('Skills');
  const repoAgents=document.querySelector('.view:not([hidden]) .skills-page');
  await act(async()=>{button(repoAgents,'Browse skills').click();button(document,'Refresh').click();await wait();});
  await act(async()=>{[...repoAgents.querySelectorAll('.record')].find(record=>record.textContent.includes('example/skills')).click();await wait();});
  const intelRoot='skills/collections/collection/intelligence';
  responses[intelRoot+'?'+new URLSearchParams({commit:catalogCommit,q:'',kind:'',offset:'0',limit:'40'})]={
   available:true,files:[{path:'README.md',kind:'documentation',size:10,has_excerpt:true}],
   file_count:1,total:1,kinds:['documentation'],reports:[]
  };
  responses[intelRoot+'/reports/assessment-1']={id:'assessment-1',model:'test:latest',commit_sha:catalogCommit,
   evidence_paths:[{path:'README.md',truncated:false}],verification:[],report:{summary:'One tool found.',
   open_questions:[],capabilities:[{name:'Slide validator',kind:'Task tool',decision:'Install tool',reason:'Documented.',
    sources:['README.md'],prerequisites:[],permissions:[],license_notes:'',steps:[],test_input:'Slides',expected_result:'Valid'}]}};
  await act(async()=>{const details=repoAgents.querySelector('.repo-intelligence');details.open=true;
   details.dispatchEvent(new dom.window.Event('toggle'));await wait();});
  const intelligencePanel=repoAgents.querySelector('.repo-intelligence');
  await act(async()=>{intelligencePanel.querySelector('input[type=checkbox]').click();});
  await act(async()=>{submit(intelligencePanel);await wait();});
  assert.match(intelligencePanel.textContent,/Slide validator.*Install tool/);
  const verification=intelligencePanel.querySelector('article form');
  await act(async()=>{change(verification.querySelector('select'),'Verified');
   input(verification.querySelector('textarea'),'Test passed.');});
  await act(async()=>{submit(intelligencePanel.querySelector('article'));await wait();});
  assert.match(intelligencePanel.textContent,/Test passed/);
  await act(async()=>{
   const details=[...repoAgents.querySelectorAll('details')].find(node=>node.querySelector('summary')?.textContent==='Repository Reviewer');
   details.open=true;details.dispatchEvent(new dom.window.Event('toggle'));await wait();
  });
  assert.match(repoAgents.textContent,/Review with evidence/);
  await act(async()=>{button(repoAgents,'Import agent').click();await wait();});
  const agentView=document.querySelector('.view:not([hidden]) .agents-page');
  assert.match(agentView.querySelector('.catalog-heading').textContent,/Repository Reviewer.*Disabled/);
  assert.equal(agentView.querySelector('input[required]').value,'Repository Reviewer');

 }finally{await act(async()=>root.unmount());global.fetch=fetchOld;delete global.IS_REACT_ACT_ENVIRONMENT;for(const k of Object.keys(old)){if(old[k])Object.defineProperty(global,k,old[k]);else delete global[k];}if(locationOld)Object.defineProperty(global,'location',locationOld);else delete global.location;dom.window.close();}
});
