"""Effective key presence only; real ConfigStore/routes, entirely synthetic secrets."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from aiohttp import web
from h3_adapter.config import ConfigStore
from h3_adapter.routes import register_routes


class Request:
    headers = {}
    remote = '127.0.0.1'
    host = '127.0.0.1:8188'
    scheme = 'http'
    content_type = 'application/json'
    def __init__(self, data):
        self.data = data
        self.content_length = len(json.dumps(data).encode())
    async def json(self): return self.data


class EffectiveKeyTests(unittest.IsolatedAsyncioTestCase):
    async def test_key_response_reports_effective_environment_or_private_presence(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(dir=root.parent / 'work' / 'tmp') as folder:
            store = ConfigStore(Path(folder) / 'providers.json')
            cfg = json.loads((root / 'config' / 'providers.example.json').read_text(encoding='utf-8-sig'))
            for p in cfg['providers']: p['key_env'] = ''
            cfg['providers'][0]['key_env'] = 'ROUND3_TEST_SYNTHETIC_ENV'
            store.save(cfg)
            routes = web.RouteTableDef()
            register_routes(routes, store)
            handler = next(r.handler for r in routes if r.method == 'POST' and r.path == '/h3-adapter/key')
            with patch.dict(os.environ, {'H3_ADAPTER_MANAGEMENT_TOKEN': '', 'H3_ADAPTER_DISABLE_MANAGEMENT': '0', 'ROUND3_TEST_SYNTHETIC_ENV': 'round3-not-real-env'}):
                for pid, key, expected in [('primary', '', True), ('primary', 'round3-not-real-file', True), ('primary', '', True), ('backup1', 'round3-not-real-file', True), ('backup1', '', False)]:
                    with self.subTest(provider=pid, empty=not key):
                        response = await handler(Request({'provider_id': pid, 'key': key}))
                        self.assertEqual(response.status, 200)
                        body = json.loads(response.body)
                        self.assertEqual(body, {'ok': True, 'has_key': expected})
                        self.assertIsInstance(body['has_key'], bool)
                        self.assertEqual(body['has_key'], store.public()['keys'][pid])
                        self.assertNotIn('round3-not-real', response.text)
                rejected = await handler(Request({'provider_id': 'unknown', 'key': 'round3-not-real-file'}))
                self.assertEqual(rejected.status, 400)
                self.assertNotIn('round3-not-real', rejected.text)


if __name__ == '__main__': unittest.main()
