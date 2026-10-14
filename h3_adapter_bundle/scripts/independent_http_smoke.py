"""New independent TCP/HTTP smoke, not a replay of repository test fixtures."""
import argparse, base64, copy, hashlib, io, json, os, socket, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from PIL import Image

parser=argparse.ArgumentParser(); parser.add_argument('--source',required=True); parser.add_argument('--output',required=True)
args=parser.parse_args(); sys.path.insert(0,args.source)
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
import httpx

def picture(size=(8,6),mode='RGB',fmt='PNG'):
    s=io.BytesIO(); Image.new(mode,size,'blue' if mode!='L' else 255).save(s,fmt); return s.getvalue()
PNG=picture(); MASK=picture(mode='RGBA'); records=[]
class Peer:
    def __init__(self):
        self.calls=[]; self.plans={}; self.complete=False; self.result=PNG
        peer=self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self,*a):pass
            def answer(self):
                data=self.rfile.read(int(self.headers.get('Content-Length',0))); pid=self.path.strip('/').split('/')[0]
                call={'method':self.command,'path':self.path,'provider':pid,'key':self.headers.get('Authorization'),'fields':{},'images':[]}
                if data and 'multipart/form-data' in self.headers.get('Content-Type',''):
                    m=BytesParser(policy=default).parsebytes(('Content-Type: '+self.headers['Content-Type']+'\r\nMIME-Version: 1.0\r\n\r\n').encode()+data)
                    for part in m.iter_parts():
                        name=part.get_param('name',header='Content-Disposition'); content=part.get_payload(decode=True)
                        if part.get_filename():
                            with Image.open(io.BytesIO(content)) as image:
                                call['images'].append({'field':name,'size':list(image.size),'mode':image.mode,'alpha':list(image.getchannel('A').getextrema()) if 'A' in image.getbands() else None,'sha256':hashlib.sha256(content).hexdigest()})
                        else:call['fields'][name]=content.decode()
                elif data:
                    call['json']=json.loads(data)
                peer.calls.append(call)
                plan=peer.plans.get(pid,{})
                if plan.get('delay'):time.sleep(plan['delay'])
                status=plan.get('status',200); mode=plan.get('mode','normal')
                if self.command=='GET' and self.path.endswith('/models'):
                    payload={'data':[{'id':'remote-edit'},{'id':'remote-edit'},{'id':'second-model'}]}
                elif self.command=='GET':
                    payload={'status':plan.get('poll_status','succeeded' if peer.complete else 'pending'),'data':[{'b64_json':base64.b64encode(peer.result).decode()}]}
                elif mode=='async':payload={'id':'accepted-id'}
                else:payload={'data':[{'b64_json':base64.b64encode(b'not-image' if mode=='bad_image' else peer.result).decode()}]}
                if mode=='two_results':payload['data'].append({'b64_json':base64.b64encode(picture((3,3))).decode()})
                if mode=='missing_result':payload={'ok':True}
                content=b'not-json' if mode=='bad_json' else json.dumps(payload).encode()
                self.send_response(status); self.send_header('Content-Type','application/json')
                self.send_header('Content-Length',str(len(content)+50 if mode=='truncated' else len(content))); self.end_headers()
                try:
                    self.wfile.write(content[:5] if mode=='truncated' else content); self.wfile.flush()
                    if mode=='truncated':self.connection.shutdown(socket.SHUT_WR)
                except OSError:pass
            do_POST=answer; do_GET=answer
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=lambda:self.server.serve_forever(poll_interval=.01),daemon=True);self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
    def close(self):self.server.shutdown();self.server.server_close();self.thread.join()
