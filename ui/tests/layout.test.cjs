const {test}=require('node:test');const assert=require('node:assert/strict');const ts=require('typescript');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('src/layout.ts','utf8');const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;const box={exports:{},URLSearchParams};vm.runInNewContext(js,box);const {restore,defaults,closeTab,focusView,readView}=box.exports;
test('corrupted browser layout resets safely',()=>{for(const s of ['no json','{}','{"version":1}','{"groups":[null]}'])assert.equal(restore(s).active[0],'Chat');});
test('invalid active pane and dimensions reset',()=>{const l=defaults();l.groups=[['Tasks']];assert.equal(restore(JSON.stringify(l)).active[0],'Chat');l.groups=[['Chat']];l.leftWidth=99999;assert.equal(restore(JSON.stringify(l)).leftWidth,260);});
test('closing last panel retains usable home',()=>{const l=closeTab(defaults(),'Chat',0);assert.equal(l.groups.length,1);assert.equal(l.active[0],'Chat');});
test('closing a split clamps focused group',()=>{const l=defaults();l.groups=[['Chat'],['Tasks']];l.active=['Chat','Tasks'];l.focus=1;const out=closeTab(l,'Tasks',1);assert.equal(out.focus,0);assert.equal(out.groups.length,1);});

test('typography upgrades the legacy defaults while retaining custom sizes',()=>{
 const appearanceSource=fs.readFileSync('src/appearance.ts','utf8');
 const compiled=ts.transpileModule(appearanceSource,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;
 const module={exports:{}};
 vm.runInNewContext(compiled,module);
 const {restoreAppearance,defaultAppearance,typographyVersion}=module.exports;
 const legacy={...defaultAppearance,fontSize:12,readingSize:14};
 assert.equal(restoreAppearance(JSON.stringify(legacy)).fontSize,15);
 assert.equal(restoreAppearance(JSON.stringify(legacy)).readingSize,17);
 const custom={...legacy,fontSize:15,readingSize:19};
 assert.equal(restoreAppearance(JSON.stringify(custom)).fontSize,15);
 assert.equal(restoreAppearance(JSON.stringify(custom)).readingSize,19);
 assert.equal(restoreAppearance(JSON.stringify({...legacy,typographyVersion})).fontSize,12);
});

test('shareable page selection retains saved panes and rejects unknown views',()=>{
 const l=defaults();
 l.groups=[['Chat','Tools'],['Skills']];l.active=['Chat','Skills'];l.paneIds=['primary','second'];l.focus=0;
 const direct=focusView(l,readView('?view=Skills'));
 assert.equal(direct.focus,1);
 assert.equal(direct.active[1],'Skills');
 assert.equal(direct.groups.length,2);
 assert.equal(direct.paneIds[0],'primary');
 assert.equal(l.focus,0);
 const newView=focusView(l,readView('?view=Workflows'));
 assert.equal(newView.active[0],'Workflows');
 assert.equal(newView.groups[0].includes('Workflows'),true);
 assert.equal(l.groups[0].includes('Workflows'),false);
 assert.equal(readView('?view=invalid'),null);
 assert.equal(readView(''),null);
});
