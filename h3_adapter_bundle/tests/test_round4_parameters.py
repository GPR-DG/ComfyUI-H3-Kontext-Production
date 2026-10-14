"""Invalid JSON parameter values must not become a paid empty-object request."""
import base64
import json
import tempfile
import unittest
from pathlib import Path

import httpx
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
from mock_api import PNG_BYTES
from test_config import config


class ParameterBoundaryTests(unittest.TestCase):
    def execute(self, params):
        self.calls = []
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        with tempfile.TemporaryDirectory(dir=work) as folder:
            store = ConfigStore(Path(folder) / 'providers.json')
            cfg = config()
            cfg['providers'][0]['key_env'] = ''
            store.save(cfg)
            store.save_key('primary', 'synthetic-round4-only')
            def handler(request):
                self.calls.append(request.method)
                return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(PNG_BYTES).decode()}]})
            engine = Engine(store, Path(folder) / 'runtime',
                            lambda p, k: Protocol(p, k, transport=httpx.MockTransport(handler)))
            result = engine.edit([PNG_BYTES], prompt='free simulated edit', params=params)
            self.state_count = engine.journal.get(result['report']['request_id']) if result['report']['request_id'] else None
            return result

    def test_non_object_json_parameters_are_rejected_before_submission(self):
        # json.loads is the actual node's parameter parser; falsey values used to bypass Engine validation.
        for encoded in ('[]', 'false', '0', '""', '[1]', 'true', '"value"'):
            with self.subTest(parameters=encoded):
                result = self.execute(json.loads(encoded))
                self.assertEqual(result['report']['status'], 'failed')
                self.assertEqual(result['report']['error'], 'invalid_prompt_or_parameters')
                self.assertEqual(self.calls, [])
                self.assertIsNone(self.state_count)

    def test_optional_none_and_empty_object_keep_supported_default(self):
        for value in (None, {}):
            with self.subTest(params=value):
                result = self.execute(value)
                self.assertEqual(result['report']['status'], 'success')
                self.assertEqual(result['images'], [PNG_BYTES])
                self.assertEqual(self.calls, ['POST'])


if __name__ == '__main__':
    unittest.main()
