import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from h3_adapter.config import ConfigStore, ConfigError


def provider(pid='primary'):
    return {'id': pid, 'base_url': 'https://api.example.invalid/v1', 'key_env': 'H3_TEST_KEY',
            'protocol': 'openai_images', 'edit_path': '/images/edits', 'enabled': True,
            'models': {'background-edit': {'id': 'edit-model', 'task': 'image_edit',
                        'supports_mask': False, 'max_images': 1, 'price_upper_bound': 0.1,
                        'allowed_params': [], 'defaults': {}}}, 'discovery': None}


def config():
    return {'version': 1, 'primary': 'primary', 'fallbacks': [], 'currency': 'USD',
            'providers': [provider()], 'auto_failover': True, 'timeout_seconds': 30,
            'cooldown_seconds': 30, 'max_total_cost': None}


class ConfigTests(unittest.TestCase):
    def test_save_reload_preserves_config_and_key_stays_private(self):
        with tempfile.TemporaryDirectory() as d:
            store = ConfigStore(Path(d) / 'providers.json')
            store.save(config())
            store.save_key('primary', 'test-secret-value')
            self.assertEqual(ConfigStore(store.path).key(provider()), 'test-secret-value')
            self.assertEqual(store.load()['primary'], 'primary')
            self.assertNotIn('test-secret-value', json.dumps(store.public()))
            self.assertNotIn('test-secret-value', store.path.read_text())

    def test_invalid_types_are_rejected_before_provider_use(self):
        mutations = [
            ('enabled', 'false'), ('base_url', 123), ('base_url', 'https://api.example.invalid:999999/v1'),
            ('auth', {'header': {}, 'prefix': 'Bearer '}), ('auth', {'header': 'Authorization', 'prefix': []}),
            ('async', True), ('safe_reject_statuses', [500]),
        ]
        with tempfile.TemporaryDirectory() as d:
            store = ConfigStore(Path(d) / 'providers.json')
            for name, value in mutations:
                with self.subTest(name=name, value=value):
                    cfg = copy.deepcopy(config())
                    cfg['providers'][0][name] = value
                    with self.assertRaises(ConfigError):
                        store.save(cfg)


if __name__ == '__main__':
    unittest.main()
