"""PNG/Mask boundary tests; ArrayInput is a NumPy port double, not a Torch runtime claim."""
import base64
import importlib.util
import io
import sys
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path
import httpx
import numpy as np
from PIL import Image
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
from test_config import config


def plugin():
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location('h3_mask_plugin', root / '__init__.py', submodule_search_locations=[str(root)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return sys.modules[spec.name + '.nodes']


class ArrayInput:
    def __init__(self, value): self.value = value
    def detach(self): return self
    def cpu(self): return self
    def numpy(self): return self.value


class MaskTests(unittest.TestCase):
    def test_comfy_white_mask_encodes_transparent_edit_alpha(self):
        module = plugin()
        images, mask = module.png_inputs(ArrayInput(np.zeros((1, 1, 2, 3))), ArrayInput(np.array([[0., 1.]])))
        with Image.open(io.BytesIO(mask)) as decoded:
            self.assertEqual(np.array(decoded.getchannel('A')).flatten().tolist(), [255, 0])
        self.assertEqual(len(images), 1)

    def test_declared_grayscale_mask_is_translated_per_provider_model(self):
        images, mask = plugin().png_inputs(ArrayInput(np.zeros((1, 1, 2, 3))), ArrayInput(np.array([[0., 1.]])))
        observed = []
        def handler(request):
            envelope = BytesParser(policy=policy.default).parsebytes(('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + request.content)
            part = next(p for p in envelope.iter_parts() if p.get_param('name', header='content-disposition') == 'mask')
            with Image.open(io.BytesIO(part.get_payload(decode=True))) as decoded:
                observed.append((decoded.mode, np.array(decoded).flatten().tolist()))
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(images[0]).decode()}]})
        with tempfile.TemporaryDirectory() as d:
            store = ConfigStore(Path(d) / 'providers.json')
            cfg = config()
            p = cfg['providers'][0]
            p['key_env'] = ''
            p['models']['background-edit'].update(supports_mask=True, mask_encoding='grayscale_white_edit')
            store.save(cfg); store.save_key('primary', 'fake-mask-key')
            result = Engine(store, Path(d) / 'runtime', lambda p, k: Protocol(p, k, transport=httpx.MockTransport(handler))).edit(images, mask, 'edit background')
            self.assertEqual(result['report']['status'], 'success')
            self.assertEqual(observed, [('L', [0, 255])])

    @unittest.skipUnless(importlib.util.find_spec('torch'), 'Real PyTorch not installed; tensor/ComfyUI runtime check pending')
    def test_real_torch_image_output_has_standard_bhwc_shape(self):
        import torch
        module = plugin()
        original = torch.zeros((1, 2, 3, 3))
        images, _ = module.png_inputs(original)
        output = module.image_tensor(images, original.shape)
        self.assertEqual(tuple(output.shape), (1, 2, 3, 3))
        self.assertEqual(output.dtype, torch.float32)
        self.assertTrue(torch.equal(output, original))


if __name__ == '__main__': unittest.main()
