// Exercise the shipped UI callbacks with synthetic providers and node parameters.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../web/h3_adapter.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.attrs={};this.value='';this.textContent='';}
 append(...items){this.children.push(...items);for(const e of items)e.parent=this;}
 replaceChildren(...items){this.children=[];this.append(...items);}
 setAttribute(k,v){this.attrs[k]=v;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this);}
 focus(){}
}
async function fixture(provider='a') {
 let extension,config={version:1,primary:'a',fallbacks:['b'],providers:['a','b'].map(id=>({id,enabled:true,base_url:'https://'+id+'.invalid',models:{edit:{id:'model-'+id,task:'image_edit',defaults:{size:id==='a'?'1024x1024':'auto'}}}}))};
 const body=new Element('body'),calls=[];
 const api={async fetchApi(url,init){calls.push(url);let data;if(url==='/h3-adapter/config'&&init.method==='POST'){config=JSON.parse(init.body).config;data={ok:true,revision:'2'};}else if(url==='/h3-adapter/config')data={config,revision:'1',keys:{a:true,b:true}};else if(url==='/h3-adapter/models')data={models:['model-a','model-b'],source:'api'};else throw Error(url);return {ok:true,status:200,json:async()=>structuredClone(data)};}};
 vm.runInNewContext(source,{app:{registerExtension(e){extension=e;}},api,document:{body,createElement:tag=>new Element(tag)},structuredClone});
 function Node(){this.widgets=[{name:'provider',value:provider},{name:'model_alias',value:'edit'},{name:'parameters',value:'{"size":"1024x1024"}'}];}
 Node.prototype.addWidget=function(type,name,value,callback){this.widgets.push({name,value,callback});};
 await extension.beforeRegisterNodeDef(Node,{name:'H3ImageEdit'});const node=new Node();node.onNodeCreated();
 const all=(e=body)=>[e,...e.children.flatMap(c=>all(c))];
 return {node,calls,field:label=>all().find(e=>e.attrs['aria-label']===label),button:label=>all().find(e=>e.tag==='button'&&e.textContent===label),open:name=>node.widgets.find(w=>w.name===name).callback(),param:()=>node.widgets.find(w=>w.name==='parameters').value};
}
let failed=0;
async function check(name,run){try{await run();console.log('PASS '+name);}catch(e){failed++;console.error('FAIL '+name+': '+e.message);}}
await check('provider A to B clears prior size',async()=>{const h=await fixture();await h.open('H3 供应商 / 密钥');h.field('供应商').value='b';h.field('供应商').onchange();h.button('本节点使用所选供应商').onclick();assert.equal(h.param(),'{}');});
await check('fixed provider to auto clears prior size',async()=>{const h=await fixture();await h.open('H3 供应商 / 密钥');h.button('本节点恢复 auto').onclick();assert.equal(h.param(),'{}');});
await check('unchanged provider preserves explicit parameters',async()=>{const h=await fixture();await h.open('H3 供应商 / 密钥');h.button('本节点使用所选供应商').onclick();assert.equal(h.param(),'{"size":"1024x1024"}');});
await check('changed model clears prior size',async()=>{const h=await fixture();await h.open('H3 搜索 / 选择模型');h.field('实际模型 ID').value='model-new';await h.button('保存映射并用于本节点').onclick();assert.equal(h.param(),'{}');});
await check('changed alias clears prior size',async()=>{const h=await fixture();await h.open('H3 搜索 / 选择模型');h.field('逻辑模型别名').value='other';h.field('实际模型 ID').value='model-new';await h.button('保存映射并用于本节点').onclick();assert.equal(h.param(),'{}');});
await check('unchanged mapping preserves explicit parameters',async()=>{const h=await fixture();await h.open('H3 搜索 / 选择模型');await h.button('保存映射并用于本节点').onclick();assert.equal(h.param(),'{"size":"1024x1024"}');});
process.exitCode=failed?1:0;
