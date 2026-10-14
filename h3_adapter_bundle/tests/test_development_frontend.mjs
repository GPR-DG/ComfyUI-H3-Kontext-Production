// Exercise production callbacks; all credentials and providers are synthetic.
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
const config={version:1,primary:'a',fallbacks:[],providers:[{id:'a',enabled:true,base_url:'https://a.invalid',key_env:'',models:{edit:{id:'synthetic-model'}}}]};
function fixture(handler){
 const body=new Element('body'),calls=[],context={app:{registerExtension(){}},api:{async fetchApi(url,init){calls.push({url,init});return handler(url,init);}},document:{body,createElement:tag=>new Element(tag)}};
 vm.createContext(context);
 vm.runInContext(source+'\n globalThis.testUI={request,openManager,setToken:v=>managementToken=v,getToken:()=>managementToken};',context);
 const all=(e=body)=>[e,...e.children.flatMap(c=>all(c))];
 return {...context.testUI,calls,field:label=>all().find(e=>e.attrs['aria-label']===label),button:label=>all().find(e=>e.tag==='button'&&e.textContent===label),status:()=>all().find(e=>e.attrs.role==='status')};
}
const response=(data,status=200)=>({ok:status===200,status,json:async()=>structuredClone(data)});
const deferred=()=>{let resolve;const promise=new Promise(r=>resolve=r);return {promise,resolve};};
await (async()=>{
 const h=fixture(async()=>{throw Error('ByteString token failure');});h.setToken('中文');
 await assert.rejects(h.request('/h3-adapter/config'),/ByteString/);assert.equal(h.getToken(),'');
 console.log('PASS invalid cached token cleared on fetch failure');
})();
await (async()=>{
 const h=fixture(async()=>response({error:'denied'},401));h.setToken('expired');
 await assert.rejects(h.request('/h3-adapter/config',undefined,false),/denied/);assert.equal(h.getToken(),'');
 console.log('PASS denied last retry clears cached token');
})();
await (async()=>{
 const pending=deferred();let revision='1';
 const h=fixture(async(url,init)=>{if(init.method==='POST'){await pending.promise;revision='2';return response({ok:true,revision});}return response({config,revision,keys:{a:true}});});
 await h.openManager({widgets:[{name:'provider',value:'a'}]});
 const save=h.button('保存配置').onclick();h.field('非秘密配置 JSON').value='{';pending.resolve();await save;
 assert.match(h.status().textContent,/配置已保存/);assert.match(h.status().textContent,/当前 JSON 编辑无效/);assert.equal(h.field('非秘密配置 JSON').value,'{');assert.equal(revision,'2');
 console.log('PASS successful save survives invalid unsaved editor');
})();
await (async()=>{
 const pending=deferred();let posts=0;
 const h=fixture(async(url,init)=>{if(url==='/h3-adapter/key'){posts++;await pending.promise;return response({has_key:true});}return response({config,revision:'1',keys:{a:false}});});
 await h.openManager({widgets:[{name:'provider',value:'a'}]});
 h.field('供应商密钥').value='synthetic-secret';const button=h.button('保存密钥'),first=button.onclick();assert.equal(button.disabled,true);
 await button.onclick();assert.equal(posts,1);h.button('关闭').onclick();pending.resolve();await first;assert.equal(posts,1);assert.equal(button.disabled,false);
 console.log('PASS overlapping key submissions serialized and close handled');
})();
