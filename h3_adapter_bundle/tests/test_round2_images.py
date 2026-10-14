"""Round-2 adapter boundaries: returned size/mask guidance are not local compositing."""
import base64
import io
import tempfile
import unittest
from pathlib import Path
import httpx
from PIL import Image
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine, valid_image
from h3_adapter.protocol import Protocol
from test_config import config

def png(size, color, mode="RGB"):
    stream = io.BytesIO()
    Image.new(mode, size, color).save(stream, "PNG")
    return stream.getvalue()

class ImageBoundaryTests(unittest.TestCase):
    def run_edit(self, original, returned, mask=None):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        store = ConfigStore(Path(folder.name) / "providers.json")
        cfg = config()
        cfg["providers"][0]["key_env"] = ""
        cfg["providers"][0]["models"]["background-edit"]["supports_mask"] = True
        store.save(cfg)
        store.save_key("primary", "round2-synthetic")
        observed = []
        def handler(request):
            observed.append(request.content)
            return httpx.Response(200, json={"data":[{"b64_json":base64.b64encode(returned).decode()}]})
        engine = Engine(store, Path(folder.name) / "runtime",
                        lambda p,k: Protocol(p,k,transport=httpx.MockTransport(handler)))
        result = engine.edit([original], mask=mask, prompt="edit")
        self.assertEqual(result["report"]["status"], "success")
        self.assertEqual(len(observed), 1)
        return result, observed[0]

    def test_upstream_different_dimensions_are_preserved_without_resize(self):
        source = png((16, 8), "red")
        returned = png((4, 6), "blue")
        result, _ = self.run_edit(source, returned)
        self.assertEqual(valid_image(source), (16, 8))
        self.assertEqual(valid_image(result["images"][0]), (4, 6))
        self.assertEqual(result["images"], [returned])

    def test_mask_is_forwarded_but_adapter_does_not_fake_unmasked_preservation(self):
        source = png((2, 2), "red")
        returned = png((2, 2), "blue")
        mask = png((2, 2), (0,0,0,255), "RGBA")
        result, body = self.run_edit(source, returned, mask)
        self.assertIn(b'name="mask"', body)
        self.assertIn(mask, body)
        with Image.open(io.BytesIO(result["images"][0])) as output:
            self.assertEqual(output.getpixel((0,0)), (0,0,255))
        self.assertEqual(result["images"], [returned])

if __name__ == "__main__":
    unittest.main()
