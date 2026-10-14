"""Management authorization contract regressions using the shipped aiohttp routes."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from h3_adapter.config import ConfigStore
from h3_adapter.routes import register_routes
from test_config import config

class DevelopmentAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def test_non_ascii_header_is_unauthorized_and_valid_token_recovers(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {'H3_ADAPTER_MANAGEMENT_TOKEN': 'synthetic-admin-token'}):
            store = ConfigStore(Path(folder) / 'providers.json')
            store.save(config())
            routes = web.RouteTableDef()
            register_routes(routes, store)
            app = web.Application()
            app.add_routes(routes)
            async with TestClient(TestServer(app)) as client:
                for token in ('é', '中文', '', 'wrong'):
                    response = await client.get('/h3-adapter/config', headers={'X-H3-Management-Token': token})
                    self.assertEqual(response.status, 401)
                    self.assertEqual(await response.text(), 'Administrator token required')
                response = await client.get('/h3-adapter/config', headers={'X-H3-Management-Token': 'synthetic-admin-token'})
                self.assertEqual(response.status, 200)
                self.assertIn('revision', await response.json())
