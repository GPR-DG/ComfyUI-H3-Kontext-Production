"""Independent review: real Engine/Protocol/Bridge; synthetic peer replies only."""
import base64,copy,gzip,importlib.util,json,os,sys,tempfile,types,unittest,zlib
from pathlib import Path
from unittest.mock import patch
import httpx
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol,APIError
import test_engine as engine_fixtures
import test_round4_credentials as credential_fixtures
FA,FB=credential_fixtures.FA,credential_fixtures.FB
from mock_api import PNG_BYTES
ROOT=Path(__file__).resolve().parents[1]
class ReviewTests(unittest.TestCase):
 def fixture(self):
  f=engine_fixtures.EngineTests();f.setUp();self.addCleanup(f.doCleanups);return f
 def plugin(self,store):
  spec=importlib.util.spec_from_file_location('independent017_plugin',ROOT/'__init__.py',submodule_search_locations=[str(ROOT)])
  p=importlib.util.module_from_spec(spec);sys.modules[spec.name]=p;spec.loader.exec_module(p)
  ad=sys.modules[spec.name+'.nodes'];ad.STORE=store
  bn=sys.modules[spec.name+'.h3_background_bridge.nodes']
  context=patch.object(bn,'registry',return_value=p.NODE_CLASS_MAPPINGS);context.start();self.addCleanup(context.stop)
  return ad,bn
 def test_unused_backup_changes_do_not_repost_or_enter_prompt(self):
  f=self.fixture();ad,bn=self.plugin(f.store);e=f.engine()
  g={'api':{'class_type':'H3ImageEdit','inputs':{'provider':'auto','model_alias':'background-edit','parameters':'{}'}},'z':{'class_type':'KSampler','inputs':{'seed':1}}}
  run=lambda:bn.H3A2Recipe().run(.86,'remove people','api','z',0,g)
  a=run();x=e.edit([PNG_BYTES],prompt=a[1],request_nonce=a[2]);self.assertEqual(x['report']['status'],'success')
  cfg=f.store.load();cfg['providers'][1]['models']['background-edit']['id']='unused-model-changed';cfg['providers'][1]['key_env']='UNUSED_SYNTHETIC_KEY';f.store.save(cfg);f.store.save_key('p1','BACKUP-FAKE')
  b=run();self.assertEqual(a,b);self.assertEqual(b[1],'remove people')
  y=e.edit([PNG_BYTES],prompt=b[1],request_nonce=b[2]);self.assertTrue(y['report']['cached']);self.assertEqual(len(f.api.calls(method='POST')),1)
  self.assertIn(b'remove people',f.api.calls(method='POST')[0]['body']);self.assertNotIn(b'Processing configuration',f.api.calls(method='POST')[0]['body'])
 def test_recipe_active_model_changes_nonce_but_key_rotation_does_not(self):
  f=self.fixture();ad,bn=self.plugin(f.store);g={'api':{'inputs':{}},'z':{'class_type':'KSampler','inputs':{'seed':1}}};run=lambda:bn.H3A2Recipe().run(.86,'remove','api','z',0,g)
  a=run();os.environ['H3_MOCK_KEY']='DIFFERENT-FAKE';b=run();self.assertNotEqual(a[0],b[0]);self.assertEqual(a[1:],b[1:])
  cfg=f.store.load();cfg['providers'][0]['models']['background-edit']['id']='new-active-model';f.store.save(cfg);c=run();self.assertNotEqual(b[2],c[2]);self.assertEqual(c[1],'remove')
 def test_key_account_switch_blocks_completed_private_cache_without_post(self):
  f=self.fixture();e=f.engine();a=e.edit([PNG_BYTES],prompt='same');self.assertEqual(a['report']['status'],'success')
  os.environ['H3_MOCK_KEY']='SECOND-ACCOUNT-FAKE';b=e.edit([PNG_BYTES],prompt='same');self.assertEqual(b['images'],[]);self.assertEqual(b['report']['error'],'credential_changed_no_resubmit');self.assertEqual(len(f.api.calls(method='POST')),1)
  os.environ['H3_MOCK_KEY']='H3_FAKE_SECRET';self.assertTrue(e.edit([PNG_BYTES],prompt='same')['report']['cached'])
 def test_two_config_stores_shared_runtime_do_not_leak_results(self):
  f=self.fixture();e=f.engine();e.edit([PNG_BYTES],prompt='same')
  from h3_adapter.config import ConfigStore
  other=ConfigStore(f.root/'other'/'providers.json');cfg=copy.deepcopy(f.config)
  for p in cfg['providers']:p['key_env']=''
  other.save(cfg);other.save_key('p0','OTHER-ACCOUNT-FAKE')
  b=Engine(other,f.root/'runtime').edit([PNG_BYTES],prompt='same');self.assertEqual(b['images'],[]);self.assertEqual(b['report']['status'],'blocked');self.assertEqual(len(f.api.calls(method='POST')),1)
 def test_missing_provider_in_other_config_cannot_consume_completed_result(self):
  f=self.fixture();e=f.engine();e.edit([PNG_BYTES],prompt='private')
  from h3_adapter.config import ConfigStore
  other=ConfigStore(f.root/'foreign'/'providers.json');cfg=copy.deepcopy(f.config)
  cfg['primary']='foreign';cfg['fallbacks']=[];cfg['providers']=[cfg['providers'][0]];cfg['providers'][0]['id']='foreign';cfg['providers'][0]['key_env']=''
  other.save(cfg);other.save_key('foreign','FOREIGN-ACCOUNT-FAKE')
  with patch.dict(os.environ,{},clear=True):
   result=Engine(other,f.root/'runtime').edit([PNG_BYTES],prompt='private')
  self.assertEqual(result['images'],[]);self.assertEqual(result['report']['status'],'blocked');self.assertEqual(len(f.api.calls(method='POST')),1)
 def test_empty_corrupt_and_oversized_image_rejected_before_paid_post(self):
  import struct,binascii
  f=self.fixture();e=f.engine();oversized=bytearray(PNG_BYTES)
  oversized[16:24]=struct.pack('>II',10000,5000)
  oversized[29:33]=struct.pack('>I',binascii.crc32(oversized[12:29]) & 0xffffffff)
  for content in (b'',b'not an image',bytes(oversized)):
   with self.subTest(length=len(content)):
    result=e.edit([content],prompt='invalid input')
    self.assertEqual(result['report']['status'],'failed');self.assertEqual(result['images'],[])
  self.assertEqual(len(f.api.calls(method='POST')),0)
 def credentials(self,account=None):
  f=credential_fixtures.CredentialsTests();f.setUp();self.addCleanup(f.doCleanups)
  if account:
   cfg=f.store.load();cfg['providers'][0]['account_id']=account;f.store.save(cfg)
  return f
 def test_unproven_same_site_rotation_blocks_query_and_restore_recovers(self):
  f=self.credentials();f.accepted();f.store.save_key('slot',FB);r=f.edit();self.assertEqual(r['report']['error'],'credential_changed_no_resubmit');self.assertEqual(f.calls,[])
  f.store.save_key('slot',FA);self.assertEqual(f.edit()['report']['status'],'success');self.assertEqual([x['method'] for x in f.calls],['GET'])
 def test_declared_same_account_rotation_recovers_get_only(self):
  f=self.credentials('same-account');f.accepted();f.store.save_key('slot',FB);r=f.edit();self.assertEqual(r['report']['status'],'success');self.assertEqual([x['method'] for x in f.calls],['GET']);self.assertEqual(f.calls[0]['key'],'Bearer '+FB)
 def test_different_declared_account_same_url_cannot_query_old_task(self):
  f=self.credentials('account-A');f.accepted();cfg=f.store.load();cfg['providers'][0]['account_id']='account-B';f.store.save(cfg);f.store.save_key('slot',FB)
  self.assertEqual(f.edit()['report']['error'],'credential_changed_no_resubmit');self.assertEqual(f.calls,[])
 def test_legacy_bridge_identity_cannot_silently_submit_new_prompt(self):
  f=self.fixture();e=f.engine();r=e.edit([PNG_BYTES],prompt='legacy prompt');rid=r['report']['request_id'];row=e.journal.get(rid);snap=json.loads(row['snapshot']);snap.pop('identity_version')
  with e.journal.connection() as db:db.execute('UPDATE requests SET snapshot=? WHERE request_id=?',(json.dumps(snap),rid))
  self.assertTrue(e.edit([PNG_BYTES],prompt='legacy prompt')['report']['cached'])
  b=e.edit([PNG_BYTES],prompt='natural new prompt');self.assertEqual(b['report']['error'],'legacy_journal_new_request_requires_review');self.assertEqual(len(f.api.calls(method='POST')),1)
 def test_compression_boundaries_and_legal_streams(self):
  class Stream(httpx.SyncByteStream):
   def __init__(self,data):self.data=data
   def __iter__(self):
    for i in range(0,len(self.data),7):yield self.data[i:i+7]
  for kind,encode in [('gzip',gzip.compress),('deflate',zlib.compress),('deflate',lambda b:zlib.compress(b)[2:-4])]:
   for data,limit,ok in [(b'legal reply',64,True),(b'x'*1000000,1024,False)]:
    raw=encode(data);p=Protocol({'base_url':'https://synthetic.invalid','max_response_bytes':limit},'',httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Encoding':kind},stream=Stream(raw))))
    try:
     if ok:self.assertEqual(p._request('GET',p.base_url,2).content,data)
     else:
      with self.assertRaises(APIError) as caught:p._request('GET',p.base_url,2)
      self.assertEqual(caught.exception.code,'response_too_large')
    finally:p.close()
 def test_truncated_and_unsupported_compression_is_not_success(self):
  class Stream(httpx.SyncByteStream):
   def __iter__(self):yield gzip.compress(b'hello')[:-3]
  for kind in ['gzip','br']:
   p=Protocol({'base_url':'https://synthetic.invalid'},'',httpx.MockTransport(lambda r:httpx.Response(200,headers={'Content-Encoding':kind},stream=Stream())))
   try:
    with self.assertRaises(APIError):p._request('GET',p.base_url,2)
   finally:p.close()
if __name__=='__main__':unittest.main()
