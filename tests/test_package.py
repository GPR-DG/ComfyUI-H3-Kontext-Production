"""Deployment registration and exact-source checks; no fabricated node classes."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {'H3CBackgroundTaskStart','H3CBestBackgroundFrame','H3CBackgroundResolve',
 'H3CBackgroundWashClaim','H3CBackgroundFinish','H3CBackgroundTaskCleanup',
 'H3KBackgroundResolve','H3KBackgroundWashClaim','H3KBackgroundFinish',
 'H3KBackgroundSource','H3StageGuard','H3KRecipe','H3KPromptCapture','H3StagePreview'}

class ProductionPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory()
        cls.old_config=os.environ.get('H3_ADAPTER_CONFIG')
        os.environ['H3_ADAPTER_CONFIG']=str(Path(cls.temp.name)/'providers.json')
        spec=importlib.util.spec_from_file_location('_h3_production_test',ROOT/'__init__.py',
            submodule_search_locations=[str(ROOT)])
        cls.plugin=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=cls.plugin
        spec.loader.exec_module(cls.plugin)
    @classmethod
    def tearDownClass(cls):
        if cls.old_config is None: os.environ.pop('H3_ADAPTER_CONFIG',None)
        else: os.environ['H3_ADAPTER_CONFIG']=cls.old_config
        cls.temp.cleanup()
    def test_all_required_keys_are_real_and_callable(self):
        self.assertFalse(REQUIRED-self.plugin.NODE_CLASS_MAPPINGS.keys())
        self.assertFalse(REQUIRED-self.plugin.NODE_DISPLAY_NAME_MAPPINGS.keys())
        for name in REQUIRED:
            node=self.plugin.NODE_CLASS_MAPPINGS[name]
            self.assertTrue(node.INPUT_TYPES())
            self.assertTrue(callable(getattr(node(),node.FUNCTION)))
    def test_aliases_do_not_replace_original_classes_or_contracts(self):
        classes=self.plugin.NODE_CLASS_MAPPINGS
        for alias,original in [('H3CBackgroundFinish','H3CBackgroundAttachClean'),
            ('H3StageGuard','H3KStageGuard'),('H3StagePreview','H3KStagePreview')]:
            self.assertIs(classes[alias],classes[original])
            self.assertEqual(classes[alias].__name__,original)
        self.assertEqual(classes['H3CBackgroundFinish'].RETURN_TYPES,('BACKGROUND_VIEW','IMAGE','STRING'))
        self.assertEqual(classes['H3KBackgroundFinish'].RETURN_TYPES,
            ('BACKGROUND_VIEW','IMAGE','STRING','BOOLEAN','IMAGE','STRING','IMAGE'))
    def test_all_upstream_files_are_byte_exact(self):
        manifest=json.loads((ROOT/'UPSTREAM-MANIFEST.json').read_text())
        self.assertGreater(len(manifest['files']),100)
        for entry in manifest['files']:
            data=(ROOT/entry['path']).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(),entry['sha256'],entry['path'])
            self.assertEqual(hashlib.sha1(f'blob {len(data)}\0'.encode()+data).hexdigest(),
                entry['github_blob_sha'],entry['path'])
    def test_kontext_and_adapter_pins_match_actual_core_and_api(self):
        for pins_path,base in [('h3_adapter_bundle/h3_kontext_bridge/core-required-sha256.json','h3_core'),
            ('h3_adapter_bundle/h3_background_bridge/adapter-required-sha256.json','h3_adapter_bundle')]:
            pins=json.loads((ROOT/pins_path).read_text())
            for name,expected in pins.items():
                self.assertEqual(hashlib.sha256((ROOT/base/name).read_bytes()).hexdigest(),expected,name)
    def test_existing_api_a2_core_and_canonical_kontext_remain_available(self):
        expected={'H3ImageEdit','H3A2BackgroundResolve','H3A2BackgroundFinish','H3CShotPlanner',
            'H3CShotReferenceRouter','H3KStageGuard','H3KStagePreview'}
        self.assertFalse(expected-self.plugin.NODE_CLASS_MAPPINGS.keys())
        self.assertTrue((ROOT/self.plugin.WEB_DIRECTORY/'h3_adapter.js').is_file())

if __name__=='__main__': unittest.main()
