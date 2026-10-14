import json
import os
import tempfile
import unittest
from pathlib import Path
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from h3_adapter.config import ConfigStore
from h3_adapter.routes import register_routes
from test_config import config


class RoutesTests(unittest.IsolatedAsyncioTestCase):
    async def test_manager_rejects_cross_origin_and_never_echoes_key(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigStore(Path(d) / 'providers.json')
            store.save(config())
            routes = web.RouteTableDef()
            register_routes(routes, store)
            app = web.Application()
            app.add_routes(routes)
            async with TestClient(TestServer(app)) as client:
                response = await client.post('/h3-adapter/key', json={'provider_id': 'primary', 'key': 'only-server-key'}, headers={'Origin': 'http://evil.invalid'})
                self.assertEqual(response.status, 403)
                response = await client.post('/h3-adapter/key', json={'provider_id': 'primary', 'key': 'only-server-key'})
                self.assertEqual(response.status, 200)
                response = await client.get('/h3-adapter/config')
                body = await response.text()
                self.assertNotIn('only-server-key', body)
                self.assertTrue(json.loads(body)['keys']['primary'])


if __name__ == '__main__':
    unittest.main()