class F:
    def __enter__(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.peer=Peer()
        ps=[]
        for i,pid in enumerate('abcd'):
            ps.append({'id':pid,'base_url':self.peer.url+'/'+pid+'/v1','key_env':'','enabled':True,'priority':i+1,'allow_insecure_localhost':True,'protocol':'openai_images','edit_path':'/edit','discovery':{'path':'/models'},'models':{'edit':{'id':'actual-'+pid,'task':'image_edit','supports_mask':True,'max_images':2,'price_upper_bound':.1,'allowed_params':['quality'],'defaults':{'quality':'standard'}}}})
        self.cfg={'version':1,'primary':'a','fallbacks':['b','c','d'],'auto_failover':True,'currency':'USD','timeout_seconds':3,'cooldown_seconds':2,'providers':ps}
        self.store=ConfigStore(self.root/'providers.json');self.save()
        for pid in 'abcd':self.store.save_key(pid,'SMOKE-FAKE-'+pid)
        self.engine=Engine(self.store,self.root/'runtime');return self
    def __exit__(self,*a):self.peer.close();self.temp.cleanup()
    def save(self):self.store.save(self.cfg)
    def edit(self,nonce=0,**kw):
        e=kw.pop('engine',self.engine)
        return e.edit(kw.pop('images',[PNG]),mask=kw.pop('mask',None),prompt='independent clean background',model_alias='edit',request_nonce=nonce,**kw)
    def posts(self):return [c for c in self.peer.calls if c['method']=='POST']
    def emit(self,name,results,**extra):
        for c in self.peer.calls:
            if c['provider'] in 'abcd':assert c['key']=='Bearer SMOKE-FAKE-'+c['provider'],c
        with self.engine.journal.connection() as db:
            rows=[dict(r) for r in db.execute('SELECT request_id,state,provider,model,task_id,reserved_cost,currency FROM requests')]
        item={'case':name,'reports':[r['report'] for r in results],'http_calls':self.peer.calls,'journal':rows,**extra}
        records.append(item);print(name+': PASS '+json.dumps({'posts':len(self.posts()),'statuses':[r['report']['status'] for r in results]}),flush=True)

def run():
    with F() as f:
        r=f.edit(mask=MASK,images=[PNG,picture((4,4))]);assert r['report']['status']=='success'
        c=f.posts()[0];assert c['fields']=={'quality':'standard','model':'actual-a','prompt':'independent clean background'}
        assert [i['field'] for i in c['images']]==['image','image','mask'];assert len(r['images'])==1
        f.emit('multipart_model_prompt_two_images_mask',[r])
    with F() as f:
        f.peer.result=picture((11,7),fmt='JPEG');r=f.edit();assert Image.open(io.BytesIO(r['images'][0])).size==(11,7)
        f.emit('output_jpeg_and_changed_dimensions',[r],output_size=[11,7])
    with F() as f:
        f.peer.plans['a']={'mode':'two_results'};r=f.edit();assert len(r['images'])==1
        f.emit('explicit_default_first_result_contract',[r],remote_count=2,adapter_count=1)
    for statuses,name,expected in (({'a':401},'auth_failure_backup','b'),({'a':401,'b':403,'c':404},'three_rejected_then_fourth','d'),({'a':401,'b':403,'c':404,'d':401},'all_four_rejected',None)):
        with F() as f:
            f.peer.plans={p:{'status':s} for p,s in statuses.items()};r=f.edit()
            assert r['report']['status']==('success' if expected else 'no_provider');assert r['report']['provider']==(expected or 'd')
            f.emit(name,[r])
    for mode in ('bad_json','truncated','missing_result','bad_image'):
        with F() as f:
            f.peer.plans['a']={'mode':mode};r=f.edit();again=f.edit();assert len(f.posts())==1
            assert r['report']['status'] in ('uncertain','awaiting_result');assert again['report']['status']==r['report']['status']
            assert f.engine.journal.get(r['report']['request_id'])['reserved_cost']==.1
            f.emit('accepted_'+mode+'_no_resubmit',[r,again])
    with F() as f:
        f.peer.plans['a']={'delay':.3};r=f.edit(timeout_seconds=.08);again=f.edit();assert r['report']['status']=='uncertain';assert len(f.posts())==1
        f.emit('accepted_response_timeout_no_backup',[r,again])
    with F() as f:
        for m in (f.cfg['providers'][0]['models']['edit'],):m['defaults']={}
        f.save();r=f.edit(params={'quality':float('nan')});assert not f.posts();assert f.engine.journal.available('a')
        f.emit('invalid_json_parameters_before_http',[r])
    with F() as f:
        f.cfg['providers'][0]['request']={'image_field':42};f.save();r=f.edit();assert r['report']['provider']=='b';assert [c['provider'] for c in f.posts()]==['b'];assert f.engine.journal.available('a')
        f.emit('invalid_multipart_field_no_primary_http_or_cooldown',[r])
    with F() as f:
        p=f.cfg['providers'][0];p['protocol']='json_template';p['request']={'body':{'image':'{image_base64}','model':'constant-model','prompt':'constant-prompt'}};f.save();r=f.edit()
        assert f.posts()[0]['json']['model']=='constant-model';assert 'json_template_unmapped_prompt' in r['report']['warnings'];assert r['report']['model']=='actual-a'
        f.emit('legal_constant_json_template_with_warnings',[r])
    with F() as f:
        p=f.cfg['providers'][0];p['protocol']='json_template';p['request']={'body':{'prompt':'{prompt}'}};f.save();r=f.edit();assert r['report']['provider']=='b';assert len(f.posts())==1;assert f.engine.journal.available('a')
        f.emit('unmapped_image_local_error_keeps_primary_healthy',[r])
    with F() as f:
        dead=socket.socket();dead.bind(('127.0.0.1',0));port=dead.getsockname()[1];dead.close()
        f.cfg['providers'][0]['base_url']=f'http://127.0.0.1:{port}/a/v1';f.save();r=f.edit()
        assert r['report']['provider']=='b';assert len(f.posts())==1;assert not f.engine.journal.available('a')
        f.emit('actual_tcp_connection_refused_safe_backup',[r])
    with F() as f:
        def injected(p,key):
            if p['id']=='a':
                def fail(req):raise httpx.ConnectTimeout('controlled unsent connect timeout')
                return Protocol(p,key,transport=httpx.MockTransport(fail))
            return Protocol(p,key)
        e=Engine(f.store,f.root/'runtime',injected);r=f.edit(engine=e);assert r['report']['provider']=='b';assert len(f.posts())==1
        f.emit('fault_injected_connect_timeout_not_real_network_timeout',[r])
    with F() as f:
        p=f.cfg['providers'][0];p['async']={'task_id_path':'id','poll_path':'/tasks/{task_id}','status_path':'status','max_polls':1,'poll_interval':0};f.save();f.peer.plans['a']={'mode':'async'}
        first=f.edit();assert first['report']['status']=='awaiting_result';f.peer.complete=True
        p['enabled']=False;p['base_url']=f.peer.url+'/wrong/v1';p['models']['edit']['id']='replacement';f.cfg['primary']='b';f.cfg['fallbacks']=['a','c','d'];f.save()
        restart=Engine(f.store,f.root/'runtime');second=f.edit(engine=restart);cached=f.edit(engine=restart);new=f.edit(1,engine=restart)
        assert second['report']['status']=='success';assert second['report']['model']=='actual-a';assert cached['report']['cached'];assert new['report']['provider']=='b';assert len(f.posts())==2
        f.emit('real_async_restart_snapshot_cache_new_nonce',[first,second,cached,new])
    with F() as f:
        p=f.cfg['providers'][0];p['async']={'task_id_path':'id','poll_path':'/tasks/{task_id}','status_path':'status','max_polls':1,'poll_interval':0};f.save();f.peer.plans['a']={'mode':'async'}
        first=f.edit();p['base_url']=f.peer.url+'/wrong/v1';f.save();f.store.save_key('a','SMOKE-FAKE-new-key');before=len(f.peer.calls);blocked=f.edit()
        assert blocked['report']['error']=='credential_changed_no_resubmit';assert len(f.peer.calls)==before;assert len(f.posts())==1
        f.emit('changed_key_and_endpoint_block_old_poll_no_resubmit',[first,blocked])
    for same in (True,False):
        with F() as f:
            f.cfg['max_total_cost']=.1;f.save();f.peer.plans['a']={'delay':.08};barrier=threading.Barrier(6)
            def job(i):
                e=Engine(f.store,f.root/'runtime');barrier.wait();return f.edit(99 if same else i,engine=e)
            with ThreadPoolExecutor(max_workers=6) as pool:rs=list(pool.map(job,range(6)))
            assert len(f.posts())==1;assert sum(r['report']['status']=='success' for r in rs)>=1
            with f.engine.journal.connection() as db:assert abs(db.execute('SELECT SUM(reserved_cost) FROM requests').fetchone()[0]-.1)<1e-9
            f.emit('parallel_same_nonce' if same else 'parallel_budget_reservation',rs)
    with F() as f:
        f.peer.plans['a']={'status':503};first=f.edit();again=f.edit()
        assert first['report']['status']=='uncertain' and again['report']['status']=='uncertain';assert len(f.posts())==1
        f.emit('actual_http_503_unknown_acceptance_no_backup',[first,again])
    for remote,expected in [('vendor_new_unrecognized_status','awaiting_result'),('failed','failed')]:
        with F() as f:
            p=f.cfg['providers'][0];p['async']={'task_id_path':'id','poll_path':'/tasks/{task_id}','status_path':'status','max_polls':1,'poll_interval':0};f.save();f.peer.plans['a']={'mode':'async','poll_status':remote}
            first=f.edit();again=f.edit();assert first['report']['status']==expected and again['report']['status']==expected;assert len(f.posts())==1
            f.emit('async_unknown_status_pending' if expected=='awaiting_result' else 'async_terminal_failed_no_resubmit',[first,again])
    with F() as f:
        f.cfg['providers'][0]['models']['edit']['supports_mask']=False;f.save();r=f.edit(mask=MASK)
        assert r['report']['provider']=='b' and [c['provider'] for c in f.posts()]==['b'];assert f.engine.journal.available('a')
        f.emit('mask_capability_exclusion_without_cooling',[r])
    with F() as f:
        f.cfg['providers'][0]['models']['edit']['mask_encoding']='grayscale_white_edit';f.save();r=f.edit(mask=MASK)
        assert r['report']['status']=='success';file=f.posts()[0]['images'][1];assert file['mode']=='L'
        expected=io.BytesIO();Image.new('L',(8,6),0).save(expected,'PNG');assert file['sha256']==hashlib.sha256(expected.getvalue()).hexdigest()
        f.emit('actual_alpha_to_grayscale_mask_mapping',[r])
    with F() as f:
        p=f.cfg['providers'][0];client=Protocol(p,f.store.credential(p))
        try:ids=client.discover()
        finally:client.close()
        assert ids==['remote-edit','second-model'];r=f.edit();f.cfg['providers'][0]['models']['edit']['id']='changed-model';f.save();cached=f.edit();new=f.edit(1)
        assert cached['report']['cached'];assert cached['report']['model']=='actual-a';assert new['report']['model']=='changed-model';assert len(f.posts())==2
        f.emit('actual_model_discovery_and_nonce_paid_intent',[r,cached,new],discovered=ids)

out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True)
completed=False
try:
    run();completed=True
finally:out.write_text(json.dumps({'source':str(Path(args.source).resolve()),'cases':records,'all_completed':completed},ensure_ascii=False,indent=2),encoding='utf-8')
print('Completed independent cases:',len(records))