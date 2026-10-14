"""Round-two regressions: durable accounting, deadlines, and concurrent recovery."""
import base64
import io
import json
import os
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
import httpx
from PIL import Image
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.ledger import Journal
from h3_adapter.protocol import Protocol, APIError

WORK = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
WORK.mkdir(parents=True, exist_ok=True)

class Round2SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        stream = io.BytesIO()
        Image.new('RGB', (2, 2), 'blue').save(stream, 'PNG')
        self.content = stream.getvalue()
        self.payload = {'data': [{'b64_json': base64.b64encode(self.content).decode()}]}
        self.calls = []
        self.environ = patch.dict(os.environ, {'H3_ROUND2_PRIMARY': 'SYNTHETIC-PRIMARY', 'H3_ROUND2_BACKUP': 'SYNTHETIC-BACKUP'})
        self.environ.start()
        self.addCleanup(self.environ.stop)
        self.config = {'version': 1, 'primary': 'primary', 'fallbacks': ['backup'], 'currency': 'USD',
                       'timeout_seconds': 2, 'cooldown_seconds': 0, 'max_total_cost': 1,
                       'providers': [self.provider(pid) for pid in ('primary', 'backup')]}
        self.store = ConfigStore(self.folder / 'providers.json')
        self.store.save(self.config)

    def provider(self, pid):
        return {'id': pid, 'base_url': 'https://' + pid + '.example/v1', 'protocol': 'openai_images',
                'edit_path': '/edit', 'key_env': 'H3_ROUND2_' + pid.upper(),
                'models': {'background-edit': {'id': 'model-' + pid, 'task': 'image_edit', 'max_images': 1,
                           'supports_mask': True, 'price_upper_bound': 0.1, 'allowed_params': [], 'defaults': {}}}}

    def engine(self, handler=None):
        if handler is None:
            def handler(request):
                self.calls.append((request.method, request.url.host, request.url.path))
                return httpx.Response(200, json=self.payload)
        return Engine(self.store, self.folder / 'runtime', lambda p, key: Protocol(p, key, httpx.MockTransport(handler)))

    def edit(self, engine=None, **kwargs):
        return (engine or self.engine()).edit([self.content], prompt='synthetic blue edit', **kwargs)

    def test_zero_price_history_does_not_break_later_finite_budget_reservation(self):
        # Break caught: previous zero-cost model dict shadows new model id in SQLite binding.
        self.config['providers'][0]['models']['background-edit']['price_upper_bound'] = 0
        self.store.save(self.config)
        self.assertEqual(self.edit()['report']['status'], 'success')
        self.config['providers'][0]['models']['background-edit']['price_upper_bound'] = 0.1
        self.store.save(self.config)
        result = self.edit(request_nonce=1)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(result['report']['model'], 'model-primary')
        self.assertEqual(len(self.calls), 2)

    def test_historical_cost_currency_survives_config_currency_change(self):
        # Break caught: cached/recovered cost uses current currency instead of the reserved currency.
        for mode in ('completed', 'uncertain', 'accepted', 'failed'):
            with self.subTest(state=mode):
                self.config['currency'] = 'USD'
                provider = self.config['providers'][0]
                provider.pop('async', None)
                if mode in ('accepted', 'failed'):
                    provider['async'] = {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}',
                                         'status_path': 'status', 'max_polls': 1, 'poll_interval': 0}
                self.store.save(self.config)
                def handler(request):
                    if mode == 'uncertain':
                        return httpx.Response(500, json={'error': 'ambiguous acceptance'})
                    if mode in ('accepted', 'failed'):
                        payload = {'id': 'accepted-task'} if request.method == 'POST' else {'status': 'failed' if mode == 'failed' else 'pending'}
                        return httpx.Response(200, json=payload)
                    return httpx.Response(200, json=self.payload)
                factory = lambda p, key: Protocol(p, key, httpx.MockTransport(handler))
                engine = Engine(self.store, self.folder / mode, factory)
                first = self.edit(engine)
                self.assertEqual(first['report']['currency'], 'USD')
                self.config['currency'] = 'CNY'
                self.store.save(self.config)
                replay = self.edit(engine)
                self.assertEqual(replay['report']['estimated_cost'], 0.1)
                self.assertEqual(replay['report']['currency'], 'USD')

    def test_poll_download_and_discovery_stop_trickling_responses_at_their_deadline(self):
        # Break caught: HTTPX inactivity timeout lets GETs trickle indefinitely beyond caller budget.
        provider = self.config['providers'][0]
        provider['async'] = {'poll_path': '/tasks/{task_id}', 'status_path': 'status'}
        provider['result'] = {'download_hosts': ['primary.example']}
        provider['discovery'] = {'path': '/models'}
        for operation in ('poll', 'download', 'discover'):
            with self.subTest(operation=operation):
                data = {'poll': b'{"status":"pending"}', 'download': self.content,
                        'discover': b'{"data":[{"id":"model-1"}]}' }[operation]
                class SlowChunks(httpx.SyncByteStream):
                    def __iter__(self):
                        for index in range(0, len(data), 2):
                            time.sleep(0.005)
                            yield data[index:index + 2]
                protocol = Protocol(provider, 'SYNTHETIC-KEY', httpx.MockTransport(
                    lambda request: httpx.Response(200, stream=SlowChunks())))
                try:
                    with self.assertRaises(APIError) as caught:
                        if operation == 'poll':
                            protocol.poll('accepted-job', 0.012)
                        elif operation == 'download':
                            protocol.result({'data': [{'url': 'https://primary.example/result.png'}]}, 0.012)
                        else:
                            protocol.discover(0.012)
                    self.assertEqual(caught.exception.code, 'submit_deadline_exceeded')
                finally:
                    protocol.close()

    def test_invalid_auth_value_is_rejected_before_network_and_can_use_backup(self):
        # Break caught: definitely-unsent header construction errors become irrevocable uncertain charges.
        for nonce, key in enumerate(('中文-key', 'ascii\nkey', 'ascii\rkey'), 10):
            with self.subTest(key=repr(key)):
                os.environ['H3_ROUND2_PRIMARY'] = key
                result = self.edit(request_nonce=nonce)
                self.assertEqual(result['report']['status'], 'success')
                self.assertEqual(result['report']['provider'], 'backup')
                self.assertEqual(result['report']['attempts'][0]['error'], 'invalid_auth_header')
        self.assertEqual([host for method, host, path in self.calls], ['backup.example'] * 3)

    def test_late_concurrent_poll_preserves_completed_cache_over_real_http(self):
        # Break caught: a delayed recovery can roll completed back and hide its valid saved result.
        for late_status in ('succeeded', 'failed'):
            with self.subTest(late_poll=late_status):
                gate = threading.Barrier(2)
                completed = threading.Event()
                lock = threading.Lock()
                counters = {'poll': 0, 'download': 0}
                phase = ['seed']
                calls = []
                content = self.content
                class Handler(BaseHTTPRequestHandler):
                    protocol_version = 'HTTP/1.1'
                    def log_message(self, *args):
                        pass
                    def reply(self, status, body):
                        self.send_response(status)
                        self.send_header('Content-Length', str(len(body)))
                        self.send_header('Connection', 'close')
                        self.end_headers()
                        self.wfile.write(body)
                    def do_POST(self):
                        self.rfile.read(int(self.headers.get('Content-Length', 0)))
                        calls.append((self.command, self.path))
                        self.reply(200, b'{"id":"accepted-job"}')
                    def do_GET(self):
                        calls.append((self.command, self.path))
                        if self.path == '/image.png':
                            with lock:
                                index = counters['download']
                                counters['download'] += 1
                            self.reply(200 if index == 0 else 503, content if index == 0 else b'url expired')
                            return
                        if phase[0] == 'seed':
                            self.reply(200, b'{"status":"pending"}')
                            return
                        with lock:
                            index = counters['poll']
                            counters['poll'] += 1
                        gate.wait(3)
                        if index == 1:
                            if not completed.wait(3):
                                self.reply(500, b'missing completion')
                                return
                        status = late_status if index == 1 else 'succeeded'
                        payload = {'status': status, 'data': [{'url': base + '/image.png'}]}
                        self.reply(200, json.dumps(payload).encode())
                server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
                server.daemon_threads = True
                thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
                thread.start()
                base = 'http://127.0.0.1:' + str(server.server_port)
                provider = self.config['providers'][0]
                provider['base_url'] = base + '/v1'
                provider['allow_insecure_localhost'] = True
                provider['async'] = {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}', 'status_path': 'status',
                                     'max_polls': 1, 'poll_interval': 0}
                provider['result'] = {'download_hosts': ['127.0.0.1']}
                self.store.save(self.config)
                runtime = self.folder / ('concurrent-' + late_status)
                try:
                    first = self.edit(Engine(self.store, runtime))
                    self.assertEqual(first['report']['status'], 'awaiting_result')
                    phase[0] = 'recover'
                    original_mark = Journal.mark
                    def observed_mark(journal, request_id, state, **kwargs):
                        result = original_mark(journal, request_id, state, **kwargs)
                        if state == 'completed':
                            completed.set()
                        return result
                    with patch.object(Journal, 'mark', observed_mark):
                        with ThreadPoolExecutor(max_workers=2) as pool:
                            results = list(pool.map(lambda _: self.edit(Engine(self.store, runtime)), range(2)))
                    replay = self.edit(Engine(self.store, runtime))
                    print(json.dumps({'late_poll': late_status, 'recovery_statuses': [r['report']['status'] for r in results],
                                      'replay_status': replay['report']['status'], 'replay_cached': replay['report']['cached'], 'calls': calls}))
                    self.assertTrue(all(r['report']['status'] == 'success' for r in results))
                    self.assertEqual(replay['report']['status'], 'success')
                    self.assertEqual(replay['images'], [content])
                    self.assertTrue(replay['report']['cached'])
                    self.assertEqual(sum(method == 'POST' for method, path in calls), 1)
                    self.assertEqual(counters['download'], 1)
                finally:
                    server.shutdown()
                    server.server_close()
                    thread.join(2)

    def test_provider_initialization_cannot_restart_expired_request_budget(self):
        # Break caught: a remaining budget captured before initialization becomes a new POST deadline.
        def handler(request):
            self.calls.append((request.method, request.url.host, request.url.path))
            return httpx.Response(200, json=self.payload)
        def delayed_factory(provider, key):
            time.sleep(0.05)
            return Protocol(provider, key, httpx.MockTransport(handler))
        engine = Engine(self.store, self.folder / 'runtime', delayed_factory)
        result = self.edit(engine, timeout_seconds=0.02)
        self.assertEqual(self.calls, [])
        self.assertEqual(result['report']['status'], 'no_provider')
        self.assertEqual(engine.journal.get(result['report']['request_id'])['reserved_cost'], 0)

    def test_auth_nul_and_edge_whitespace_are_unsent_but_del_and_bearer_space_work_over_http(self):
        # Break caught: h11 rejects NUL/edge SP/HTAB locally, locking an unsent paid request uncertain.
        calls = []
        payload = json.dumps(self.payload).encode()
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            def log_message(self, *args):
                pass
            def do_POST(self):
                self.rfile.read(int(self.headers.get('Content-Length', 0)))
                calls.append(self.path)
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.send_header('Connection', 'close')
                self.end_headers()
                self.wfile.write(payload)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
        thread.start()
        base = 'http://127.0.0.1:' + str(server.server_port)
        for provider in self.config['providers']:
            provider['base_url'] = base + '/' + provider['id'] + '/v1'
            provider['allow_insecure_localhost'] = True
        primary = self.config['providers'][0]
        primary['key_env'] = ''
        fixtures = (
            ('nul', 'Bearer ', 'synthetic\x00key', 'backup'),
            ('leading_space', ' Bearer ', 'synthetic-key', 'backup'),
            ('leading_tab', '\tBearer ', 'synthetic-key', 'backup'),
            ('trailing_space', 'Bearer ', 'synthetic-key ', 'backup'),
            ('trailing_tab', 'Bearer ', 'synthetic-key\t', 'backup'),
            ('normal_bearer_internal_space', 'Bearer ', 'synthetic-key', 'primary'),
            ('del', 'Bearer ', 'synthetic\x7fkey', 'primary'),
        )
        try:
            for nonce, (case, prefix, key, expected_provider) in enumerate(fixtures, 100):
                with self.subTest(case=case):
                    primary['auth'] = {'header': 'Authorization', 'prefix': prefix}
                    self.store.save(self.config)
                    self.store.save_key('primary', key)
                    before = len(calls)
                    result = self.edit(Engine(self.store, self.folder / 'runtime'), request_nonce=nonce)
                    actual = calls[before:]
                    print(json.dumps({'auth_fixture': case, 'status': result['report']['status'],
                                      'provider': result['report']['provider'], 'actual_http_POSTs': actual}))
                    self.assertEqual(result['report']['status'], 'success')
                    self.assertEqual(result['report']['provider'], expected_provider)
                    self.assertEqual(actual, ['/' + expected_provider + '/v1/edit'])
                    if expected_provider == 'backup':
                        self.assertEqual(result['report']['attempts'][0]['error'], 'invalid_auth_header')
        finally:
            server.shutdown()
            server.server_close()
            thread.join(2)

if __name__ == '__main__':
    unittest.main()
