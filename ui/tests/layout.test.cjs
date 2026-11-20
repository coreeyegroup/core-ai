const {test}=require('node:test');const assert=require('node:assert/strict');const ts=require('typescript');const fs=require('node:fs');const vm=require('node:vm');
const source=fs.readFileSync('src/layout.ts','utf8');const js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS}}).outputText;const box={exports:{}};vm.runInNewContext(js,box);const {restore,defaults,closeTab}=box.exports;
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
 assert.equal(restoreAppearance(JSON.stringify(legacy)).fontSize,14);
 assert.equal(restoreAppearance(JSON.stringify(legacy)).readingSize,17);
 const custom={...legacy,fontSize:15,readingSize:19};
 assert.equal(restoreAppearance(JSON.stringify(custom)).fontSize,15);
 assert.equal(restoreAppearance(JSON.stringify(custom)).readingSize,19);
 assert.equal(restoreAppearance(JSON.stringify({...legacy,typographyVersion})).fontSize,12);
});
