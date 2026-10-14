"""Round 3: real Engine/Protocol request captures, never live/paid APIs."""
import base64
import copy
import io
import json
import tempfile
import unittest
from email import policy
from email.parser import BytesParser
from pathlib import Path

import httpx
from PIL import Image
from h3_adapter.config import ConfigStore
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol


def png(color):
    buffer = io.BytesIO()
    Image.new('RGBA', (2, 2), color).save(buffer, 'PNG')
    return buffer.getvalue()


IMAGE, SECOND, MASK = png((0, 0, 255, 255)), png((255, 0, 0, 255)), png((0, 0, 0, 0))
INLINE = {'model': '{model}', 'prompt': '{prompt}', 'image': '{image_base64}'}


class TemplateMappingTests(unittest.TestCase):
    def execute(self, body, *, mask=MASK, images=None, upload=False, params=None,
                fallback=False, provider='auto', protocol='json_template'):
        self.calls = []
        def handler(request):
            call = {'method': request.method, 'path': request.url.path}
            if 'application/json' in request.headers.get('content-type', ''):
                call['json'] = json.loads(request.content)
            else:
                envelope = BytesParser(policy=policy.default).parsebytes(
                    ('Content-Type: ' + request.headers['content-type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + request.content)
                call['parts'] = {part.get_filename(): part.get_payload(decode=True)
                                 for part in envelope.iter_parts() if part.get_filename()}
            self.calls.append(call)
            if request.url.path.endswith('/upload'):
                return httpx.Response(200, json={'url': 'ref-' + str(len(self.calls))})
            return httpx.Response(200, json={'data': [{'b64_json': base64.b64encode(IMAGE).decode()}]})
        p = {'id': 'primary', 'base_url': 'https://mock.invalid/primary', 'key_env': '',
             'protocol': protocol, 'edit_path': '/edit', 'request': {'body': body},
             'models': {'background-edit': {'id': 'mock-editor', 'task': 'image_edit',
                 'supports_mask': True, 'max_images': 2, 'price_upper_bound': 0,
                 'allowed_params': list((params or {}).keys()), 'defaults': {}}}}
        if upload:
            p['upload'] = {'path': '/upload', 'field': 'file', 'ref_path': 'url'}
        cfg = {'version': 1, 'primary': 'primary', 'fallbacks': [], 'providers': [p]}
        if fallback:
            backup = copy.deepcopy(p)
            backup.update(id='backup', base_url='https://mock.invalid/backup',
                          request={'body': {**INLINE, 'mask': '{mask_base64}'}})
            cfg['providers'].append(backup)
            cfg['fallbacks'] = ['backup']
        work = Path(__file__).resolve().parents[2] / 'work' / 'tmp'
        with tempfile.TemporaryDirectory(dir=work) as d:
            store = ConfigStore(Path(d) / 'providers.json')
            store.save(cfg)
            for item in cfg['providers']:
                store.save_key(item['id'], 'fake-round3-mock')
            engine = Engine(store, Path(d) / 'runtime', lambda p, k: Protocol(p, k, transport=httpx.MockTransport(handler)))
            return engine.edit(images or [IMAGE], mask=mask, prompt='edit region',
                               params=params or {}, provider=provider, timeout_seconds=10)

    def rejected_without_http(self, body, error, **kwargs):
        result = self.execute(body, **kwargs)
        self.assertEqual(result['report']['status'], 'no_provider')
        self.assertEqual(result['images'], [])
        self.assertEqual(result['report']['attempts'][0]['error'], error)
        self.assertEqual(self.calls, [])

    def test_missing_mask_never_posts(self):
        self.rejected_without_http(INLINE, 'unmapped_mask')

    def test_mask_key_and_embedded_strings_are_not_mapping(self):
        for body in [{**INLINE, '{mask_base64}': 'literal'}, {**INLINE, 'mask': 'prefix {mask_base64}'}]:
            with self.subTest(body=body):
                self.rejected_without_http(body, 'unmapped_mask')

    def test_params_are_not_recursively_interpolated(self):
        for body in [INLINE, {**INLINE, 'parameters': '{params}'}]:
            with self.subTest(body=body):
                self.rejected_without_http(body, 'unmapped_mask', params={'region': '{mask_base64}'})

    def test_missing_mask_mapping_rejected_before_any_upload(self):
        self.rejected_without_http({'image': '{image_ref}'}, 'unmapped_mask', upload=True)

    def test_bad_primary_mapping_uses_only_valid_backup_post(self):
        result = self.execute(INLINE, upload=True, fallback=True)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(result['report']['provider'], 'backup')
        self.assertEqual(result['report']['attempts'][0]['error'], 'unmapped_mask')
        self.assertEqual([(x['method'], x['path']) for x in self.calls], [('POST', '/backup/edit')])
        self.assertEqual(self.calls[0]['json']['mask'], base64.b64encode(MASK).decode())

    def test_fixed_bad_provider_cannot_submit_or_use_backup(self):
        self.rejected_without_http(INLINE, 'unmapped_mask', upload=True, fallback=True, provider='primary')

    def test_missing_key_embedded_and_params_image_are_not_mapping(self):
        for body in [{'mask': '{mask_base64}'}, {'{image_base64}': 'literal', 'mask': '{mask_base64}'},
                     {'image': 'prefix {image_base64}', 'mask': '{mask_base64}'},
                     {'parameters': '{params}', 'mask': '{mask_base64}'}]:
            with self.subTest(body=body):
                self.rejected_without_http(body, 'unmapped_images', params={'source': '{image_base64}'})

    def test_multiple_images_require_all_image_mapping_before_upload(self):
        self.rejected_without_http({**INLINE, 'mask': '{mask_base64}'}, 'template_single_image_only', images=[IMAGE, SECOND])

    def test_nested_mask_mapping_preserves_bytes(self):
        result = self.execute({**INLINE, 'nested': [{'region': '{mask_data_url}'}]})
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(self.calls[0]['json']['nested'][0]['region'], 'data:image/png;base64,' + base64.b64encode(MASK).decode())

    def test_all_image_mapping_preserves_both_images(self):
        result = self.execute({'nested': [{'images': '{images_data_urls}', 'mask': '{mask_base64}'}]}, images=[IMAGE, SECOND])
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(self.calls[0]['json']['nested'][0]['images'], ['data:image/png;base64,' + base64.b64encode(x).decode() for x in [IMAGE, SECOND]])

    def test_upload_references_preserve_image_and_mask(self):
        result = self.execute({'image': '{image_ref}', 'mask': '{mask_ref}'}, upload=True)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual([x['path'] for x in self.calls], ['/primary/upload', '/primary/upload', '/primary/edit'])
        self.assertEqual(self.calls[0]['parts']['image.png'], IMAGE)
        self.assertEqual(self.calls[1]['parts']['mask.png'], MASK)
        self.assertEqual(self.calls[2]['json'], {'image': 'ref-1', 'mask': 'ref-2'})

    def test_ref_token_needs_upload_before_any_http(self):
        self.rejected_without_http({'image': '{image_ref}', 'mask': '{mask_base64}'}, 'missing_upload_config')

    def test_upload_reference_single_image_boundary_remains(self):
        self.rejected_without_http({'images': '{images_data_urls}', 'mask': '{mask_ref}'}, 'upload_single_image_only', upload=True, images=[IMAGE, SECOND])

    def test_no_mask_input_does_not_require_mask_mapping(self):
        result = self.execute(INLINE, mask=None)
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(len(self.calls), 1)

    def test_literal_reference_keys_and_embedded_text_do_not_require_upload(self):
        result = self.execute({**INLINE, 'mask': '{mask_base64}', '{image_ref}': 'literal', 'annotation': 'literal {mask_ref}'})
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]['json']['annotation'], 'literal {mask_ref}')

    def test_inline_mapping_with_unused_upload_config_has_no_extra_post(self):
        result = self.execute({'images': '{images_data_urls}', 'mask': '{mask_base64}'}, upload=True, images=[IMAGE, SECOND])
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual([x['path'] for x in self.calls], ['/primary/edit'])

    def test_mixed_mapping_uploads_only_actual_reference(self):
        for body, filename in [({**INLINE, 'mask': '{mask_ref}'}, 'mask.png'),
                               ({'image': '{image_ref}', 'mask': '{mask_base64}'}, 'image.png')]:
            with self.subTest(body=body):
                result = self.execute(body, upload=True)
                self.assertEqual(result['report']['status'], 'success')
                self.assertEqual([x['path'] for x in self.calls], ['/primary/upload', '/primary/edit'])
                self.assertEqual(set(self.calls[0]['parts']), {filename})

    def test_multipart_mapping_remains_complete(self):
        result = self.execute(None, protocol='openai_images', images=[IMAGE, SECOND])
        self.assertEqual(result['report']['status'], 'success')
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.calls[0]['parts'], {'image_0.png': IMAGE, 'image_1.png': SECOND, 'mask.png': MASK})


if __name__ == '__main__':
    unittest.main()
