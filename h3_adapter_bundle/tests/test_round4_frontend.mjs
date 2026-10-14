// Original callbacks; fake API only. New identities must not inherit retired/env credentials.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
const source = readFileSync(new URL('../web/h3_adapter.js', import.meta.url), 'utf8').replace(/^import .*;\r?\n/gm, '');
class Element {
 constructor(tag) { this.tag=tag; this.children=[]; this.style={}; this.value=''; this.textContent=''; this.attrs={}; }
 append(...items) { this.children.push(...items); for (const item of items) item.parent=this; }
 replaceChildren(...items) { this.children=[]; this.append(...items); }
 setAttribute(name,value) { this.attrs[name]=value; }
 remove() { if (this.parent) this.parent.children=this.parent.children.filter(item=>item!==this); }
 focus() {}
}
async function harness() {
 const body=new Element('body'), calls=[]; let extension;
 let config=JSON.parse(readFileSync(new URL('../config/providers.example.json',import.meta.url),'utf8')),revision=0,postBarrier;
 config.providers.push({...structuredClone(config.providers[0]),id:'provider_1'});
 const api={async fetchApi(path,init) {
  const payload=init.body===undefined?undefined:JSON.parse(init.body);calls.push({path,payload});
  if(path==='/h3-adapter/config'&&init.method==='POST'){if(postBarrier)await postBarrier();config=structuredClone(payload.config);revision++;return {ok:true,status:200,json:async()=>({ok:true,revision:String(revision)})};}
  const data=path==='/h3-adapter/config'?{config,revision:String(revision),keys:{primary:true,provider_1:true}}:{ok:true,has_key:!!payload.key};
  return {ok:true,status:200,json:async()=>structuredClone(data)};
 }};
 vm.runInNewContext(source,{app:{registerExtension(e){extension=e;}},api,document:{body,createElement:tag=>new Element(tag)},structuredClone});
 function Node(){this.widgets=[{name:'provider',value:'auto'}];}
 Node.prototype.addWidget=function(type,name,value,callback){this.widgets.push({name,value,callback});};
 await extension.beforeRegisterNodeDef(Node,{name:'H3ImageEdit'});const node=new Node();node.onNodeCreated();await node.widgets.find(w=>w.name==='H3 供应商 / 密钥').callback();
 const all=(e=body)=>[e,...e.children.flatMap(child=>all(child))];
 return {calls,field:label=>all().find(e=>e.attrs['aria-label']===label),button:label=>all().find(e=>e.tag==='button'&&e.textContent===label),barrier:fn=>{postBarrier=fn;},status:()=>all().find(e=>e.attrs.role==='status').textContent};
}
let failures=0;
async function check(name,run){try{await run();console.log('PASS '+name);}catch(error){failures++;console.error('FAIL '+name+'\n'+error.stack);}}
await check('new provider does not reuse deleted private identity',async()=>{
 const h=await harness();h.field('供应商').value='provider_1';h.field('供应商').onchange();h.button('删除所选供应商').onclick();await h.button('保存配置').onclick();h.button('新增供应商（先禁用）').onclick();
 const added=JSON.parse(h.field('非秘密配置 JSON').value).providers.at(-1);assert.notEqual(added.id,'provider_1');assert.equal(added.enabled,false);
});
await check('new provider does not inherit shipped primary environment',async()=>{
 const h=await harness();h.button('新增供应商（先禁用）').onclick();const cfg=JSON.parse(h.field('非秘密配置 JSON').value);
 assert.equal(cfg.providers.at(-1).key_env,'','A new provider needs an explicit independent credential source');
});
await check('key save sends displayed revision and successful config save updates it',async()=>{
 const h=await harness();h.field('供应商密钥').value='ROUND4-FAKE-KEY';await h.button('保存密钥').onclick();
 let keyCall=h.calls.filter(c=>c.path==='/h3-adapter/key').at(-1);assert.equal(keyCall.payload.expected_revision,'0');
 await h.button('保存配置').onclick();h.field('供应商密钥').value='ROUND4-FAKE-NEXT';await h.button('保存密钥').onclick();keyCall=h.calls.filter(c=>c.path==='/h3-adapter/key').at(-1);assert.equal(keyCall.payload.expected_revision,'1');assert.equal(h.field('供应商密钥').value,'');
});
await check('unapplied provider ID BaseURL or key_env prevents key HTTP',async()=>{
 for(const label of ['供应商 ID','Base URL','Key 环境变量名']){
  const h=await harness();h.field(label).value='not-yet-applied';h.field('供应商密钥').value='ROUND4-FAKE-KEY';await h.button('保存密钥').onclick();
  assert.equal(h.calls.filter(c=>c.path==='/h3-adapter/key').length,0,label);assert.match(h.status(),/应用|保存/);assert.equal(h.field('供应商密钥').value,'');
 }
});
await check('unsaved JSON identity prevents key until explicit config save',async()=>{
 const h=await harness();h.field('Base URL').value='https://merchant-b.example.invalid/v1';h.button('应用供应商表单到 JSON').onclick();h.field('供应商密钥').value='ROUND4-FAKE-B-KEY';await h.button('保存密钥').onclick();
 assert.equal(h.calls.filter(c=>c.path==='/h3-adapter/key').length,0);assert.match(h.status(),/保存/);
 await h.button('保存配置').onclick();h.field('供应商密钥').value='ROUND4-FAKE-B-KEY';await h.button('保存密钥').onclick();assert.equal(h.calls.filter(c=>c.path==='/h3-adapter/key').length,1);
});
await check('pending config save stores clicked snapshot not later editor content',async()=>{
 const h=await harness(),editor=h.field('非秘密配置 JSON');let cfg=JSON.parse(editor.value);cfg.cooldown_seconds=79;editor.value=JSON.stringify(cfg);
 let entered,release;const reached=new Promise(resolve=>{entered=resolve;});h.barrier(async()=>{entered();await new Promise(resolve=>{release=resolve;});});
 const saving=h.button('保存配置').onclick();await reached;cfg=JSON.parse(editor.value);cfg.providers[0].base_url='https://merchant-b.example.invalid/v1';editor.value=JSON.stringify(cfg);release();await saving;
 assert.notEqual(h.calls.find(c=>c.path==='/h3-adapter/config'&&c.payload)?.payload.config.providers[0].base_url,cfg.providers[0].base_url);
 h.field('供应商密钥').value='ROUND4-FAKE-B-KEY';await h.button('保存密钥').onclick();assert.equal(h.calls.filter(c=>c.path==='/h3-adapter/key').length,0);
});
process.exitCode=failures?1:0;
