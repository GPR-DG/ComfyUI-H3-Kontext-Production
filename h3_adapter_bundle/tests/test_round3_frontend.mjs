// Round3 independent regression: original extension callback with delayed key response.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const source=readFileSync(new URL('../web/h3_adapter.js',import.meta.url),'utf8').replace(/^import .*;\r?\n/gm,'');
class Element {
 constructor(tag){this.tag=tag;this.children=[];this.style={};this.value='';this.textContent='';this.attrs={}}
 append(...items){this.children.push(...items);for(const item of items)item.parent=this}
 replaceChildren(...items){this.children=[];this.append(...items)}
 setAttribute(name,value){this.attrs[name]=value}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(e=>e!==this)}
 focus(){}
}
async function trial({switchProvider=false,secret='synthetic-round3',initialKeys={a:false,b:false},effectiveEnvironment=false}={}){
 let extension,release;const body=new Element('body'),calls=[];
 const config={version:1,primary:'a',fallbacks:['b'],providers:['a','b'].map(id=>({id,enabled:true,base_url:`https://${id}.example/v1`,key_env:'',models:{edit:{id:'old',task:'image_edit'}}}))};
 const keys={...initialKeys};
 const api={async fetchApi(path,init){
  let data;
  if(path==='/h3-adapter/config')data={config,revision:'synthetic',keys:{...keys}};
  else if(path==='/h3-adapter/key'){
   const payload=JSON.parse(init.body);calls.push({provider_id:payload.provider_id,hasKey:!!payload.key});
   await new Promise(resolve=>release=resolve);keys[payload.provider_id]=!!payload.key || effectiveEnvironment;data={ok:true,has_key:keys[payload.provider_id]};
  }else throw Error('Unexpected fixture endpoint');
  return {ok:true,status:200,json:async()=>structuredClone(data)};
 }};
 vm.runInNewContext(source,{app:{registerExtension(e){extension=e}},api,document:{body,createElement:tag=>new Element(tag)},structuredClone});
 function Node(){this.widgets=[{name:'provider',value:'auto'}]}
 Node.prototype.addWidget=function(type,name,value,callback){this.widgets.push({name,value,callback})};
 await extension.beforeRegisterNodeDef(Node,{name:'H3ImageEdit'});
 const node=new Node();node.onNodeCreated();await node.widgets.find(w=>w.name==='H3 供应商 / 密钥').callback();
 const all=(e=body)=>[e,...e.children.flatMap(c=>all(c))];
 const field=label=>all().find(e=>e.attrs['aria-label']===label);
 const button=label=>all().find(e=>e.tag==='button'&&e.textContent===label);
 const status=()=>all().find(e=>e.attrs.role==='status').textContent;
 field('供应商密钥').value=secret;const saving=button('保存密钥').onclick();
 assert.equal(field('供应商密钥').value,'');
 if(switchProvider){field('供应商').value='b';field('供应商').onchange()}
 const selectedStatus=status();release();await saving;
 assert.deepEqual(calls,[{provider_id:'a',hasKey:!!secret}], 'request must stay bound to original provider');
 if(switchProvider)assert.equal(status(),selectedStatus,'late key response must not overwrite currently selected provider status');
 for(const pid of ['a','b']){
  field('供应商').value=pid;field('供应商').onchange();
  assert.equal(status().includes('服务器已有密钥'),keys[pid],`UI key boolean must agree with server for ${pid}`);
 }
 assert.equal(node.widgets[0].value,'auto');
}
await trial({switchProvider:true});
await trial({switchProvider:true,secret:'',initialKeys:{a:true,b:true}});
await trial();
await trial({secret:'',initialKeys:{a:true,b:true}});
await trial({secret:'',initialKeys:{a:true,b:false},effectiveEnvironment:true});
await trial({secret:'',initialKeys:{a:true,b:false},effectiveEnvironment:true,switchProvider:true});
console.log('PASS round3 frontend key response identity: save/delete x switched/unchanged');
