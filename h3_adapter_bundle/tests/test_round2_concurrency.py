"""Real management route regression for independent dialogs and TOCTOU saves."""
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

class ConfigConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_stale_dialog_cannot_overwrite_new_model_price(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"H3_ADAPTER_MANAGEMENT_TOKEN":"", "H3_ADAPTER_DISABLE_MANAGEMENT":""}):
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            routes = web.RouteTableDef()
            register_routes(routes, store)
            app = web.Application()
            app.add_routes(routes)
            async with TestClient(TestServer(app)) as client:
                first = await (await client.get("/h3-adapter/config")).json()
                stale = await (await client.get("/h3-adapter/config")).json()
                first["config"]["providers"][0]["models"]["background-edit"]["price_upper_bound"] = 10
                saved = await client.post("/h3-adapter/config", json={"config":first["config"], "expected_revision":first.get("revision","not-implemented")})
                self.assertEqual(saved.status, 200)
                stale["config"]["cooldown_seconds"] = 99
                collision = await client.post("/h3-adapter/config", json={"config":stale["config"], "expected_revision":stale.get("revision","not-implemented")})
                self.assertEqual(collision.status, 409, "A stale editor silently restores the old 0.1 price")
                self.assertEqual(store.load()["providers"][0]["models"]["background-edit"]["price_upper_bound"], 10)
                self.assertEqual(store.load()["cooldown_seconds"], 30)
                current = await (await client.get("/h3-adapter/config")).json()
                self.assertNotEqual(current["revision"], stale["revision"])

    async def test_successful_save_returns_revision_for_next_save(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, {"H3_ADAPTER_MANAGEMENT_TOKEN":"", "H3_ADAPTER_DISABLE_MANAGEMENT":""}):
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            routes = web.RouteTableDef()
            register_routes(routes, store)
            app = web.Application()
            app.add_routes(routes)
            async with TestClient(TestServer(app)) as client:
                data = await (await client.get("/h3-adapter/config")).json()
                self.assertIn("revision", data)
                data["config"]["cooldown_seconds"] = 77
                response = await client.post("/h3-adapter/config", json={"config":data["config"],"expected_revision":data["revision"]})
                self.assertEqual(response.status, 200)
                saved = await response.json()
                self.assertIn("revision", saved)
                data["config"]["cooldown_seconds"] = 88
                response = await client.post("/h3-adapter/config", json={"config":data["config"],"expected_revision":saved["revision"]})
                self.assertEqual(response.status, 200)
                self.assertEqual(store.load()["cooldown_seconds"], 88)

if __name__ == "__main__":
    unittest.main()
