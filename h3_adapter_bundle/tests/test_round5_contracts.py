"""Input mapping, local multipart errors and credential write contracts."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import os
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from mock_api import MockAPI, PNG_BYTES
from test_config import config, provider

WORK = Path(__file__).resolve().parents[2] / 'work' / 'tmp'

class InputContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=WORK)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.api = MockAPI()
        self.addCleanup(self.api.close)
        self.store = ConfigStore(self.root / 'providers.json')
        self.cfg = config()
        self.cfg['providers'] = [provider('primary'), provider('backup')]
        self.cfg['fallbacks'] = ['backup']
        for p in self.cfg['providers']:
            p.update(base_url=self.api.url(p['id']), key_env='', allow_insecure_localhost=True)
            p['models']['background-edit'].update(supports_mask=True, allowed_params=['quality'])
        self.store.save(self.cfg)
        for p in self.cfg['providers']:
            self.store.save_key(p['id'], 'ROUND5-SYNTHETIC-FAKE')
        self.engine = Engine(self.store, self.root / 'runtime')

    def edit(self, **kw):
        return self.engine.edit([PNG_BYTES], prompt=kw.pop('prompt', 'user prompt'), timeout_seconds=3, **kw)

    def test_bad_multipart_fields_never_submit_or_cool_primary(self):
        for nonce, value in enumerate((42, [], {}, '', 'bad\nfield')):
            with self.subTest(value=value):
                self.cfg['providers'][0]['request'] = {'image_field': value}
                self.store.save(self.cfg)
                self.api.requests.clear()
                result = self.edit(request_nonce=nonce)
                self.assertEqual(result['report']['status'], 'success')
                self.assertEqual(result['report']['attempts'][0]['error'], 'invalid_multipart_field')
                self.assertEqual([r['provider'] for r in self.api.calls(method='POST')], ['backup'])
                self.assertTrue(self.engine.journal.available('primary'))
                row = self.engine.journal.get(result['report']['request_id'])
                self.assertEqual(row['state'], 'completed')
                self.assertAlmostEqual(row['reserved_cost'], 0.1)

    def test_bad_auth_header_name_is_rejected_before_storage(self):
        from h3_adapter.config import ConfigError
        original = self.store.path.read_bytes()
        for value in (42, [], {}, False, 'bad header', 'bad\nheader', 'bad:header', '中文'):
            with self.subTest(header=value):
                self.cfg['providers'][0]['auth'] = {'header': value, 'prefix': 'Bearer '}
                with self.assertRaises(ConfigError):
                    self.store.save(self.cfg)
                self.assertEqual(self.store.path.read_bytes(), original)
                self.assertEqual(self.api.calls(), [])

    def test_bad_mask_field_never_submits(self):
        self.cfg['providers'][0]['request'] = {'image_field': 'image[]', 'mask_field': False}
        self.store.save(self.cfg)
        result = self.edit(mask=PNG_BYTES)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(result['report']['attempts'][0]['error'], 'invalid_multipart_field')
        self.assertEqual([r['provider'] for r in self.api.calls(method='POST')], ['backup'])

    def test_bad_upload_field_never_uploads_or_submits(self):
        p = self.cfg['providers'][0]
        p.update(protocol='json_template', request={'body': {'model': '{model}', 'prompt': '{prompt}', 'image': '{image_ref}'}},
                 upload={'path': '/upload', 'field': 42, 'ref_path': 'url'})
        self.store.save(self.cfg)
        result = self.edit()
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual([r['provider'] for r in self.api.calls(method='POST')], ['backup'])
        self.assertTrue(self.engine.journal.available('primary'))

    def test_fixed_json_fields_remain_legal_but_are_reported(self):
        p = self.cfg['providers'][0]
        p.update(protocol='json_template', request={'body': {'model': 'fixed-model-B', 'prompt': 'fixed prompt', 'image': '{image_base64}'}})
        self.store.save(self.cfg)
        result = self.edit(params={'quality': 'high'})
        self.assertEqual(result['report']['status'], 'success')
        actual = json.loads(self.api.calls(method='POST')[0]['body'])
        self.assertEqual(actual['model'], 'fixed-model-B')
        self.assertEqual(actual['prompt'], 'fixed prompt')
        self.assertEqual(result['report']['model'], 'edit-model')
        self.assertEqual(set(result['report'].get('warnings', [])), {'json_template_unmapped_model', 'json_template_unmapped_prompt', 'json_template_unmapped_parameters'})
        self.api.requests.clear()
        cached = self.edit(params={'quality': 'high'})
        self.assertTrue(cached['report']['cached'])
        self.assertEqual(cached['report']['warnings'], result['report']['warnings'])
        self.assertEqual(self.api.calls(), [])
        print(json.dumps({'captured_fixed_body': actual, 'mapped_model': result['report']['model'], 'warnings': result['report']['warnings']}))

    def test_fixed_template_warnings_survive_async_recovery(self):
        p = self.cfg['providers'][0]
        p.update(protocol='json_template', request={'body': {'model': 'fixed-B', 'prompt': 'literal {prompt}', 'image': '{image_base64}'}},
                 **{'async': {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}', 'status_path': 'status',
                              'success': ['succeeded'], 'failure': ['failed'], 'max_polls': 1, 'poll_interval': 0}})
        self.store.save(self.cfg)
        self.api.set_plan('primary', **{'async': True, 'task_status': 'pending'})
        first = self.edit(params={'quality': 'high'})
        self.assertEqual(first['report']['status'], 'awaiting_result')
        self.assertEqual(len(first['report']['warnings']), 3)
        self.api.complete()
        self.engine = Engine(self.store, self.root / 'runtime')
        recovered = self.edit(params={'quality': 'high'})
        self.assertEqual(recovered['report']['status'], 'success')
        self.assertEqual(recovered['report']['warnings'], first['report']['warnings'])
        self.assertEqual(len(self.api.calls(method='POST')), 1)
        body = json.loads(self.api.calls(method='POST')[0]['body'])
        self.assertEqual(body['prompt'], 'literal {prompt}')

    def test_nested_tokens_follow_changed_user_input(self):
        p = self.cfg['providers'][0]
        p.update(protocol='json_template', request={'body': {'input': [{'modelId': '{model}', 'text': '{prompt}', 'image': '{image_base64}', 'options': '{params}'}]}})
        self.store.save(self.cfg)
        first = self.edit(prompt='first', params={'quality': 'high'})
        p['models']['background-edit']['id'] = 'model-C'
        self.store.save(self.cfg)
        second = self.edit(prompt='second', params={'quality': 'low'})
        bodies = [json.loads(r['body'])['input'][0] for r in self.api.calls(method='POST')]
        self.assertEqual([(x['modelId'], x['text'], x['options']) for x in bodies], [('edit-model', 'first', {'quality': 'high'}), ('model-C', 'second', {'quality': 'low'})])
        self.assertEqual(first['report'].get('warnings', []), [])
        self.assertEqual(second['report'].get('warnings', []), [])

    def test_key_writes_preserve_other_providers_and_allow_last_writer(self):
        revision = self.store.public()['revision']
        self.store.save_key('primary', 'ROUND5-FIRST', revision)
        self.store.save_key('primary', 'ROUND5-LAST', revision)
        self.assertEqual(self.store.key(self.cfg['providers'][0]), 'ROUND5-LAST')
        self.assertEqual(self.store.public()['revision'], revision)
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda pid: self.store.save_key(pid, 'ROUND5-' + pid, revision), ('primary', 'backup')))
        self.assertEqual(json.loads(self.store.secret_path.read_text()), {'primary': 'ROUND5-primary', 'backup': 'ROUND5-backup'})
        with patch.dict(os.environ, {'ROUND5_ENV': 'ROUND5-ENV-VALUE'}):
            p = copy.deepcopy(self.cfg['providers'][0]); p['key_env'] = 'ROUND5_ENV'
            self.assertEqual(self.store.key(p), 'ROUND5-ENV-VALUE')

if __name__ == '__main__':
    unittest.main()
