import importlib.util
import json
import unittest
from pathlib import Path


class NodeContractTests(unittest.TestCase):
    def test_workflow_interface_has_no_secret_widgets_and_standard_ports(self):
        root = Path(__file__).resolve().parents[1]
        self.assertTrue((root / '__init__.py').exists(), 'ComfyUI package entrypoint missing')
        spec = importlib.util.spec_from_file_location('h3_test_plugin', root / '__init__.py', submodule_search_locations=[str(root)])
        import sys
        plugin = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = plugin
        spec.loader.exec_module(plugin)
        cls = plugin.NODE_CLASS_MAPPINGS['H3ImageEdit']
        inputs = cls.INPUT_TYPES()
        self.assertEqual(inputs['required']['image'], ('IMAGE',))
        self.assertEqual(inputs['optional']['mask'], ('MASK',))
        self.assertEqual(cls.RETURN_TYPES, ('IMAGE', 'STRING', 'STRING'))
        text = json.dumps(inputs).lower()
        self.assertNotIn('api_key', text)
        self.assertNotIn('base_url', text)
        self.assertIn('request_nonce', inputs['required'])


if __name__ == '__main__':
    unittest.main()
