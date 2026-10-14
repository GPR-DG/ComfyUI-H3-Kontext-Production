"""Integrated package contracts; synthetic credentials and CPU tensors only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'H3ImageEdit', 'H3A2Recipe', 'H3A2BackgroundResolve',
         'H3A2BackgroundWashClaim', 'H3A2APISource', 'H3A2APIGuard',
         'H3A2PromptCapture', 'H3A2BackgroundFinish'}


K_NAMES = {'H3KBackgroundResolve', 'H3KBackgroundWashClaim', 'H3KBackgroundFinish',
          'H3KBackgroundSource', 'H3KStageGuard', 'H3KRecipe',
          'H3KPromptCapture', 'H3KStagePreview'}


class IntegratedBridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location(
            '_integrated_bridge_tests', ROOT / '__init__.py',
            submodule_search_locations=[str(ROOT)])
        cls.plugin = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.plugin
        spec.loader.exec_module(cls.plugin)
        cls.api = sys.modules[spec.name + '.nodes']
        cls.bridge = sys.modules[spec.name + '.h3_background_bridge.nodes']

    def test_single_package_registration_without_core(self):
        self.assertEqual(set(self.plugin.NODE_CLASS_MAPPINGS), NAMES | K_NAMES)
        self.assertEqual(set(self.plugin.NODE_DISPLAY_NAME_MAPPINGS), NAMES | K_NAMES)
        self.assertEqual(self.plugin.WEB_DIRECTORY, './web')
        js = (ROOT / 'web/h3_adapter.js').read_text(encoding='utf-8')
        for label in ('H3 供应商 / 密钥', 'H3 搜索 / 选择模型'):
            self.assertIn(label, js)

    def test_exact_source_pins_and_tamper_rejection(self):
        mappings = self.plugin.NODE_CLASS_MAPPINGS
        with patch.object(self.bridge, 'registry', return_value=mappings):
            self.assertIs(self.bridge.adapter(), self.api)
            real_file = self.api.__file__
            pins = json.loads((ROOT / 'h3_background_bridge/adapter-required-sha256.json').read_text())
            self.assertEqual(set(pins), {'nodes.py', 'h3_adapter/config.py',
                'h3_adapter/engine.py', 'h3_adapter/protocol.py',
                'h3_adapter/ledger.py', 'h3_adapter/routes.py'})
            with tempfile.TemporaryDirectory() as folder:
                fake = Path(folder)
                for name, expected in pins.items():
                    data = (ROOT / name).read_bytes()
                    self.assertNotIn(b'\r\n', data)
                    self.assertEqual(hashlib.sha256(data).hexdigest(), expected)
                    (fake / name).parent.mkdir(parents=True, exist_ok=True)
                    (fake / name).write_bytes(data)
                (fake / 'h3_adapter/config.py').write_bytes(b'# tampered\n')
                with patch.object(self.api, '__file__', str(fake / 'nodes.py')):
                    with self.assertRaisesRegex(RuntimeError, 'config.py'):
                        self.bridge.adapter()
            self.assertEqual(self.api.__file__, real_file)

    def test_recipe_snapshot_key_rotation_and_z_separation(self):
        with tempfile.TemporaryDirectory() as folder:
            store = self.api.ConfigStore(Path(folder) / 'providers.json')
            config = json.loads((ROOT / 'config/providers.example.json').read_text())
            config['providers'][0].update(enabled=True, key_env='')
            store.save(config)
            store.save_key(config['providers'][0]['id'], 'SYNTHETIC-INTEGRATION-A')
            prompt = {'api': {'class_type': 'H3ImageEdit', 'inputs': {
                'provider': 'auto', 'model_alias': 'background-edit', 'parameters': '{}'}},
                'z': {'class_type': 'KSampler', 'inputs': {'seed': 17, 'steps': 8}}}
            with patch.object(self.api, 'STORE', store), patch.object(
                    self.bridge, 'registry', return_value=self.plugin.NODE_CLASS_MAPPINGS):
                run = lambda: self.bridge.H3A2Recipe().run(.86, 'remove people', 'api', 'z', 0, prompt)
                first = run()
                self.assertEqual(first, run())
                prompt['z']['inputs']['steps'] = 9
                z_changed = run()
                self.assertNotEqual(first[0], z_changed[0])
                self.assertEqual(first[1:], z_changed[1:])
                store.save_key(config['providers'][0]['id'], 'SYNTHETIC-INTEGRATION-B')
                rotated = run()
                self.assertNotEqual(z_changed[0], rotated[0])
                self.assertEqual(z_changed[1:], rotated[1:])
                self.assertNotIn('SYNTHETIC-INTEGRATION', repr(rotated))
                credential = store.credential
                def race(provider, **kwargs):
                    changed = store.load()
                    changed['providers'][0]['base_url'] = 'https://synthetic-changed.example.invalid'
                    store.save(changed)
                    return credential(provider, **kwargs)
                from importlib import import_module
                conflict = import_module(self.api.ConfigStore.__module__).ConfigConflict
                with patch.object(store, 'credential', side_effect=race):
                    with self.assertRaises(conflict):
                        run()

    def test_aspect_ratio_guard_and_failed_output_boundary(self):
        task = types.SimpleNamespace(cleaned=False, task_id='synthetic-task')
        view = types.SimpleNamespace(task_id=task.task_id, view_id='synthetic-view',
            candidate=types.SimpleNamespace(image=np.zeros((32, 18, 3), np.float32)))
        guard = self.bridge.H3A2APIGuard()
        with self.assertRaisesRegex(ValueError, 'aspect ratio'):
            guard.run(task, view, torch.zeros((1, 32, 32, 3)), '{"status":"success"}')
        self.assertNotIn(view.view_id, self.bridge.state(task)['api'])
        for status in ('failed', 'uncertain', 'awaiting_result'):
            with self.assertRaisesRegex(RuntimeError, 'unavailable'):
                guard.run(task, view, torch.zeros((0, 32, 18, 3)), json.dumps({'status': status}))
        # Near ratios and inconsistent batches must not be coerced into a scene.
        for invalid in (torch.zeros((1, 320, 181, 3)), torch.zeros((2, 32, 18, 3)),
                        torch.empty((1, 0, 18, 3)), torch.full((1, 32, 18, 3), float('nan'))):
            with self.assertRaises((ValueError, RuntimeError)):
                guard.run(task, view, invalid, '{"status":"success"}')
            self.assertNotIn(view.view_id, self.bridge.state(task)['api'])
        resized = guard.run(task, view, torch.zeros((1, 64, 36, 3)), '{"status":"success"}')[0]
        self.assertEqual(tuple(resized.shape), (1, 32, 18, 3))

    def test_release_includes_bridge_workflow_and_exact_pins(self):
        import shutil
        import zipfile
        from scripts.build_release import RELEASE_FILES, build
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'source'
            for name in RELEASE_FILES:
                path = ROOT / name
                if path.is_file():
                    (source / name).parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(path, source / name)
            result = build(source, Path(folder) / 'release')
            with zipfile.ZipFile(result['path']) as archive:
                prefix = 'ComfyUI-H3-Adapter/'
                pins = json.loads(archive.read(prefix + 'h3_background_bridge/adapter-required-sha256.json'))
                for name, expected in pins.items():
                    self.assertEqual(hashlib.sha256(archive.read(prefix + name)).hexdigest(), expected)
                self.assertIn(prefix + 'h3_background_bridge/nodes.py', archive.namelist())
                workflow = json.loads(archive.read(prefix + 'workflows/H3_A2_API_ZImage_BackgroundCache_INTEGRATED.json'))
                self.assertEqual(len(workflow['nodes']), 121)
                self.assertEqual(len(workflow['links']), 251)
                self.assertTrue(all(not p['enabled'] for p in json.loads(archive.read(prefix + 'config/providers.json'))['providers']))

    def test_workflow_class_names_and_counts(self):
        workflow = json.loads((ROOT / 'workflows/H3_A2_API_ZImage_BackgroundCache_INTEGRATED.json').read_text(encoding='utf-8'))
        self.assertEqual(len(workflow['nodes']), 121)
        self.assertEqual(len(workflow['links']), 251)
        types_used = {node['type'] for node in workflow['nodes']}
        self.assertTrue(NAMES <= types_used)
        self.assertEqual(workflow['extra']['integrated_repository']['adapter_required_sha256'],
            json.loads((ROOT / 'h3_background_bridge/adapter-required-sha256.json').read_text()))


if __name__ == '__main__':
    unittest.main()

