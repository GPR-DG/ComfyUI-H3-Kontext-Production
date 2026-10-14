"""Round-four health regressions: client safety is not provider outage."""
import base64
import copy
import io
import tempfile
import unittest
from pathlib import Path
import httpx
from PIL import Image
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol

WORK = Path(__file__).resolve().parents[2] / 'work' / 'tmp'

class Round4HealthTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        data = io.BytesIO()
        Image.new('RGBA', (2, 2), 'blue').save(data, 'PNG')
        self.image = data.getvalue()
        self.payload = {'data': [{'b64_json': base64.b64encode(self.image).decode()}]}
        self.calls = []
        self.config = {'version': 1, 'primary': 'primary', 'fallbacks': ['backup'],
                       'cooldown_seconds': 60, 'timeout_seconds': 10, 'providers': []}
        for pid, cost in [('primary', 0.1), ('backup', 0.7)]:
            self.config['providers'].append({'id': pid, 'base_url': 'https://' + pid + '.invalid',
                'key_env': '', 'protocol': 'json_template', 'edit_path': '/edit',
                'request': {'body': {'images': '{images_data_urls}', 'mask': '{mask_base64}'}},
                'models': {'background-edit': {'id': 'model-' + pid, 'task': 'image_edit',
                    'supports_mask': True, 'max_images': 2, 'price_upper_bound': cost,
                    'allowed_params': [], 'defaults': {}}}})
        self.store = ConfigStore(self.folder / 'providers.json')
        self.save()
        for pid in ('primary', 'backup'):
            self.store.save_key(pid, 'fake-local-' + pid)

    def save(self):
        self.store.save(self.config)

    def handler(self, request):
        self.calls.append((request.method, request.url.host))
        return httpx.Response(200, json=self.payload)

    def engine(self, runtime='runtime', handler=None):
        return Engine(self.store, self.folder / runtime,
                      lambda p, k: Protocol(p, k, httpx.MockTransport(handler or self.handler)))

    def edit(self, engine, **kwargs):
        images = kwargs.pop('images', [self.image])
        return engine.edit(images, mask=self.image, prompt='free local fixture', **kwargs)

    def test_local_template_and_auth_errors_fall_over_without_cooling_primary(self):
        # Break caught: a definitely-unsent client error persists a whole-provider cooldown.
        baseline = copy.deepcopy(self.config)
        for case in ('unmapped_mask', 'unmapped_images', 'template_single_image_only',
                     'missing_upload_config', 'upload_single_image_only', 'invalid_protocol',
                     'invalid_auth_header'):
            with self.subTest(case=case):
                self.config = copy.deepcopy(baseline)
                p = self.config['providers'][0]
                body = p['request']['body']
                images = [self.image]
                if case == 'unmapped_mask':
                    body.pop('mask')
                elif case == 'unmapped_images':
                    body.pop('images')
                elif case == 'template_single_image_only':
                    body['images'] = '{image_base64}'
                    images *= 2
                elif case == 'missing_upload_config':
                    body['images'] = '{image_ref}'
                elif case == 'upload_single_image_only':
                    body['mask'] = '{mask_ref}'
                    p['upload'] = {'path': '/upload'}
                    images *= 2
                elif case == 'invalid_protocol':
                    p['request']['body'] = None
                self.save()
                self.store.save_key('primary', 'fake-local-primary' + ('\x00' if case == 'invalid_auth_header' else ''))
                self.calls.clear()
                engine = self.engine(case)
                first = self.edit(engine, images=images, request_nonce=1)
                self.assertEqual(first['report']['status'], 'success')
                self.assertEqual(first['report']['provider'], 'backup')
                self.assertEqual(first['report']['attempts'][0]['error'], case)
                self.assertEqual(self.calls, [('POST', 'backup.invalid')])
                self.assertTrue(engine.journal.available('primary'), case)
                # Correcting the client mapping/key permits a new low-cost primary task.
                self.config = copy.deepcopy(baseline)
                self.save()
                self.store.save_key('primary', 'fake-local-primary')
                self.calls.clear()
                corrected = self.edit(self.engine(case), images=images, request_nonce=2, max_cost=0.2)
                self.assertEqual(corrected['report']['status'], 'success')
                self.assertEqual(corrected['report']['provider'], 'primary')
                self.assertEqual(corrected['report']['estimated_cost'], 0.1)
                self.assertEqual(self.calls, [('POST', 'primary.invalid')])

    def test_pool_timeout_is_safe_to_fail_over_but_does_not_cool_primary(self):
        # Break caught: local HTTP pool contention is mistaken for provider unavailability.
        def handler(request):
            if request.url.host == 'primary.invalid':
                raise httpx.PoolTimeout('synthetic local pool contention', request=request)
            return self.handler(request)
        engine = self.engine(handler=handler)
        result = self.edit(engine)
        self.assertEqual(result['report']['provider'], 'backup')
        self.assertEqual(result['report']['attempts'][0]['error'], 'request_not_sent')
        self.assertTrue(engine.journal.available('primary'))
        self.assertEqual(self.calls, [('POST', 'backup.invalid')])

    def test_connection_failure_still_falls_over_and_cools_primary(self):
        # Break caught: removing all unsent cooldowns hides real failed connections.
        for error_type in (httpx.ConnectError, httpx.ConnectTimeout):
            with self.subTest(error=error_type.__name__):
                def handler(request):
                    if request.url.host == 'primary.invalid':
                        raise error_type('synthetic connection failure', request=request)
                    return self.handler(request)
                engine = self.engine(error_type.__name__, handler)
                result = self.edit(engine)
                self.assertEqual(result['report']['provider'], 'backup')
                self.assertEqual(result['report']['attempts'][0]['error'], 'request_not_sent')
                self.assertFalse(engine.journal.available('primary'))

    def test_configured_remote_safe_rejection_still_releases_and_cools(self):
        # Break caught: safe remote refusal must retain failover and cooldown semantics.
        self.config['max_total_cost'] = 0.7
        self.save()
        def handler(request):
            if request.url.host == 'primary.invalid':
                return httpx.Response(401, json={'error': 'explicit non-acceptance'})
            return self.handler(request)
        engine = self.engine(handler=handler)
        result = self.edit(engine)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(result['report']['provider'], 'backup')
        self.assertFalse(engine.journal.available('primary'))
        self.assertEqual(engine.journal.get(result['report']['request_id'])['reserved_cost'], 0.7)

    def test_uncertain_and_accepted_tasks_keep_claim_without_backup(self):
        # Break caught: health classification must never release an ambiguous/accepted claim.
        for state in ('uncertain', 'accepted'):
            with self.subTest(state=state):
                p = self.config['providers'][0]
                p.pop('async', None)
                if state == 'accepted':
                    p['async'] = {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}',
                        'status_path': 'status', 'max_polls': 1, 'poll_interval': 0}
                self.save()
                calls = []
                def handler(request):
                    calls.append((request.method, request.url.host))
                    if state == 'uncertain':
                        return httpx.Response(500, json={'error': 'ambiguous'})
                    return httpx.Response(200, json={'id': 'accepted-job'} if request.method == 'POST' else {'status': 'pending'})
                engine = self.engine(state, handler)
                self.edit(engine, request_nonce=1)
                self.edit(self.engine(state, handler), request_nonce=1)
                row = engine.journal.get(self.edit(self.engine(state, handler), request_nonce=1)['report']['request_id'])
                self.assertEqual(row['state'], state)
                self.assertEqual(row['reserved_cost'], 0.1)
                self.assertEqual([call for call in calls if call[0] == 'POST'], [('POST', 'primary.invalid')])
                self.assertTrue(engine.journal.available('primary'))

if __name__ == '__main__':
    unittest.main()
