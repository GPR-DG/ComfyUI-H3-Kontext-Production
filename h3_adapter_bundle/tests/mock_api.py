"""Deterministic, loopback-only image-edit API fixtures. No paid API or image semantics."""
import base64
import json
import struct
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit


def _chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


# Hand-defined fixture: two rows of two blue RGBA pixels, not a semantic repair.
PNG_BYTES = (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", struct.pack(">IIBBBBB", 2, 2, 8, 6, 0, 0, 0))
             + _chunk(b"IDAT", zlib.compress((b"\0" + b"\0\0\xff\xff" * 2) * 2))
             + _chunk(b"IEND", b""))
PNG_B64 = base64.b64encode(PNG_BYTES).decode("ascii")


class MockAPI:
    def __init__(self, port=0):
        self.lock = threading.RLock()
        self.requests = []
        self.plans = {}
        self.tasks = {}
        self.task_counter = 0
        api = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def reply(self, status, payload):
                body = json.dumps(payload).encode("utf-8")
                try:
                    self.send_response(status)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Connection", "close")
                    self.close_connection = True
                    self.end_headers()
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass  # A deliberate read-timeout client may already have disconnected.

            def do_POST(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                parts = urlsplit(self.path).path.strip("/").split("/")
                pid = parts[0] if parts else ""
                with api.lock:
                    api.requests.append({"method": "POST", "provider": pid, "path": self.path,
                                         "body": body, "headers": dict(self.headers)})
                    plan = dict(api.plans.get(pid, {}))
                if plan.get("delay"):
                    time.sleep(plan["delay"])
                status = plan.get("status", 200)
                if status >= 400:
                    self.reply(status, {"error": {"message": "private server detail H3_FAKE_SECRET"}})
                elif plan.get("async"):
                    with api.lock:
                        api.task_counter += 1
                        task_id = "task-" + str(api.task_counter)
                        api.tasks[task_id] = {"provider": pid, "status": plan.get("task_status", "pending")}
                    self.reply(status, {"id": task_id, "status": "pending"})
                elif plan.get("malformed"):
                    self.reply(status, {"no_result": True})
                else:
                    self.reply(status, {"data": [{"b64_json": PNG_B64}]})

            def do_GET(self):
                parts = urlsplit(self.path).path.strip("/").split("/")
                pid = parts[0] if parts else ""
                with api.lock:
                    api.requests.append({"method": "GET", "provider": pid, "path": self.path,
                                         "body": b"", "headers": dict(self.headers)})
                if parts[-1] == "models":
                    self.reply(200, {"data": [{"id": "mock-editor"}, {"id": "mock-editor"}]})
                    return
                with api.lock:
                    task = api.tasks.get(parts[-1])
                    task = dict(task) if task else None
                if not task or task["provider"] != pid:
                    self.reply(404, {"error": "not found"})
                    return
                payload = {"id": parts[-1], "status": task["status"]}
                if task["status"] == "succeeded":
                    payload["data"] = [{"b64_json": PNG_B64}]
                self.reply(200, payload)

        self.server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.base_url = "http://127.0.0.1:" + str(self.server.server_port)

    def set_plan(self, provider, **plan):
        with self.lock:
            self.plans[provider] = plan

    def url(self, provider):
        return self.base_url + "/" + provider + "/v1"

    def calls(self, provider=None, method=None):
        with self.lock:
            return [dict(r) for r in self.requests
                    if (provider is None or r["provider"] == provider)
                    and (method is None or r["method"] == method)]

    def complete(self, status="succeeded"):
        with self.lock:
            for task in self.tasks.values():
                task["status"] = status

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
