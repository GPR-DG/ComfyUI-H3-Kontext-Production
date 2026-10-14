// Independent audit-round2 harness. Executes original extension callbacks; no network.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
const sourcePath = fileURLToPath(new URL('../web/h3_adapter.js', import.meta.url));
const source = readFileSync(sourcePath, 'utf8').replace(/^import .*;\r?\n/gm, '');
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.value = ''; this.textContent = ''; this.attributes = {}; }
  append(...children) { this.children.push(...children); for (const c of children) c.parentElement = this; }
  replaceChildren(...c) { this.children = []; this.append(...c); }
  setAttribute(k, v) { this.attributes[k] = v; }
  remove() { if (this.parentElement) this.parentElement.children = this.parentElement.children.filter(c => c !== this); }
  focus() {}
}
const fresh = () => ({version:1,primary:'primary',fallbacks:['backup1','backup2','backup3'],currency:'USD',auto_failover:true,cooldown_seconds:60,
  providers:['primary','backup1','backup2','backup3'].map((id,i)=>({id,enabled:true,base_url:`https://${id}.example/v1`,protocol:'openai_images',edit_path:'/images/edits',key_env:`H3_${id.toUpperCase()}_KEY`,priority:i+1,
  models:{'background-edit':{id:`${id}-old-model`,task:'image_edit',supports_mask:true,mask_encoding:'grayscale_white_edit',max_images:8,price_upper_bound:0.1,allowed_params:['quality','size'],defaults:{quality:'high',size:'1024x1024'}},
  'other-edit':{id:`${id}-other-model`,task:'image_edit',supports_mask:false,max_images:1,price_upper_bound:1.0,allowed_params:[],defaults:{}}}}))});
