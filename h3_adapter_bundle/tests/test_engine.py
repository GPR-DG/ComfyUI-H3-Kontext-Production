"""Engine integration regressions against a real local HTTP server and durable SQLite."""
import importlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from mock_api import MockAPI, PNG_BYTES
from h3_adapter.config import ConfigStore


class EngineTests(unittest.TestCase):
    def setUp(self):
        work = Path(__file__).resolve().parents[2] / "work" / "tmp"
        work.mkdir(parents=True, exist_ok=True)
        self.tmp = tempfile.TemporaryDirectory(dir=work)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.api = MockAPI()
        self.addCleanup(self.api.close)
        self.previous_key = os.environ.get("H3_MOCK_KEY")
        os.environ["H3_MOCK_KEY"] = "H3_FAKE_SECRET"
        self.addCleanup(self.restore_key)
        self.store = ConfigStore(self.root / "providers.json")
        self.config = {
            "version": 1, "primary": "p0", "fallbacks": ["p1", "p2", "p3"],
            "currency": "USD", "auto_failover": True, "timeout_seconds": 1,
            "cooldown_seconds": 10, "max_total_cost": None,
            "providers": [self.provider("p" + str(i)) for i in range(4)],
        }
        self.store.save(self.config)

    def restore_key(self):
        if self.previous_key is None:
            os.environ.pop("H3_MOCK_KEY", None)
        else:
            os.environ["H3_MOCK_KEY"] = self.previous_key

    def provider(self, pid):
        return {
            "id": pid, "base_url": self.api.url(pid), "key_env": "H3_MOCK_KEY",
            "allow_insecure_localhost": True, "protocol": "openai_images",
            "edit_path": "/images/edits", "enabled": True,
            "models": {"background-edit": {
                "id": "model-" + pid, "task": "image_edit", "supports_mask": True,
                "max_images": 1, "price_upper_bound": 0.1, "allowed_params": [], "defaults": {},
            }},
            "discovery": None,
            "result": {"b64_path": "data.0.b64_json", "url_path": "data.0.url",
                       "download_hosts": [], "download_auth": False},
            "request": {"image_field": "image", "mask_field": "mask"},
            "safe_reject_statuses": [401, 403, 404],
        }

    def engine(self):
        try:
            module = importlib.import_module("h3_adapter.engine")
        except ModuleNotFoundError as exc:
            if exc.name == "h3_adapter.engine":
                self.fail("Engine implementation missing: safe failover behavior is not implemented")
            raise
        return module.Engine(self.store, self.root / "runtime")

    def edit(self, engine=None, **kwargs):
        return (engine or self.engine()).edit([PNG_BYTES], prompt="replace background with blue",
                                             model_alias="background-edit", timeout_seconds=kwargs.pop("timeout_seconds", 1), **kwargs)

    def test_safe_rejection_fails_over_without_duplicate_payment(self):
        # Break caught: removing safe-reject fallback or submitting either route twice.
        self.api.set_plan("p0", status=401)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertEqual(result["images"], [PNG_BYTES])
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0", "p1"])
        self.assertNotIn("H3_FAKE_SECRET", json.dumps(result["report"]))

    def test_primary_and_three_backups_are_tried_in_config_order(self):
        for pid in ("p0", "p1", "p2"):
            self.api.set_plan(pid, status=401)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p3")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0", "p1", "p2", "p3"])
        self.assertAlmostEqual(result["report"]["estimated_cost"], 0.1)

    def test_same_nonce_survives_engine_restart_without_a_second_post(self):
        first = self.edit(request_nonce=7)
        second = self.edit(request_nonce=7)
        self.assertEqual(second["images"], [PNG_BYTES])
        self.assertEqual(first["report"]["request_id"], second["report"]["request_id"])
        self.assertTrue(second["report"]["cached"])
        self.assertEqual(len(self.api.calls(method="POST")), 1)
        third = self.edit(request_nonce=8)
        self.assertEqual(third["report"]["status"], "success")
        self.assertNotEqual(first["report"]["request_id"], third["report"]["request_id"])
        self.assertEqual(len(self.api.calls(method="POST")), 2)

    def test_read_timeout_is_uncertain_and_same_nonce_cannot_repay(self):
        self.api.set_plan("p0", delay=0.2)
        # Isolate a sent request read timeout from protocol initialization budget.
        self.config["providers"][0]["timeout_seconds"] = 0.02
        self.store.save(self.config)
        first = self.edit(timeout_seconds=1, request_nonce=9)
        self.assertEqual(first["report"]["status"], "uncertain")
        self.assertEqual(first["images"], [])
        second = self.edit(request_nonce=9)
        self.assertIn(second["report"]["status"], ("uncertain", "blocked"))
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])

    def test_server_500_never_crosses_to_a_paid_backup(self):
        self.api.set_plan("p0", status=500)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "uncertain")
        self.assertEqual(result["images"], [])
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])
        self.assertNotIn("private server detail", json.dumps(result["report"]))

    def test_accepted_without_image_is_not_treated_as_safe_rejection(self):
        self.api.set_plan("p0", malformed=True)
        result = self.edit()
        self.assertIn(result["report"]["status"], ("uncertain", "awaiting_result"))
        self.assertEqual(result["images"], [])
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])

    def test_accepted_async_task_recovers_only_by_get_on_saved_provider(self):
        self.api.set_plan("p0", **{"async": True, "status": 202})
        self.config["providers"][0]["async"] = {
            "task_id_path": "id", "poll_path": "/tasks/{task_id}", "status_path": "status",
            "success": ["succeeded"], "failure": ["failed"], "poll_interval": 0.01, "max_polls": 2,
        }
        self.store.save(self.config)
        # Establish acceptance by pending/max_polls, not a 100ms client-initialization race.
        engine = self.engine()
        first = self.edit(engine, request_nonce=12)
        self.assertEqual(first["report"]["status"], "awaiting_result")
        self.assertEqual(first["report"]["error"], "poll_limit_no_resubmit")
        row = engine.journal.get(first["report"]["request_id"])
        self.assertEqual(row["state"], "accepted")
        self.assertEqual(row["task_id"], "task-1")
        self.assertEqual(len(self.api.calls(method="GET")), 2)
        self.assertEqual(len(self.api.calls(method="POST")), 1)
        self.api.complete()
        self.config["primary"] = "p1"
        self.config["fallbacks"] = ["p0", "p2", "p3"]
        self.config["providers"][0]["enabled"] = False
        self.config["providers"][0]["models"]["background-edit"]["id"] = "replacement-model"
        self.config["providers"][0]["base_url"] = self.api.url("changed-route")
        self.store.save(self.config)
        recovered = self.edit(request_nonce=12)
        self.assertEqual(recovered["report"]["status"], "success")
        self.assertEqual(recovered["report"]["provider"], "p0")
        self.assertEqual(recovered["report"]["model"], "model-p0")
        self.assertEqual(recovered["images"], [PNG_BYTES])
        self.assertEqual(first["report"]["request_id"], recovered["report"]["request_id"])
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])
        queries = self.api.calls(method="GET")
        self.assertTrue(queries)
        self.assertEqual({r["provider"] for r in queries}, {"p0"})
        self.assertEqual({r["path"] for r in queries}, {"/p0/v1/tasks/task-1"})
        cached = self.edit(request_nonce=12)
        self.assertEqual(cached["report"]["status"], "success")
        self.assertTrue(cached["report"]["cached"])
        self.assertEqual(cached["report"]["model"], "model-p0")
        self.assertEqual(cached["images"], [PNG_BYTES])
        self.assertEqual(len(self.api.calls(method="GET")), len(queries))
        self.assertEqual(len(self.api.calls(method="POST")), 1)

    def test_terminal_async_failure_does_not_start_a_backup_task(self):
        self.api.set_plan("p0", **{"async": True, "task_status": "failed"})
        self.config["providers"][0]["async"] = {
            "task_id_path": "id", "poll_path": "/tasks/{task_id}", "status_path": "status",
            "success": ["succeeded"], "failure": ["failed"], "poll_interval": 0.01, "max_polls": 2,
        }
        self.store.save(self.config)
        result = self.edit(request_nonce=13)
        self.assertEqual(result["report"]["status"], "failed")
        self.edit(request_nonce=13)
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])

    def test_mask_capability_skips_primary_and_keeps_mask_on_backup(self):
        self.config["providers"][0]["models"]["background-edit"]["supports_mask"] = False
        self.store.save(self.config)
        result = self.edit(mask=PNG_BYTES)
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertEqual(result["report"]["status"], "success")
        calls = self.api.calls(method="POST")
        self.assertEqual([r["provider"] for r in calls], ["p1"])
        self.assertIn(b'name="mask"', calls[0]["body"])
        self.assertIn(b"model-p1", calls[0]["body"])

    def test_multiple_images_require_explicit_model_capacity(self):
        self.config["providers"][1]["models"]["background-edit"]["max_images"] = 2
        self.store.save(self.config)
        result = self.engine().edit([PNG_BYTES, PNG_BYTES], prompt="change", timeout_seconds=1)
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        call = self.api.calls(method="POST")
        self.assertEqual([r["provider"] for r in call], ["p1"])
        self.assertEqual(call[0]["body"].count(b'name="image"'), 2)

    def test_unsupported_parameter_skips_incompatible_model(self):
        self.config["providers"][1]["models"]["background-edit"]["allowed_params"] = ["quality"]
        self.store.save(self.config)
        result = self.edit(params={"quality": "high"})
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p1"])
        self.assertIn(b"high", self.api.calls(method="POST")[0]["body"])

    def test_disabled_primary_is_skipped_before_any_network(self):
        self.config["providers"][0]["enabled"] = False
        self.store.save(self.config)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p1"])

    def test_missing_credential_never_submits(self):
        for provider in self.config["providers"]:
            provider["key_env"] = "H3_MOCK_INTENTIONALLY_MISSING"
        self.store.save(self.config)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "no_provider")
        self.assertEqual(self.api.calls(), [])

    def test_per_request_cost_cap_rejects_all_expensive_routes(self):
        result = self.edit(max_cost=0.05)
        self.assertEqual(result["report"]["status"], "no_provider")
        self.assertEqual(self.api.calls(), [])

    def test_unknown_price_cannot_bypass_a_finite_cost_cap(self):
        for provider in self.config["providers"]:
            provider["models"]["background-edit"]["price_upper_bound"] = None
        self.store.save(self.config)
        result = self.edit(max_cost=1)
        self.assertEqual(result["report"]["status"], "no_provider")
        self.assertEqual(self.api.calls(), [])

    def test_global_budget_persists_across_nonce_and_engine_restart(self):
        self.config["max_total_cost"] = 0.15
        self.store.save(self.config)
        first = self.edit(request_nonce=21)
        self.assertEqual(first["report"]["status"], "success")
        second = self.edit(request_nonce=22)
        self.assertIn(second["report"]["status"], ("no_provider", "blocked"))
        self.assertEqual(len(self.api.calls(method="POST")), 1)

    def test_safe_rejection_releases_reservation_before_backup(self):
        self.config["max_total_cost"] = 0.1
        self.store.save(self.config)
        self.api.set_plan("p0", status=401)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertAlmostEqual(result["report"]["estimated_cost"], 0.1)
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0", "p1"])

    def test_manual_provider_never_uses_any_other_route(self):
        self.api.set_plan("p2", status=401)
        result = self.edit(provider="p2")
        self.assertNotEqual(result["report"]["status"], "success")
        self.assertEqual(result["images"], [])
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p2"])

    def test_disabled_auto_failover_never_submits_a_backup(self):
        self.api.set_plan("p0", status=401)
        result = self.edit(auto_failover=False)
        self.assertNotEqual(result["report"]["status"], "success")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])

    def test_cooldown_persists_and_skips_rejected_primary_for_new_nonce(self):
        self.api.set_plan("p0", status=401)
        first = self.edit(request_nonce=31)
        self.assertEqual(first["report"]["provider"], "p1")
        second = self.edit(request_nonce=32)
        self.assertEqual(second["report"]["status"], "success")
        self.assertEqual(second["report"]["provider"], "p1")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0", "p1", "p1"])

    def test_connection_refused_before_submission_can_use_backup(self):
        import socket
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            unavailable_port = sock.getsockname()[1]
        self.config["providers"][0]["base_url"] = "http://127.0.0.1:" + str(unavailable_port) + "/v1"
        self.config["providers"][0]["timeout_seconds"] = 0.1
        self.store.save(self.config)
        result = self.edit()
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(result["report"]["provider"], "p1")
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p1"])

    def test_same_nonce_concurrent_claim_cannot_duplicate_paid_post(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        engines = [self.engine(), self.engine()]
        self.api.set_plan("p0", delay=0.05)
        barrier = Barrier(2)
        def run(engine):
            barrier.wait(timeout=2)
            return self.edit(engine=engine, request_nonce=41)
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(run, engines))
        self.assertTrue(any(r["report"]["status"] == "success" for r in results))
        self.assertEqual(len(self.api.calls(method="POST")), 1)
        self.assertTrue(all(r["report"]["status"] in ("success", "blocked", "uncertain") for r in results))

    def test_uncertain_submission_keeps_global_budget_reservation(self):
        self.config["max_total_cost"] = 0.15
        self.store.save(self.config)
        self.api.set_plan("p0", status=500)
        first = self.edit(request_nonce=51)
        self.assertEqual(first["report"]["status"], "uncertain")
        second = self.edit(request_nonce=52)
        self.assertIn(second["report"]["status"], ("no_provider", "blocked"))
        self.assertEqual([r["provider"] for r in self.api.calls(method="POST")], ["p0"])

    def test_pending_async_task_keeps_global_budget_reservation(self):
        self.config["max_total_cost"] = 0.15
        self.api.set_plan("p0", **{"async": True})
        self.config["providers"][0]["async"] = {
            "task_id_path": "id", "poll_path": "/tasks/{task_id}", "status_path": "status",
            "success": ["succeeded"], "failure": ["failed"], "poll_interval": 0.01, "max_polls": 1,
        }
        self.store.save(self.config)
        first = self.edit(request_nonce=61)
        self.assertEqual(first["report"]["status"], "awaiting_result")
        second = self.edit(request_nonce=62)
        self.assertIn(second["report"]["status"], ("no_provider", "blocked"))
        self.assertEqual(len(self.api.calls(method="POST")), 1)

    def test_mock_fixture_is_a_known_blue_image_not_a_background_edit_claim(self):
        import io
        from PIL import Image
        with Image.open(io.BytesIO(PNG_BYTES)) as image:
            self.assertEqual(image.size, (2, 2))
            self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (0, 0, 255, 255))


if __name__ == "__main__":
    unittest.main()
