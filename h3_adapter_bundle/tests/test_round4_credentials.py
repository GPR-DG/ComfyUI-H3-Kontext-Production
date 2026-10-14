"""Round-four credential identity regressions: fake keys, local MockTransport only."""
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import patch
import httpx
from PIL import Image
from aiohttp import web
from h3_adapter.config import ConfigStore, ConfigError, atomic_json, settings_lock
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
from h3_adapter.routes import register_routes

FA, FB = 'ROUND4-FAKE-A-KEY', 'ROUND4-FAKE-B-KEY'

def provider(pid='slot', url='https://merchant-a.example.invalid/v1', env=''):
    return {'id': pid, 'base_url': url, 'key_env': env, 'enabled': True,
            'protocol': 'openai_images', 'edit_path': '/images/edits', 'discovery': None,
            'models': {'edit': {'id': 'fake-edit', 'task': 'image_edit', 'price_upper_bound': 0.1}},
            'async': {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}', 'status_path': 'status',
                      'poll_interval': 0, 'max_polls': 1}}

def config(providers=None):
    return {'version': 1, 'primary': 'slot', 'fallbacks': [], 'currency': 'USD',
            'timeout_seconds': 3, 'providers': providers or [provider()]}

class Request:
    headers = {}; remote = '127.0.0.1'; host = '127.0.0.1:8188'; scheme = 'http'; content_type = 'application/json'
    def __init__(self, payload): self.payload = payload; self.content_length = len(json.dumps(payload).encode())
    async def json(self): return self.payload

class CredentialsTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        self.temp = tempfile.TemporaryDirectory(dir=work); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = ConfigStore(self.root / 'providers.json')
        self.store.save(config()); self.store.save_key('slot', FA)
        stream = io.BytesIO(); Image.new('RGB', (2, 2), 'blue').save(stream, 'PNG'); self.png = stream.getvalue()
        self.calls = []; self.complete = False
        def handler(request):
            self.calls.append({'method': request.method, 'url': str(request.url), 'key': request.headers.get('Authorization')})
            return httpx.Response(200, json={'id': 'task-A'} if request.method == 'POST' else {'status': 'succeeded' if self.complete else 'pending', 'data': [{'b64_json': __import__('base64').b64encode(self.png).decode()}]})
        self.factory = lambda p, key: Protocol(p, key, transport=httpx.MockTransport(handler))
        self.engine = Engine(self.store, self.root / 'runtime', self.factory)

    def edit(self): return self.engine.edit([self.png], prompt='fake audit', model_alias='edit', timeout_seconds=3)

    def accepted(self, legacy=False):
        result = self.edit(); self.assertEqual(result['report']['status'], 'awaiting_result')
        self.rid = result['report']['request_id']
        if legacy:
            row = self.engine.journal.get(self.rid); snapshot = json.loads(row['snapshot']); snapshot.pop('credential_fingerprint', None)
            with self.engine.journal.connection() as db: db.execute('UPDATE requests SET snapshot=? WHERE request_id=?', (json.dumps(snapshot), self.rid))
        self.calls.clear(); self.complete = True

    def replace(self, key=FB):
        cfg = self.store.load(); cfg['providers'][0]['base_url'] = 'https://merchant-b.example.invalid/v1'; self.store.save(cfg); self.store.save_key('slot', key)

    def remove(self):
        cfg = config([provider('keeper', 'https://keeper.example.invalid/v1')]); cfg['primary'] = 'keeper'; self.store.save(cfg)

    def assert_blocked_recovery(self):
        result = self.edit(); self.assertEqual(result['report']['status'], 'awaiting_result')
        self.assertEqual(result['report']['error'], 'credential_changed_no_resubmit')
        self.assertEqual(self.calls, [], 'Do not send a new merchant credential to a saved old endpoint')
        row = self.engine.journal.get(self.rid); self.assertEqual(row['state'], 'accepted'); self.assertEqual(row['reserved_cost'], 0.1)

    def test_changed_merchant_and_private_key_blocks_recovery(self):
        self.accepted(); self.replace(); self.assert_blocked_recovery()

    def test_saved_key_allows_old_url_after_address_change(self):
        self.accepted(); self.replace(FA); result = self.edit()
        self.assertEqual(result['report']['status'], 'success'); self.assertEqual(len(self.calls), 1)
        self.assertTrue(self.calls[0]['url'].startswith('https://merchant-a.')); self.assertEqual(self.calls[0]['key'], 'Bearer ' + FA)

    def test_same_identity_key_rotation_is_allowed(self):
        cfg=self.store.load(); cfg['providers'][0]['account_id']='declared-same-account'; self.store.save(cfg)
        self.accepted(); self.store.save_key('slot', FB); result = self.edit()
        self.assertEqual(result['report']['status'], 'success'); self.assertEqual(self.calls[0]['key'], 'Bearer ' + FB)

    def test_legacy_same_identity_rotation_is_allowed(self):
        cfg=self.store.load(); cfg['providers'][0]['account_id']='declared-same-account'; self.store.save(cfg)
        self.accepted(legacy=True); self.store.save_key('slot', FB); self.assertEqual(self.edit()['report']['status'], 'success')

    def test_legacy_changed_identity_cannot_prove_same_key(self):
        self.accepted(legacy=True); self.replace(FA); self.assert_blocked_recovery()

    def test_deleted_provider_with_matching_saved_key_recovers(self):
        self.accepted(); self.remove(); self.assertEqual(self.edit()['report']['status'], 'success')
        self.assertEqual(self.calls[0]['key'], 'Bearer ' + FA)

    def test_repurposed_then_deleted_provider_does_not_bypass_hash(self):
        self.accepted(); self.replace(); self.remove(); self.assert_blocked_recovery()

    def test_legacy_deleted_provider_is_conservatively_blocked(self):
        self.accepted(legacy=True); self.remove(); self.assert_blocked_recovery()

    def test_missing_old_env_does_not_fallback_to_new_private_key(self):
        cfg = self.store.load(); cfg['providers'][0]['key_env'] = 'ROUND4_FAKE_A_ENV'; self.store.save(cfg)
        with patch.dict(os.environ, {'ROUND4_FAKE_A_ENV': FA}): self.accepted()
        self.replace(); self.assert_blocked_recovery()

    def test_snapshot_records_hash_not_secret(self):
        self.accepted(); snapshot = json.loads(self.engine.journal.get(self.rid)['snapshot'])
        self.assertEqual(snapshot.get('credential_fingerprint'), hashlib.sha256(FA.encode()).hexdigest())
        self.assertNotIn(FA, json.dumps(snapshot)); self.assertNotIn(FB, json.dumps(snapshot))

    def test_submit_uses_one_captured_key_not_second_mutable_lookup(self):
        count = [0]
        def key(p): count[0] += 1; return FA if count[0] == 1 else FB
        with patch.object(self.store, 'key', key): self.edit()
        self.assertEqual(self.calls[0]['key'], 'Bearer ' + FA)

    def test_changed_config_between_load_and_credential_never_sends(self):
        load = self.store.load; once = [True]
        def stale_load():
            value = load()
            if once[0]:
                once[0] = False; self.replace()
            return value
        with patch.object(self.store, 'load', stale_load): self.edit()
        self.assertEqual(self.calls, [])

    def test_key_membership_is_checked_inside_settings_lock(self):
        @contextmanager
        def changed_before_lock(path):
            cfg = config([provider('keeper')]); cfg['primary'] = 'keeper'; atomic_json(self.store.path, cfg)
            with settings_lock(path): yield
        with patch('h3_adapter.config.settings_lock', changed_before_lock):
            with self.assertRaises(ConfigError): self.store.save_key('slot', FB)
        self.assertEqual(self.store.key(provider()), FA)

class CredentialRoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_cannot_pair_stale_endpoint_with_new_key(self):
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        with tempfile.TemporaryDirectory(dir=work) as folder, patch.dict(os.environ, {'H3_ADAPTER_MANAGEMENT_TOKEN': '', 'H3_ADAPTER_DISABLE_MANAGEMENT': ''}):
            store = ConfigStore(Path(folder) / 'providers.json'); cfg = config(); cfg['providers'][0]['discovery'] = {'path': '/models'}; store.save(cfg); store.save_key('slot', FA)
            routes = web.RouteTableDef(); register_routes(routes, store); handler = next(r.handler for r in routes if r.method == 'POST' and r.path == '/h3-adapter/models')
            original_load = store.load; once = [True]; calls = []
            def stale_load():
                value = original_load()
                if once[0]:
                    once[0] = False; changed = copy.deepcopy(value); changed['providers'][0]['base_url'] = 'https://merchant-b.example.invalid/v1'; store.save(changed); store.save_key('slot', FB)
                return value
            def transport(request):
                calls.append((str(request.url), request.headers.get('Authorization'))); return httpx.Response(200, json={'data': [{'id': 'fake-edit'}]})
            factory = lambda p, key: Protocol(p, key, transport=httpx.MockTransport(transport))
            with patch.object(store, 'load', stale_load), patch('h3_adapter.protocol.Protocol', factory):
                response = await handler(Request({'provider_id': 'slot'}))
            self.assertEqual(response.status, 400); self.assertEqual(calls, [])

    async def test_stale_key_save_revision_returns_409_without_overwrite(self):
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        with tempfile.TemporaryDirectory(dir=work) as folder, patch.dict(os.environ, {'H3_ADAPTER_MANAGEMENT_TOKEN': '', 'H3_ADAPTER_DISABLE_MANAGEMENT': ''}):
            store = ConfigStore(Path(folder) / 'providers.json'); store.save(config()); store.save_key('slot', FA)
            revision = store.public()['revision']; cfg = store.load(); cfg['providers'][0]['base_url'] = 'https://merchant-b.example.invalid/v1'; store.save(cfg); store.save_key('slot', FB)
            routes = web.RouteTableDef(); register_routes(routes, store); handler = next(r.handler for r in routes if r.method == 'POST' and r.path == '/h3-adapter/key')
            response = await handler(Request({'provider_id': 'slot', 'key': FA, 'expected_revision': revision}))
            self.assertEqual(response.status, 409); self.assertEqual(store.key(provider()), FB)
            # Old direct callers deliberately write by current ID; retain the API signature.
            response = await handler(Request({'provider_id': 'slot', 'key': FB})); self.assertEqual(response.status, 200)

if __name__ == '__main__': unittest.main()
