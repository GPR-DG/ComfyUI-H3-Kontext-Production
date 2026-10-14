"""Protocol boundary regression checks: no remote or paid requests."""
import copy
import gzip
import json
import unittest
from unittest.mock import patch

import httpx

PROVIDER = {
    "base_url": "https://api.example/v1", "protocol": "openai_images",
    "edit_path": "/images/edits", "auth": {"header": "Authorization", "prefix": "Bearer "},
    "request": {"image_field": "image", "mask_field": "mask"},
    "result": {"b64_path": "data.0.b64_json", "url_path": "data.0.url", "download_hosts": [], "download_auth": False},
    "safe_reject_statuses": [401, 403, 404],
}
MODEL = {"id": "image-editor", "task": "image_edit", "supports_mask": True, "max_images": 1}


class ProtocolTests(unittest.TestCase):
    def protocol(self, handler, provider=None):
        from h3_adapter.protocol import Protocol
        value = Protocol(copy.deepcopy(provider or PROVIDER), "secret-key", transport=httpx.MockTransport(handler))
        self.addCleanup(value.close)
        return value

    def submit(self, protocol, **kwargs):
        return protocol.submit(MODEL, [b"source-png"], kwargs.pop("mask", None), "make blue", kwargs.pop("params", {}), "stable-id", 2, **kwargs)

    def test_multipart_preserves_base_path_and_auth(self):
        sent = []
        def handler(request):
            sent.append(request)
            self.assertEqual(str(request.url), "https://api.example/v1/images/edits")
            self.assertEqual(request.headers["Authorization"], "Bearer secret-key")
            self.assertIn(b'name="image"', request.content)
            self.assertIn(b"source-png", request.content)
            self.assertIn(b'name="mask"', request.content)
            self.assertIn(b"mask-png", request.content)
            self.assertIn(b"make blue", request.content)
            return httpx.Response(200, json={"data": [{"b64_json": "aW1hZ2U="}]})
        p = self.protocol(handler)
        self.assertEqual(self.submit(p, mask=b"mask-png"), {"data": [{"b64_json": "aW1hZ2U="}]})
        self.assertEqual(len(sent), 1)

    def test_json_template_preserves_typed_values(self):
        config = copy.deepcopy(PROVIDER)
        config["protocol"] = "json_template"
        config["request"]["body"] = {"model": "{model}", "prompt": "{prompt}", "images": "{images_data_urls}", "parameters": "{params}", "mask": "{mask_base64}", "nested": ["{image_base64}"]}
        def handler(request):
            self.assertEqual(json.loads(request.content), {"model": "image-editor", "prompt": "make blue", "images": ["data:image/png;base64,c291cmNlLXBuZw=="], "parameters": {"n": 1, "flag": False}, "mask": "bWFzaw==", "nested": ["c291cmNlLXBuZw=="]})
            return httpx.Response(200, json={"ok": True})
        self.submit(self.protocol(handler, config), mask=b"mask", params={"n": 1, "flag": False})

    def test_upload_ref_and_submit_are_distinct_requests(self):
        config = copy.deepcopy(PROVIDER)
        config.update(protocol="json_template", upload={"path": "/upload", "field": "file", "ref_path": "data.url"})
        config["request"]["body"] = {"image": "{image_ref}", "prompt": "{prompt}", "model": "{model}"}
        paths = []
        def handler(request):
            paths.append(request.url.path)
            if request.url.path.endswith("/upload"):
                self.assertIn(b'name="file"', request.content)
                return httpx.Response(200, json={"data": {"url": "uploaded-ref"}})
            self.assertEqual(json.loads(request.content)["image"], "uploaded-ref")
            return httpx.Response(200, json={"id": "job-1"})
        self.assertEqual(self.submit(self.protocol(handler, config))["id"], "job-1")
        self.assertEqual(paths, ["/v1/upload", "/v1/images/edits"])

    def test_transport_failures_classified_without_any_retry(self):
        from h3_adapter.protocol import APIError
        cases = [(httpx.ConnectError, True), (httpx.ConnectTimeout, True), (httpx.PoolTimeout, True), (httpx.ReadTimeout, False), (httpx.WriteTimeout, False), (httpx.ReadError, False), (httpx.WriteError, False), (httpx.RemoteProtocolError, False)]
        for error_class, safe in cases:
            with self.subTest(error=error_class.__name__):
                calls = []
                def handler(request):
                    calls.append(request)
                    raise error_class("secret-key https://sensitive.example/priv?token=secret-key", request=request)
                with self.assertRaises(APIError) as caught:
                    self.submit(self.protocol(handler))
                self.assertEqual(caught.exception.safe_to_failover, safe)
                self.assertEqual(caught.exception.uncertain, not safe)
                self.assertNotIn("secret-key", str(caught.exception))
                self.assertNotIn("sensitive", str(caught.exception))
                self.assertEqual(len(calls), 1)

    def test_http_rejections_only_use_explicit_safe_statuses(self):
        from h3_adapter.protocol import APIError
        for status, safe in [(401, True), (403, True), (404, True), (429, False), (500, False), (503, False), (400, False), (408, False)]:
            with self.subTest(status=status):
                def handler(request):
                    return httpx.Response(status, text="secret-key sensitive server body")
                with self.assertRaises(APIError) as caught:
                    self.submit(self.protocol(handler))
                self.assertEqual(caught.exception.safe_to_failover, safe)
                self.assertEqual(caught.exception.uncertain, not safe)
                self.assertNotIn("secret-key", str(caught.exception))

    def test_malformed_success_and_redirect_never_resubmit(self):
        from h3_adapter.protocol import APIError
        for status, body, headers in [(200, b"not-json", {}), (200, b"[]", {}), (302, b"redirect", {"Location": "https://other.example/edits"})]:
            calls = []
            def handler(request):
                calls.append(request)
                return httpx.Response(status, content=body, headers=headers)
            with self.assertRaises(APIError) as caught:
                self.submit(self.protocol(handler))
            self.assertTrue(caught.exception.uncertain)
            self.assertFalse(caught.exception.safe_to_failover)
            self.assertEqual(len(calls), 1)

    def test_poll_tracks_same_task_and_normalizes_status(self):
        config = copy.deepcopy(PROVIDER)
        config["async"] = {"task_id_path": "data.id", "poll_path": "/tasks/{task_id}", "status_path": "data.status", "success": ["done"], "failure": ["failed"]}
        seen = []
        def handler(request):
            seen.append(request.url.path)
            self.assertEqual(request.method, "GET")
            return httpx.Response(200, json={"data": {"status": "done"}})
        p = self.protocol(handler, config)
        self.assertEqual(p.task_id({"data": {"id": "task/a"}}), "task/a")
        self.assertIsNone(p.task_id({}))
        self.assertEqual(p.poll("task/a", 2), ("succeeded", {"data": {"status": "done"}}))
        self.assertEqual(seen, ["/v1/tasks/task/a"])

    def test_pending_failed_poll_states(self):
        config = copy.deepcopy(PROVIDER)
        config["async"] = {"task_id_path": "id", "poll_path": "/tasks/{task_id}", "status_path": "status", "success": ["done"], "failure": ["failed"]}
        for incoming, expected in [("working", "pending"), ("failed", "failed")]:
            p = self.protocol(lambda request: httpx.Response(200, json={"status": incoming}), config)
            self.assertEqual(p.poll("job", 2)[0], expected)

    def test_inline_result_decodes_or_marks_invalid(self):
        from h3_adapter.protocol import APIError
        p = self.protocol(lambda request: self.fail("No HTTP for inline result"))
        self.assertEqual(p.result({"data": [{"b64_json": "aW1hZ2U="}]}, 2), [b"image"])
        for payload in [{}, {"data": [{"b64_json": "@invalid"}]}]:
            with self.assertRaises(APIError):
                p.result(payload, 2)

    def test_allowlisted_download_never_sends_api_key_to_cdn(self):
        config = copy.deepcopy(PROVIDER)
        config["result"].update(download_hosts=["cdn.example"], download_auth=True)
        def handler(request):
            self.assertEqual(request.url.host, "cdn.example")
            self.assertNotIn("Authorization", request.headers)
            return httpx.Response(200, content=b"image")
        p = self.protocol(handler, config)
        self.assertEqual(p.result({"data": [{"url": "https://cdn.example/image.png?signature=private"}]}, 2), [b"image"])

    def test_download_rejects_unlisted_host_and_redirect(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["result"]["download_hosts"] = ["cdn.example"]
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(302, headers={"Location": "https://api.example/leak"})
        p = self.protocol(handler, config)
        for url in ["https://evil.example/a", "http://cdn.example/a", "https://name:secret@cdn.example/a"]:
            with self.assertRaises(APIError):
                p.result({"data": [{"url": url}]}, 2)
        self.assertEqual(len(calls), 0)
        with self.assertRaises(APIError):
            p.result({"data": [{"url": "https://cdn.example/a"}]}, 2)
        self.assertEqual(len(calls), 1)

    def test_result_record_strips_echoed_secrets_and_resumes(self):
        p = self.protocol(lambda request: self.fail("No HTTP for inline result"))
        raw = {"echoed_key": "secret-key", "data": [{"b64_json": "aW1hZ2U=", "extra": "private"}]}
        record = p.result_record(raw)
        self.assertEqual(record, {"_h3_result": {"b64": "aW1hZ2U="}})
        self.assertNotIn("secret-key", json.dumps(record))
        self.assertEqual(p.result(record, 2), [b"image"])
        self.assertEqual(p.result_record({"data": [{"url": "https://cdn.example/a?sig=secret"}]}), {"_h3_result": {"url": "https://cdn.example/a?sig=secret"}})

    def test_same_host_auth_requires_explicit_host_and_download_opt_in(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["result"].update(download_auth=True)
        p = self.protocol(lambda request: self.fail("Host is not allowed"), config)
        payload = {"data": [{"url": "https://api.example/v1/result"}]}
        with self.assertRaises(APIError):
            p.result(payload, 2)
        config["result"]["download_hosts"] = ["api.example"]
        def handler(request):
            self.assertEqual(request.headers["Authorization"], "Bearer secret-key")
            return httpx.Response(200, content=b"image")
        self.assertEqual(self.protocol(handler, config).result(payload, 2), [b"image"])

    def test_same_host_different_port_never_receives_auth(self):
        config = copy.deepcopy(PROVIDER)
        config["result"].update(download_hosts=["api.example"], download_auth=True)
        seen = []
        def handler(request):
            seen.append(request)
            return httpx.Response(200, content=b"image")
        p = self.protocol(handler, config)
        self.assertEqual(p.result({"data": [{"url": "https://api.example:8443/image"}]}, 2), [b"image"])
        self.assertNotIn("Authorization", seen[0].headers)

    def test_documented_explicit_429_rejection_can_be_configured(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["safe_reject_statuses"] = [429]
        p = self.protocol(lambda request: httpx.Response(429, json={"error": "capacity rejected before acceptance"}), config)
        with self.assertRaises(APIError) as caught:
            self.submit(p)
        self.assertTrue(caught.exception.safe_to_failover)
        self.assertFalse(caught.exception.uncertain)

    def test_provider_plain_http_requires_loopback_opt_in(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["base_url"] = "http://127.0.0.1:9999/v1"
        with self.assertRaises(APIError):
            self.protocol(lambda request: httpx.Response(200, json={}), config)
        config["allow_insecure_localhost"] = True
        self.assertEqual(self.submit(self.protocol(lambda request: httpx.Response(200, json={"ok": True}), config)), {"ok": True})
        config["base_url"] = "http://public.example/v1"
        with self.assertRaises(APIError):
            self.protocol(lambda request: httpx.Response(200, json={}), config)

    def test_gzip_json_stream_is_decoded_once(self):
        encoded = gzip.compress(b'{"data":[{"b64_json":"aW1hZ2U="}]}')
        p = self.protocol(lambda request: httpx.Response(200, headers={"content-encoding": "gzip"}, stream=httpx.ByteStream(encoded)))
        payload = self.submit(p)
        self.assertEqual(payload, {"data": [{"b64_json": "aW1hZ2U="}]})
        self.assertEqual(p.result(payload, 2), [b"image"])

    def test_result_size_limit_applies_to_inline_base64(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["max_response_bytes"] = 4
        p = self.protocol(lambda request: self.fail("Inline data must not download"), config)
        self.assertEqual(p.result({"_h3_result": {"b64": "MTIzNA=="}}, 2), [b"1234"])
        with self.assertRaises(APIError) as caught:
            p.result({"_h3_result": {"b64": "MTIzNDU="}}, 2)
        self.assertEqual(caught.exception.code, "response_too_large")
        self.assertTrue(caught.exception.uncertain)

    def test_download_size_limit_stops_and_closes_stream(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["max_response_bytes"] = 4
        config["result"]["download_hosts"] = ["cdn.example"]
        class Chunks(httpx.SyncByteStream):
            def __init__(self):
                self.sent = 0
                self.closed = False
            def __iter__(self):
                for value in [b"1234", b"5", b"must-not-read"]:
                    self.sent += 1
                    yield value
            def close(self):
                self.closed = True
        stream = Chunks()
        p = self.protocol(lambda request: httpx.Response(200, stream=stream), config)
        with self.assertRaises(APIError) as caught:
            p.result({"data": [{"url": "https://cdn.example/image"}]}, 2)
        self.assertEqual(caught.exception.code, "response_too_large")
        self.assertEqual(stream.sent, 2)
        self.assertTrue(stream.closed)

    def test_5xx_cannot_be_declared_safe_rejection(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["safe_reject_statuses"] = [500, 503]
        for status in [500, 503]:
            p = self.protocol(lambda request: httpx.Response(status, json={"error": "unknown upstream"}), config)
            with self.assertRaises(APIError) as caught:
                self.submit(p)
            self.assertFalse(caught.exception.safe_to_failover)
            self.assertTrue(caught.exception.uncertain)

    def test_json_response_size_limit_is_uncertain_without_retry(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["max_response_bytes"] = 4
        sent = []
        def handler(request):
            sent.append(request)
            return httpx.Response(200, json={"id": "accepted-task"})
        with self.assertRaises(APIError) as caught:
            self.submit(self.protocol(handler, config))
        self.assertEqual(caught.exception.code, "response_too_large")
        self.assertTrue(caught.exception.uncertain)
        self.assertFalse(caught.exception.safe_to_failover)
        self.assertEqual(len(sent), 1)

    def test_submit_deadline_is_shared_by_upload_mask_and_edit(self):
        config = copy.deepcopy(PROVIDER)
        config.update(protocol="json_template", upload={"path": "/upload", "field": "file", "ref_path": "url"})
        config["request"]["body"] = {"image": "{image_ref}", "mask": "{mask_ref}"}
        now = [100.0]
        observed = []
        def handler(request):
            observed.append(request.extensions["timeout"]["read"])
            if request.url.path.endswith("upload"):
                now[0] += 1.5 if len(observed) == 1 else 0.4
                return httpx.Response(200, json={"url": "reference"})
            return httpx.Response(200, json={"ok": True})
        p = self.protocol(handler, config)
        with patch("h3_adapter.protocol.monotonic", side_effect=lambda: now[0], create=True):
            self.assertEqual(self.submit(p, mask=b"mask"), {"ok": True})
        self.assertEqual(len(observed), 3)
        self.assertLessEqual(observed[0], 2.0)
        self.assertLessEqual(observed[1], 0.5)
        self.assertLessEqual(observed[2], 0.100001)

    def test_expired_submit_budget_cannot_issue_edit_post(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config.update(protocol="json_template", upload={"path": "/upload", "field": "file", "ref_path": "url"})
        config["request"]["body"] = {"image": "{image_ref}"}
        now = [100.0]
        paths = []
        def handler(request):
            paths.append(request.url.path)
            now[0] += 3
            return httpx.Response(200, json={"url": "reference"})
        p = self.protocol(handler, config)
        with patch("h3_adapter.protocol.monotonic", side_effect=lambda: now[0], create=True):
            with self.assertRaises(APIError):
                self.submit(p)
        self.assertEqual(paths, ["/v1/upload"])

    def test_task_ids_reject_unbounded_or_echoed_credentials(self):
        from h3_adapter.protocol import APIError
        config = copy.deepcopy(PROVIDER)
        config["async"] = {"task_id_path": "id"}
        p = self.protocol(lambda request: self.fail("Task parsing does not request HTTP"), config)
        self.assertEqual(p.task_id({"id": "a" * 1024}), "a" * 1024)
        for value in ["a" * 1025, "secret-key", "prefix-secret-key-suffix", " ", "line\nfeed", {"secret": "value"}]:
            with self.subTest(value_type=type(value).__name__):
                with self.assertRaises(APIError) as caught:
                    p.task_id({"id": value})
                self.assertTrue(caught.exception.uncertain)
                self.assertNotIn("secret-key", str(caught.exception))

    def test_discovery_is_get_only_and_deduplicates(self):
        config = copy.deepcopy(PROVIDER)
        config["discovery"] = {"path": "/models", "items_path": "data", "id_path": "id"}
        def handler(request):
            self.assertEqual(request.method, "GET")
            self.assertEqual(request.url.path, "/v1/models")
            return httpx.Response(200, json={"data": [{"id": "a"}, {"id": "b"}, {"id": "a"}, {}]})
        self.assertEqual(self.protocol(handler, config).discover(), ["a", "b"])
        self.assertEqual(self.protocol(lambda request: self.fail("Manual models do not perform discovery")).discover(), [])


if __name__ == "__main__":
    unittest.main()
