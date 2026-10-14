"""Submission/discovery must reject a stale configuration, including delete/recreate ABA."""
import base64
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import httpx
from aiohttp import web
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
from mock_api import PNG_BYTES
from test_round4_credentials import Request

class FinalIdentityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2] / 'work' / 'tmp')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = ConfigStore(self.root / 'providers.json')
        p = {'id':'slot','enabled':True,'base_url':'https://synthetic.invalid/v1','key_env':'',
             'protocol':'openai_images','edit_path':'/edit','discovery':{'path':'/models'},
             'models':{'edit':{'id':'model-old','task':'image_edit','price_upper_bound':0.1}}}
        self.cfg = {'version':1,'primary':'slot','fallbacks':[], 'providers':[p,dict(copy.deepcopy(p),id='keeper')]}
        self.store.save(self.cfg)
        self.store.save_key('slot','FINAL-SYNTHETIC-OLD')
        self.calls=[]
        def handler(request):
            self.calls.append((request.method, request.headers.get('Authorization'),request.content))
            return httpx.Response(200,json={'data':[{'id':'model-new','b64_json':base64.b64encode(PNG_BYTES).decode()}]})
        self.factory=lambda p,k:Protocol(p,k,httpx.MockTransport(handler))

    def test_snapshot_revision_is_not_serialized_and_dict_contract_is_preserved(self):
        snapshot=self.store.load()
        self.assertIsInstance(snapshot,dict)
        self.assertEqual(json.loads(json.dumps(snapshot)),self.cfg)
        self.assertEqual(snapshot.revision,self.store.public()['revision'])

    def stale_load(self, mode):
        original=self.store.load
        once=[True]
        def load():
            value=original()
            if once[0]:
                once[0]=False
                if mode=='recreate':
                    removed=copy.deepcopy(self.cfg)
                    removed['providers']=removed['providers'][1:]
                    removed['primary']='keeper'
                    self.store.save(removed)
                    self.store.save(self.cfg)
                else:
                    changed=copy.deepcopy(self.cfg)
                    changed['providers'][0]['models']['edit']['id']='model-new'
                    self.store.save(changed)
                self.store.save_key('slot','FINAL-SYNTHETIC-NEW')
            return value
        return load

    def test_old_loaded_request_cannot_bind_recreated_id_to_new_key(self):
        engine=Engine(self.store,self.root/'runtime',self.factory)
        with patch.object(self.store,'load',self.stale_load('recreate')):
            result=engine.edit([PNG_BYTES],prompt='synthetic edit',model_alias='edit')
        self.assertEqual(self.calls,[], 'Stale request sent using the recreated provider credential')
        self.assertEqual(result['report']['status'],'failed')

    def test_old_model_snapshot_cannot_borrow_new_configuration_key(self):
        engine=Engine(self.store,self.root/'runtime',self.factory)
        with patch.object(self.store,'load',self.stale_load('model')):
            result=engine.edit([PNG_BYTES],prompt='synthetic edit',model_alias='edit')
        self.assertEqual(self.calls,[], 'Old model submitted after mapping and key changed')
        self.assertEqual(result['report']['status'],'failed')

class FinalDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    setUp = FinalIdentityTests.setUp
    stale_load = FinalIdentityTests.stale_load
    async def test_discovery_cannot_bind_recreated_id_to_new_key(self):
        from h3_adapter.routes import register_routes
        routes=web.RouteTableDef()
        register_routes(routes,self.store)
        handler=next(r.handler for r in routes if r.method=='POST' and r.path=='/h3-adapter/models')
        with patch.object(self.store,'load',self.stale_load('recreate')), patch('h3_adapter.protocol.Protocol',self.factory), patch.dict('os.environ',{'H3_ADAPTER_MANAGEMENT_TOKEN':'','H3_ADAPTER_DISABLE_MANAGEMENT':''}):
            response=await handler(Request({'provider_id':'slot'}))
        self.assertEqual(self.calls,[], 'Stale discovery sent with recreated identity')
        self.assertEqual(response.status,400)

class FinalRecoveryGenerationTests(unittest.TestCase):
    def test_recreated_environment_identity_cannot_recover_using_new_key(self):
        from test_round4_credentials import CredentialsTests, config, provider, FA, FB
        fixture=CredentialsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cfg=fixture.store.load()
        cfg['providers'][0]['key_env']='FINAL_SYNTHETIC_ENV'
        fixture.store.save(cfg)
        fixture.store.save_key('slot','')
        with patch.dict('os.environ', {'FINAL_SYNTHETIC_ENV':FA}):
            fixture.accepted()
        fixture.remove()
        fixture.store.save(cfg)
        with patch.dict('os.environ', {'FINAL_SYNTHETIC_ENV':FB}):
            fixture.assert_blocked_recovery()

    def test_task_submitted_after_recreation_still_allows_same_identity_rotation(self):
        from test_round4_credentials import CredentialsTests, config, provider, FA, FB
        fixture=CredentialsTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        cfg=fixture.store.load()
        cfg['providers'][0]['account_id']='declared-same-account'
        fixture.remove()
        fixture.store.save(cfg)
        fixture.store.save_key('slot',FA)
        fixture.accepted()
        fixture.store.save_key('slot',FB)
        result=fixture.edit()
        self.assertEqual(result['report']['status'],'success')
        self.assertEqual(fixture.calls[0]['key'],'Bearer '+FB)

class FinalHealthIdentityTests(unittest.TestCase):
    setUp = FinalIdentityTests.setUp
    def test_recreated_id_does_not_inherit_previous_provider_cooldown(self):
        def reject(request):
            return httpx.Response(401, json={'error':'synthetic rejection'})
        engine=Engine(self.store,self.root/'runtime',lambda p,k:Protocol(p,k,httpx.MockTransport(reject)))
        result=engine.edit([PNG_BYTES],prompt='synthetic edit',model_alias='edit')
        self.assertEqual(result['report']['status'],'no_provider')
        self.assertFalse(engine.journal.available('slot'))
        removed=copy.deepcopy(self.cfg)
        removed['providers']=removed['providers'][1:]
        removed['primary']='keeper'
        self.store.save(removed)
        self.store.save(self.cfg)
        self.store.save_key('slot','FINAL-SYNTHETIC-NEW')
        replacement=Engine(self.store,self.root/'runtime',self.factory)
        result=replacement.edit([PNG_BYTES],prompt='synthetic edit',model_alias='edit',request_nonce=1)
        self.assertEqual(result['report']['status'],'success')
        self.assertEqual(len(self.calls),1)

class FinalLedgerMigrationTests(unittest.TestCase):
    def test_old_health_schema_migrates_without_losing_claim_or_cooldown(self):
        import sqlite3
        import time
        from h3_adapter.ledger import Journal
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parents[2]/'work'/'tmp') as folder:
            db=sqlite3.connect(Path(folder)/'requests.sqlite3')
            db.execute('CREATE TABLE health (provider TEXT PRIMARY KEY, until REAL NOT NULL)')
            db.execute('INSERT INTO health VALUES (?,?)',('slot',time.time()+60))
            db.commit()
            db.close()
            journal=Journal(folder)
            self.assertFalse(journal.available('slot'))
            journal.begin('synthetic-request','synthetic-request')
            Journal(folder)
            self.assertEqual(journal.get('synthetic-request')['state'],'ready')
            journal.cooldown('slot',60,'old-identity')
            self.assertFalse(journal.available('slot','old-identity'))
            self.assertTrue(journal.available('slot','new-identity'))
