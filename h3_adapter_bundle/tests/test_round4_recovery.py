"""Persisted results remain private; restore the original account before consuming."""
import base64
import tempfile
import unittest
from pathlib import Path

import httpx
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol, APIError
from mock_api import PNG_BYTES
from test_config import config


class InlineRecoveryTests(unittest.TestCase):
    def test_anonymous_url_recovers_after_identity_change_but_authenticated_url_stays_guarded(self):
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        for download_auth, host, allowed in ((False, 'api.example.invalid', False),
                                             (True, 'cdn.example.invalid', False),
                                             (True, 'api.example.invalid', False)):
            with self.subTest(download_auth=download_auth, host=host), tempfile.TemporaryDirectory(dir=work) as folder:
                store = ConfigStore(Path(folder) / 'providers.json')
                cfg = config()
                p = cfg['providers'][0]
                p['key_env'] = ''
                p['result'] = {'download_hosts': [host], 'download_auth': download_auth}
                store.save(cfg)
                store.save_key('primary', 'synthetic-original-merchant')
                calls = []
                def handler(request):
                    calls.append((request.method, request.url.host, request.headers.get('Authorization')))
                    if request.method == 'POST':
                        return httpx.Response(200, json={'data': [{'url': 'https://' + host + '/result.png'}]})
                    return httpx.Response(200, content=PNG_BYTES)
                class UnavailableResult(Protocol):
                    def result(self, *args): raise APIError('synthetic_download_pending')
                runtime = Path(folder) / 'runtime'
                first = Engine(store, runtime, lambda p, k: UnavailableResult(p, k, httpx.MockTransport(handler))).edit(
                    [PNG_BYTES], prompt='free persisted URL recovery', request_nonce=18)
                self.assertEqual(first['report']['status'], 'awaiting_result')
                p['base_url'] = 'https://replacement.example.invalid/v1'
                store.save(cfg)
                store.save_key('primary', 'synthetic-replacement-merchant')
                engine = Engine(store, runtime, lambda p, k: Protocol(p, k, httpx.MockTransport(handler)))
                recovered = engine.edit([PNG_BYTES], prompt='free persisted URL recovery', request_nonce=18)
                if allowed:
                    self.assertEqual(recovered['report']['status'], 'success')
                    self.assertEqual(recovered['images'], [PNG_BYTES])
                    self.assertEqual(calls[-1], ('GET', host, None))
                    self.assertEqual(engine.journal.get(first['report']['request_id'])['state'], 'completed')
                else:
                    self.assertEqual(recovered['report']['status'], 'awaiting_result')
                    self.assertEqual(recovered['report']['error'], 'credential_changed_no_resubmit')
                    self.assertEqual(len(calls), 1)
                    self.assertEqual(engine.journal.get(first['report']['request_id'])['state'], 'result_ready')
                # Download authentication does not confer account ownership.
                store.save_key('primary', 'synthetic-original-merchant')
                restored = engine.edit([PNG_BYTES], prompt='free persisted URL recovery', request_nonce=18)
                self.assertEqual(restored['report']['status'], 'success')
                self.assertEqual(restored['images'], [PNG_BYTES])
                self.assertEqual(sum(method == 'POST' for method, _, _ in calls), 1)
                self.assertEqual(engine.journal.get(first['report']['request_id'])['reserved_cost'], 0.1)

    def test_inline_result_recovers_after_provider_and_key_change_without_http(self):
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        with tempfile.TemporaryDirectory(dir=work) as folder:
            store = ConfigStore(Path(folder) / 'providers.json')
            cfg = config()
            cfg['providers'][0]['key_env'] = ''
            store.save(cfg)
            store.save_key('primary', 'synthetic-original-merchant')
            calls = []
            def handler(request):
                calls.append((request.method, request.url.host))
                return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(PNG_BYTES).decode()}]})
            class UnavailableResult(Protocol):
                def result(self, *args):
                    # Simulate a failed local materialization after the accepted response is durable.
                    raise APIError('synthetic_materialization_pending')
            runtime = Path(folder) / 'runtime'
            first = Engine(store, runtime, lambda p, k: UnavailableResult(p, k, httpx.MockTransport(handler))).edit(
                [PNG_BYTES], prompt='free persisted inline recovery', request_nonce=17)
            self.assertEqual(first['report']['status'], 'awaiting_result')
            cfg['providers'][0]['base_url'] = 'https://replacement.example.invalid/v1'
            store.save(cfg)
            store.save_key('primary', 'synthetic-replacement-merchant')
            engine = Engine(store, runtime, lambda p, k: Protocol(p, k, httpx.MockTransport(handler)))
            recovered = engine.edit([PNG_BYTES], prompt='free persisted inline recovery', request_nonce=17)
            self.assertEqual(recovered['report']['status'], 'awaiting_result')
            self.assertEqual(recovered['report']['error'], 'credential_changed_no_resubmit')
            self.assertEqual(recovered['images'], [])
            self.assertEqual(calls, [('POST', 'api.example.invalid')])
            store.save_key('primary', 'synthetic-original-merchant')
            recovered = engine.edit([PNG_BYTES], prompt='free persisted inline recovery', request_nonce=17)
            self.assertEqual(recovered['report']['status'], 'success')
            self.assertEqual(recovered['images'], [PNG_BYTES])
            self.assertEqual(recovered['report']['request_id'], first['report']['request_id'])
            self.assertEqual(recovered['report']['model'], 'edit-model')
            self.assertEqual(recovered['report']['estimated_cost'], 0.1)
            self.assertEqual(calls, [('POST', 'api.example.invalid')])
            replay = engine.edit([PNG_BYTES], prompt='free persisted inline recovery', request_nonce=17)
            self.assertTrue(replay['report']['cached'])
            self.assertEqual(calls, [('POST', 'api.example.invalid')])


if __name__ == '__main__':
    unittest.main()
