import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";
const path = fileURLToPath(new URL("../web/h3_adapter.js", import.meta.url));
assert.ok(existsSync(path), "H3 frontend extension exists");
const source = readFileSync(path, "utf8").replace(/^import .*;\r?\n/gm, "");
assert.ok(!/localStorage|sessionStorage|innerHTML/.test(source), "No browser secret persistence or unsafe HTML");
class Element {
  constructor(tag) { this.tagName = tag; this.children = []; this.style = {}; this.value = ""; this.listeners = {}; this.textContent = ""; this.attributes = {}; }
  append(...children) { this.children.push(...children); for (const c of children) if (c && typeof c === "object") c.parentElement = this; }
  appendChild(c) { this.append(c); return c; }
  replaceChildren(...c) { this.children = []; this.append(...c); }
  setAttribute(k, v) { this.attributes[k] = v; }
  addEventListener(k, v) { this.listeners[k] = v; }
  remove() { if(this.parentElement) this.parentElement.children = this.parentElement.children.filter(c => c !== this); }
  focus() {}
}
const body = new Element("body");
const document = { body, createElement: tag => new Element(tag) };
function all(el=body) { return [el, ...el.children.filter(c=>c && typeof c==="object").flatMap(c=>all(c))]; }
function button(text) { const el = all().find(x=>x.tagName==="button" && x.textContent===text); assert.ok(el, text); return el; }
function field(label) { const el=all().find(x=>x.attributes["aria-label"]===label); assert.ok(el,label); return el; }
let extension, config = {version:1,primary:"primary",fallbacks:[],currency:"USD",providers:[{id:"primary",base_url:"https://mock.example/v1",protocol:"openai_images",edit_path:"/images/edits",key_env:"H3_PRIMARY_KEY",models:{"background-edit":{id:"old-model",task:"image_edit",supports_mask:false,allowed_params:[]}}}]};
const calls=[];
let challenge = false;
const api = { async fetchApi(path, init={}) {
  calls.push({path,init});
  if(challenge && !init.headers?.["X-H3-Management-Token"]) return {ok:false,status:401,json:async()=>({error:"Management authorization required"})};
  if(path==="/h3-adapter/config" && init.method==="POST") config=JSON.parse(init.body).config;
  const data=path==="/h3-adapter/config" ? {config,keys:{primary:false}} : path==="/h3-adapter/models" ? {models:["text-chat","new-image"],source:"api",warning:"Discovery does not verify image-edit capability"} : {ok:true,has_key:!!JSON.parse(init.body).key};
  return {ok:true,status:200,json:async()=>structuredClone(data)};
}};
vm.runInNewContext(source,{app:{registerExtension(e){extension=e;}},api,document,console,structuredClone,JSON,Promise,Error,Set,Array,String,Number,Boolean,Object});
assert.equal(extension.name,"h3.adapter");
function Node() { this.widgets=[{name:"provider",value:"auto"},{name:"model_alias",value:"background-edit"}]; this.size=[420,240]; }
Node.prototype.onNodeCreated=function(){this.oldCreated=true; return "old-return";};
Node.prototype.onExecuted=function(){this.oldExecuted=true;};
Node.prototype.addWidget=function(type,name,value,callback,options){const widget={type,name,value,callback,options};this.widgets.push(widget);return widget;};
await extension.beforeRegisterNodeDef(Node,{name:"H3ImageEdit"});
const node=new Node();
assert.equal(node.onNodeCreated(),"old-return");
assert.equal(node.widgets.filter(w=>w.type==="button").length,2);
assert.ok(node.widgets.filter(w=>w.type==="button").every(w=>w.options.serialize===false));
await node.widgets.find(w=>w.name==="H3 供应商 / 密钥").callback();
const editor=field("非秘密配置 JSON");
assert.ok(!editor.value.includes("dont-save"));
await button("新增供应商（先禁用）").onclick();
let edited=JSON.parse(editor.value);
assert.equal(edited.providers.length,2);
const added=edited.providers.find(p=>p.id!=="primary");
assert.equal(added.enabled,false,"New provider cannot immediately receive paid work");
assert.notEqual(added.key_env,"H3_PRIMARY_KEY","Clone does not inherit original key reference");
const enabled=field("启用供应商");
assert.equal(enabled.checked,false);
enabled.checked=true;
button("应用供应商表单到 JSON").onclick();
assert.equal(JSON.parse(editor.value).providers.find(p=>p.id===added.id).enabled,true);
await button("保存配置").onclick();
button("删除所选供应商").onclick();
await button("保存配置").onclick();
assert.equal(config.providers.length,1);
assert.equal(config.primary,"primary");
assert.ok(!config.fallbacks.includes(added.id));
button("删除所选供应商").onclick();
assert.equal(JSON.parse(editor.value).providers.length,1,"Cannot delete last provider");
const key=field("供应商密钥");
key.value="dont-save";
await button("保存密钥").onclick();
assert.equal(key.value,"","Clear secret after save");
const keyCall=calls.find(x=>x.path==="/h3-adapter/key");
assert.deepEqual(JSON.parse(keyCall.init.body),{provider_id:"primary",key:"dont-save"});
assert.ok(node.widgets.every(w=>w.value!=="dont-save"));
button("关闭").onclick();
await node.widgets.find(w=>w.name==="H3 搜索 / 选择模型").callback();
assert.equal(calls.filter(x=>x.path==="/h3-adapter/models").length,1);
const search=field("搜索模型");
search.value="new-image";
search.oninput();
assert.ok(all().some(x=>x.textContent==="new-image"));
const manual=field("实际模型 ID");
manual.value="manual-edit";
await button("保存映射并用于本节点").onclick();
assert.equal(config.providers[0].models["background-edit"].id,"manual-edit");
assert.equal(config.providers[0].models["background-edit"].supports_mask,false,"Discovery does not invent capabilities");
assert.equal(node.widgets[0].value,"auto","Model mapping does not silently disable automatic primary/backups");
node.onExecuted({report:[JSON.stringify({status:"success",actual_provider:"primary",actual_model:"manual-edit",error:"<img src=x>"})]});
assert.ok(node.oldExecuted);
assert.ok(node.h3ReportText.includes("<img src=x>"),"Report displayed as text");
challenge = true;
const pending=node.widgets.find(w=>w.name==="H3 供应商 / 密钥").callback();
await new Promise(resolve=>setImmediate(resolve));
const token=field("管理令牌");
assert.equal(token.type,"password");
token.value="memory-only-admin-token";
await button("授权").onclick();
await pending;
assert.equal(token.value,"");
assert.ok(calls.some(c=>c.init.headers?.["X-H3-Management-Token"]==="memory-only-admin-token"));
assert.ok(!field("非秘密配置 JSON").value.includes("memory-only-admin-token"));
button("关闭").onclick();
console.log("Frontend contract: hooks, nonserialized controls, secret modal, model mapping, report, management-token retry passed.");