async function harness() {
  const body = new Element('body');
  const calls = [];
  let extension, config = fresh(), revision = 0, postBarrier, getBarrier, modelsBarrier;
  const api = {async fetchApi(path,init={}) {
    const payload = init.body === undefined ? undefined : JSON.parse(init.body);
    calls.push({path,method:init.method,payload:structuredClone(payload)});
    if(path==='/h3-adapter/config' && init.method==='POST') {
      if(postBarrier) await postBarrier(payload);
      if(payload.expected_revision !== undefined && payload.expected_revision !== String(revision)) return {ok:false,status:409,json:async()=>({error:'Configuration changed; reload before saving'})};
      config=structuredClone(payload.config); revision++;
      return {ok:true,status:200,json:async()=>({ok:true,revision:String(revision)})};
    }
    if(path==='/h3-adapter/config' && init.method==='GET' && getBarrier) await getBarrier();
    if(path==='/h3-adapter/models' && modelsBarrier) await modelsBarrier();
    const data = path==='/h3-adapter/config' ? {config,revision:String(revision),keys:Object.fromEntries(config.providers.map(p=>[p.id,false]))} : path==='/h3-adapter/key' ? {ok:true,has_key:!!payload.key} : {models:['new-model','another-model'],source:'api'};
    const snapshot = structuredClone(data);
    return {ok:true,status:200,json:async()=>snapshot};
  }};
  vm.runInNewContext(source,{app:{registerExtension(e){extension=e;}},api,document:{body,createElement:tag=>new Element(tag)},console,structuredClone,JSON,Promise,Error,Set,Array,String,Number,Boolean,Object});
  function Node(provider='auto') { this.widgets=[{name:'provider',value:provider},{name:'model_alias',value:'background-edit'}]; }
  Node.prototype.addWidget=function(type,name,value,callback,options){const w={type,name,value,callback,options};this.widgets.push(w);return w;};
  await extension.beforeRegisterNodeDef(Node,{name:'H3ImageEdit'});
  function all(el=body) { return [el,...el.children.flatMap(c=>all(c))]; }
  function field(label,root=body) { const el=all(root).find(e=>e.attributes['aria-label']===label); assert.ok(el,label); return el; }
  function button(label,root=body) { const el=all(root).find(e=>e.tagName==='button'&&e.textContent===label);assert.ok(el,label);return el; }
  async function open(node,name) { await node.widgets.find(w=>w.name===name).callback(); return body.children.at(-1); }
  return {body,calls,Node,field,button,all,open,get:()=>structuredClone(config),mutate:fn=>{fn(config);revision++;},barrier:fn=>{postBarrier=fn;},getBarrier:fn=>{getBarrier=fn;},modelsBarrier:fn=>{modelsBarrier=fn;}};
}
const picker='H3 搜索 / 选择模型', manager='H3 供应商 / 密钥';
let failures=0,total=0;
async function check(name,fn) { total++; try { await fn(); console.log(`PASS ${name}`); } catch(error) { failures++; console.error(`FAIL ${name}\n${error.stack}`); } }
const status=(h,ui)=>h.all(ui).find(e=>e.attributes.role==='status').textContent;
await check('mapping save preserves auto provider and all three fallback mappings',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);
  h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  assert.equal(node.widgets[0].value,'auto');assert.deepEqual(h.get().fallbacks,['backup1','backup2','backup3']);
  assert.equal(h.get().providers[1].models['background-edit'].id,'backup1-old-model');
});
await check('mapping save does not replace an explicitly fixed provider',async()=>{
  const h=await harness(),node=new h.Node('backup2');node.onNodeCreated();const ui=await h.open(node,picker);
  h.field('模型供应商',ui).value='primary';await h.field('模型供应商',ui).onchange();
  h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  assert.equal(node.widgets[0].value,'backup2');
});
await check('changed model ID clears old model capabilities, price and parameter metadata',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);
  h.field('实际模型 ID',ui).value='unverified-new-model';await h.button('保存映射并用于本节点',ui).onclick();
  assert.deepEqual(h.get().providers[0].models['background-edit'],{id:'unverified-new-model',task:'image_edit',supports_mask:false,max_images:1,price_upper_bound:null,allowed_params:[],defaults:{}});
});
await check('unchanged model ID retains explicitly configured metadata',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const before=h.get().providers[0].models['background-edit'],ui=await h.open(node,picker);
  await h.button('保存映射并用于本节点',ui).onclick();assert.deepEqual(h.get().providers[0].models['background-edit'],before);
});
await check('new alias remains conservatively configured',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);
  h.field('逻辑模型别名',ui).value='new-alias';h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  assert.deepEqual(h.get().providers[0].models['new-alias'],{id:'new-model',task:'image_edit',supports_mask:false,max_images:1,price_upper_bound:null,allowed_params:[],defaults:{}});
});
await check('alias change loads that aliases mapped model before save',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);
  const alias=h.field('逻辑模型别名',ui);alias.value=' other-edit ';await alias.onchange?.();
  assert.equal(h.field('实际模型 ID',ui).value,'primary-other-model');await h.button('保存映射并用于本节点',ui).onclick();
  assert.equal(h.get().providers[0].models['other-edit'].id,'primary-other-model');assert.equal(node.widgets[1].value,'other-edit');
});
await check('manager rejects stale save and retains user editor on conflict',async()=>{
  const h=await harness(),a=new h.Node(),b=new h.Node();a.onNodeCreated();b.onNodeCreated();const ua=await h.open(a,manager),ub=await h.open(b,manager);
  const ea=h.field('非秘密配置 JSON',ua),eb=h.field('非秘密配置 JSON',ub);
  const ca=JSON.parse(ea.value);ca.providers[0].models['background-edit'].price_upper_bound=10;ea.value=JSON.stringify(ca);await h.button('保存配置',ua).onclick();
  const cb=JSON.parse(eb.value);cb.cooldown_seconds=99;eb.value=JSON.stringify(cb);const unsaved=eb.value;await h.button('保存配置',ub).onclick();
  assert.equal(h.get().providers[0].models['background-edit'].price_upper_bound,10);assert.equal(h.get().cooldown_seconds,60);
  assert.equal(eb.value,unsaved);assert.match(status(h,ub),/Configuration changed/);
});
await check('manager uses current revision for each successive successful save',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,manager),editor=h.field('非秘密配置 JSON',ui);
  for(const cooldown of [70,80]) { const cfg=JSON.parse(editor.value);cfg.cooldown_seconds=cooldown;editor.value=JSON.stringify(cfg);await h.button('保存配置',ui).onclick(); }
  const calls=h.calls.filter(c=>c.path==='/h3-adapter/config'&&c.method==='POST');
  assert.deepEqual(calls.map(c=>c.payload.expected_revision),['0','1']);assert.equal(h.get().cooldown_seconds,80);
});
await check('picker rejects config change between latest GET and POST without node mutation',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);h.field('逻辑模型别名',ui).value='new-alias';h.field('实际模型 ID',ui).value='new-model';
  let release,entered;const barrierEntered=new Promise(resolve=>{entered=resolve;});h.barrier(async()=>{entered();await new Promise(resolve=>{release=resolve;});});
  const save=h.button('保存映射并用于本节点',ui).onclick();await barrierEntered;h.mutate(cfg=>{cfg.providers[0].models['background-edit'].price_upper_bound=10;});release();await save;
  assert.equal(h.get().providers[0].models['background-edit'].price_upper_bound,10);assert.equal(h.get().providers[0].models['new-alias'],undefined);
  assert.equal(node.widgets[0].value,'auto');assert.equal(node.widgets[1].value,'background-edit');assert.equal(h.field('实际模型 ID',ui).value,'new-model');assert.match(status(h,ui),/Configuration changed/);
});
await check('picker preserves changes made before its latest GET',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);h.mutate(cfg=>{cfg.cooldown_seconds=99;});
  h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();assert.equal(h.get().cooldown_seconds,99);
});
await check('changed model keeps visible reconfirmation warning after save',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  assert.ok(h.body.children.includes(ui),'warning dialog remains visible');assert.match(status(h,ui),/能力|报价|价格/);assert.match(status(h,ui),/重新|确认/);
});
await check('pending mapping save targets provider selected at click despite UI switch',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);h.field('实际模型 ID',ui).value='primary-new-model';
  let release,entered;const enteredGet=new Promise(resolve=>{entered=resolve;});h.getBarrier(async()=>{entered();await new Promise(resolve=>{release=resolve;});});
  const saving=h.button('保存映射并用于本节点',ui).onclick();await enteredGet;
  h.field('模型供应商',ui).value='backup1';await h.field('模型供应商',ui).onchange();release();await saving;
  assert.equal(h.get().providers[0].models['background-edit'].id,'primary-new-model');assert.equal(h.get().providers[1].models['background-edit'].id,'backup1-old-model');
  assert.match(status(h,ui),/primary/);
});
await check('refresh after changed mapping uses the successfully saved ID',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  await h.button('刷新模型列表',ui).onclick();assert.equal(h.field('实际模型 ID',ui).value,'new-model');
});
await check('discovery pending at save cannot replace model reconfirmation warning',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,picker);
  let release,entered;const enteredModels=new Promise(resolve=>{entered=resolve;});h.modelsBarrier(async()=>{entered();await new Promise(resolve=>{release=resolve;});});
  const refreshing=h.button('刷新模型列表',ui).onclick();await enteredModels;h.field('实际模型 ID',ui).value='new-model';await h.button('保存映射并用于本节点',ui).onclick();
  const savedWarning=status(h,ui);assert.match(savedWarning,/重新|确认/);release();await refreshing;assert.equal(status(h,ui),savedWarning);
});
await check('provider fixing remains explicit in manager',async()=>{
  const h=await harness(),node=new h.Node();node.onNodeCreated();const ui=await h.open(node,manager);h.field('供应商',ui).value='backup1';
  h.button('本节点使用所选供应商',ui).onclick();assert.equal(node.widgets[0].value,'backup1');h.button('本节点恢复 auto',ui).onclick();assert.equal(node.widgets[0].value,'auto');
});
console.log(`Frontend review regression: ${total-failures}/${total} passed`);process.exitCode=failures?1:0;
