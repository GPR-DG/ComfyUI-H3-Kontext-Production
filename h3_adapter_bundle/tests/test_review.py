"""Independent review regressions. Synthetic credentials, local mocks only."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

import httpx
from PIL import Image
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
from h3_adapter.routes import register_routes

WORK = Path(__file__).resolve().parents[2] / "work" / "tmp"
WORK.mkdir(parents=True, exist_ok=True)

def config():
    return {"version": 1, "primary": "primary", "fallbacks": ["backup"], "currency": "USD",
            "timeout_seconds": 2, "cooldown_seconds": 0, "max_total_cost": 1.0,
            "providers": [{"id": pid, "base_url": "https://" + pid + ".example/v1", "key_env": "H3_REVIEW_SYNTHETIC",
                           "protocol": "openai_images", "edit_path": "/images/edits", "discovery": None,
                           "models": {"background-edit": {"id": "edit", "task": "image_edit", "supports_mask": True,
                           "max_images": 1, "price_upper_bound": 0.1, "allowed_params": [], "defaults": {}}}}
                          for pid in ("primary", "backup")]}

def png():
    stream = io.BytesIO()
    Image.new("RGB", (2, 2), "blue").save(stream, "PNG")
    return stream.getvalue()

class ReviewStorageTests(unittest.TestCase):
    def test_concurrent_server_key_saves_preserve_both_providers(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            store.secret_path.write_text("{}", encoding="utf-8")
            gate = threading.Barrier(2)
            original = Path.read_text
            errors = []
            def coordinated_read(path, *args, **kwargs):
                value = original(path, *args, **kwargs)
                if path == store.secret_path:
                    time.sleep(0.05)
                return value
            def writer(pid):
                try:
                    gate.wait(timeout=3)
                    store.save_key(pid, "SYNTHETIC-" + pid)
                except Exception as error:
                    errors.append(type(error).__name__)
            with patch.object(Path, "read_text", coordinated_read):
                threads = [threading.Thread(target=writer, args=(pid,)) for pid in ("primary", "backup")]
                for thread in threads:
                    thread.start()
                for thread in threads:
                    thread.join(timeout=5)
            self.assertEqual(errors, [], "Atomic server-secret saves must not race on one .tmp filename")
            saved = json.loads(store.secret_path.read_text(encoding="utf-8"))
            self.assertEqual(set(saved), {"primary", "backup"}, "Concurrent secret read/modify/write loses an independently saved key")

class ReviewRouteTests(unittest.IsolatedAsyncioTestCase):
    async def client(self, store):
        routes = web.RouteTableDef()
        register_routes(routes, store)
        app = web.Application()
        app.add_routes(routes)
        client = TestClient(TestServer(app))
        await client.start_server()
        self.addAsyncCleanup(client.close)
        return client

    async def test_cloud_reverse_proxy_loopback_does_not_grant_management(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.dict(os.environ, {"H3_ADAPTER_MANAGEMENT_TOKEN": "", "H3_ADAPTER_DISABLE_MANAGEMENT": ""}):
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            client = await self.client(store)
            response = await client.get("/h3-adapter/config", headers={
                "Host": "cloud.example", "Origin": "http://cloud.example", "X-Forwarded-For": "198.51.100.77"})
            self.assertEqual(response.status, 403, "Cloud proxy peers can be loopback; require explicit admin token")

    async def test_invalid_async_configuration_returns_400_not_500(self):
        with tempfile.TemporaryDirectory(dir=WORK) as folder, patch.dict(os.environ, {"H3_ADAPTER_MANAGEMENT_TOKEN": "", "H3_ADAPTER_DISABLE_MANAGEMENT": ""}):
            store = ConfigStore(Path(folder) / "providers.json")
            value = config()
            store.save(value)
            value["providers"][0]["async"] = True
            client = await self.client(store)
            response = await client.post("/h3-adapter/config", json={"config": value})
            self.assertEqual(response.status, 400, "Non-object async must be a rejected config, not an uncaught AttributeError")


def _secret_process(path, pid, gate, queue):
    store = ConfigStore(Path(path))
    original = Path.read_text
    def slow_read(file, *args, **kwargs):
        value = original(file, *args, **kwargs)
        if file == store.secret_path:
            time.sleep(0.05)
        return value
    try:
        gate.wait(timeout=5)
        with patch.object(Path, "read_text", slow_read):
            store.save_key(pid, "SYNTHETIC-" + pid)
        queue.put(("ok", pid))
    except Exception as error:
        queue.put(("error", type(error).__name__))

def _engine_process(path, runtime, nonce, gate, paid, queue):
    try:
        os.environ["H3_REVIEW_SYNTHETIC"] = "SYNTHETIC-NOT-A-REAL-KEY"
        content = png()
        def handler(request):
            if request.method == "POST":
                with paid.get_lock():
                    paid.value += 1
                time.sleep(0.15)
            return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(content).decode()}]})
        factory = lambda p, key: Protocol(p, key, transport=httpx.MockTransport(handler))
        engine = Engine(ConfigStore(Path(path)), Path(runtime), factory)
        gate.wait(timeout=5)
        result = engine.edit([content], prompt="mock blue", request_nonce=nonce, max_cost=0.1)
        queue.put(("ok", result["report"]["status"]))
    except Exception as error:
        queue.put(("error", type(error).__name__))

class ReviewProcessesTests(unittest.TestCase):
    def run_processes(self, target, arguments):
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        processes = [context.Process(target=target, args=(*args, queue)) for args in arguments]
        for process in processes:
            process.start()
        try:
            for process in processes:
                process.join(timeout=12)
            self.assertTrue(all(not p.is_alive() for p in processes), "Mock worker did not terminate")
            self.assertTrue(all(p.exitcode == 0 for p in processes), "Mock worker process failed")
            return [queue.get(timeout=2) for _ in processes]
        finally:
            for process in processes:
                if process.is_alive():
                    process.terminate()
                    process.join(timeout=2)
            queue.close()

    def test_cross_process_server_key_updates_preserve_both(self):
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            store.secret_path.write_text("{}", encoding="utf-8")
            gate = context.Barrier(2)
            results = self.run_processes(_secret_process, [(str(store.path), pid, gate) for pid in ("primary", "backup")])
            self.assertTrue(all(kind == "ok" for kind, detail in results), results)
            self.assertEqual(set(json.loads(store.secret_path.read_text())), {"primary", "backup"})

    def test_cross_process_identical_edit_submits_once(self):
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            store = ConfigStore(Path(folder) / "providers.json")
            store.save(config())
            gate, paid = context.Barrier(2), context.Value("i", 0)
            args = (str(store.path), str(Path(folder) / "runtime"), 0, gate, paid)
            results = self.run_processes(_engine_process, [args, args])
            self.assertTrue(all(kind == "ok" for kind, detail in results), results)
            self.assertEqual(paid.value, 1, "Stable request id must protect paid POST across processes")
            self.assertIn("success", [detail for kind, detail in results])

    def test_cross_process_distinct_requests_share_cumulative_cap(self):
        import multiprocessing
        context = multiprocessing.get_context("spawn")
        with tempfile.TemporaryDirectory(dir=WORK) as folder:
            store = ConfigStore(Path(folder) / "providers.json")
            value = config()
            value["max_total_cost"] = 0.1
            store.save(value)
            gate, paid = context.Barrier(2), context.Value("i", 0)
            args = [(str(store.path), str(Path(folder) / "runtime"), nonce, gate, paid) for nonce in (0, 1)]
            results = self.run_processes(_engine_process, args)
            self.assertTrue(all(kind == "ok" for kind, detail in results), results)
            self.assertEqual(paid.value, 1, "SQLite budget reservation must precede each independent paid POST")
            self.assertEqual(sorted(detail for kind, detail in results), ["blocked", "success"])

class ReviewEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.store = ConfigStore(self.folder / "providers.json")
        self.value = config()
        self.content = png()
        self.calls = []
        self.environment = patch.dict(os.environ, {"H3_REVIEW_SYNTHETIC": "SYNTHETIC-NOT-A-REAL-KEY"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def engine(self, handler=None):
        if handler is None:
            def handler(request):
                self.calls.append((request.method, request.url.path))
                return httpx.Response(200, json={"data": [{"b64_json": base64.b64encode(self.content).decode()}]})
        return Engine(self.store, self.folder / "runtime", lambda p, key: Protocol(p, key, transport=httpx.MockTransport(handler)))

    def test_unknown_price_remains_unknown_in_success_and_cached_report(self):
        self.value["max_total_cost"] = None
        self.value["providers"][0]["models"]["background-edit"]["price_upper_bound"] = None
        self.store.save(self.value)
        first = self.engine().edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(first["report"]["status"], "success")
        self.assertIsNone(first["report"]["estimated_cost"], "Unknown cost must not become an estimated free job")
        cached = self.engine().edit([self.content], prompt="mock blue", max_cost=None)
        self.assertTrue(cached["report"]["cached"])
        self.assertIsNone(cached["report"]["estimated_cost"])

    def test_enabling_global_cap_after_unknown_charge_denies_new_paid_submit(self):
        self.value["max_total_cost"] = None
        self.value["providers"][0]["models"]["background-edit"]["price_upper_bound"] = None
        self.store.save(self.value)
        first = self.engine().edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(first["report"]["status"], "success")
        self.value["max_total_cost"] = 0.1
        self.value["providers"][0]["models"]["background-edit"]["price_upper_bound"] = 0.1
        self.store.save(self.value)
        second = self.engine().edit([self.content], prompt="mock blue", max_cost=0.1, request_nonce=1)
        self.assertEqual(second["report"]["status"], "blocked", "A finite cumulative cap cannot treat past unknown accepted charges as zero")
        self.assertEqual(len([call for call in self.calls if call[0] == "POST"]), 1)

    def test_accepted_async_task_resumes_get_without_second_paid_post(self):
        self.value["providers"][0]["async"] = {"task_id_path": "id", "poll_path": "/tasks/{task_id}",
                                                "status_path": "status", "max_polls": 1, "poll_interval": 0,
                                                "success": ["completed"], "failure": ["failed"]}
        self.store.save(self.value)
        poll_count = 0
        def handler(request):
            nonlocal poll_count
            self.calls.append((request.method, request.url.path))
            if request.method == "POST":
                return httpx.Response(200, json={"id": "accepted-job"})
            poll_count += 1
            if poll_count == 1:
                return httpx.Response(200, json={"status": "pending"})
            return httpx.Response(200, json={"status": "completed", "data": [{"b64_json": base64.b64encode(self.content).decode()}]})
        first = self.engine(handler).edit([self.content], prompt="mock blue")
        self.assertEqual(first["report"]["status"], "awaiting_result")
        second = self.engine(handler).edit([self.content], prompt="mock blue")
        self.assertEqual(second["report"]["status"], "success")
        self.assertEqual(len([call for call in self.calls if call[0] == "POST"]), 1)
        self.assertEqual(len([call for call in self.calls if call[0] == "GET"]), 2)


    def test_unknown_price_stays_unknown_on_ambiguous_replay(self):
        self.value["max_total_cost"] = None
        self.value["providers"][0]["models"]["background-edit"]["price_upper_bound"] = None
        self.store.save(self.value)
        def handler(request):
            self.calls.append((request.method, request.url.path))
            return httpx.Response(500, json={"error": "synthetic ambiguity"})
        first = self.engine(handler).edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(first["report"]["status"], "uncertain")
        self.assertIsNone(first["report"]["estimated_cost"])
        replay = self.engine(handler).edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(replay["report"]["status"], "uncertain")
        self.assertIsNone(replay["report"]["estimated_cost"], "Ambiguous historical price remains unknown, not free")
        self.assertEqual(len(self.calls), 1)

    def test_unknown_price_stays_unknown_on_terminal_task_replay(self):
        self.value["max_total_cost"] = None
        self.value["providers"][0]["models"]["background-edit"]["price_upper_bound"] = None
        self.value["providers"][0]["async"] = {"task_id_path": "id", "poll_path": "/tasks/{task_id}",
                                                "status_path": "status", "max_polls": 1, "poll_interval": 0,
                                                "success": ["completed"], "failure": ["failed"]}
        self.store.save(self.value)
        def handler(request):
            self.calls.append((request.method, request.url.path))
            return httpx.Response(200, json={"id": "failed-job"} if request.method == "POST" else {"status": "failed"})
        first = self.engine(handler).edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(first["report"]["status"], "failed")
        self.assertIsNone(first["report"]["estimated_cost"])
        replay = self.engine(handler).edit([self.content], prompt="mock blue", max_cost=None)
        self.assertEqual(replay["report"]["status"], "failed")
        self.assertIsNone(replay["report"]["estimated_cost"], "Terminal remote failure does not imply an uncharged job")
        self.assertEqual(len([method for method, path in self.calls if method == "POST"]), 1)

class ReviewBoundedTimeTests(unittest.TestCase):
    def test_trickling_small_response_chunks_do_not_hide_deadline(self):
        from h3_adapter.protocol import APIError
        class SlowChunks(httpx.SyncByteStream):
            def __iter__(self):
                for _ in range(40):
                    time.sleep(0.005)
                    yield b"x"
        provider = config()["providers"][0]
        protocol = Protocol(provider, "SYNTHETIC-NOT-A-REAL-KEY",
                            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=SlowChunks())))
        started = time.monotonic()
        try:
            with self.assertRaises(APIError):
                protocol.submit(provider["models"]["background-edit"], [png()], None, "mock", {}, "mock-id", 0.015)
            self.assertLess(time.monotonic() - started, 0.1, "64 KiB chunk assembly must not hide expired deadline while peer trickles small chunks")
        finally:
            protocol.close()
