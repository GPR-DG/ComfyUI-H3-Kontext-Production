"""Independent follow-up contracts; loopback HTTP and fake credentials only."""
import base64
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import patch
from PIL import Image
from h3_adapter.config import ConfigStore, ConfigConflict, atomic_json
from h3_adapter.engine import Engine

FA, FB = 'FOLLOWUP-FAKE-OLD', 'FOLLOWUP-FAKE-NEW'

class Peer:
    def __init__(self):
        stream = io.BytesIO(); Image.new('RGB', (5, 3), 'blue').save(stream, 'PNG')
        self.png = stream.getvalue(); self.calls = []; self.complete = False
        peer = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args): pass
            def answer(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                peer.calls.append({'method': self.command, 'path': self.path,
                                   'key': self.headers.get('Authorization'), 'body': body.decode('latin1')})
                result = {'id': 'old-task'} if self.command == 'POST' else {
                    'status': 'succeeded' if peer.complete else 'pending',
                    'data': [{'b64_json': base64.b64encode(peer.png).decode()}]}
                data = json.dumps(result).encode(); self.send_response(200)
                self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(data)))
                self.end_headers(); self.wfile.write(data)
            do_GET = answer
            do_POST = answer
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.url = f'http://127.0.0.1:{self.server.server_port}'
    def close(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()

def provider(pid, url, asynchronous=True):
    p = {'id': pid, 'base_url': url, 'key_env': '', 'enabled': True,
         'allow_insecure_localhost': True, 'protocol': 'openai_images', 'edit_path': '/images/edits',
         'models': {'edit': {'id': 'fake-edit', 'task': 'image_edit', 'price_upper_bound': .1}}}
    if asynchronous:
        p['async'] = {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}', 'status_path': 'status',
                      'poll_interval': 0, 'max_polls': 1}
    return p

def configuration(providers):
    return {'version': 1, 'primary': providers[0]['id'], 'fallbacks': [], 'currency': 'USD',
            'timeout_seconds': 3, 'providers': providers}

class FollowupContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name); self.store = ConfigStore(self.root / 'providers.json')
    def test_replace_failure_cleans_fake_secret_and_preserves_original(self):
        path = self.root / 'secrets.private.json'; atomic_json(path, {'slot': FA}, private=True)
        before = path.read_bytes()
        with patch('h3_adapter.config.os.replace', side_effect=PermissionError(13, 'injected replace denial')):
            with self.assertRaises(PermissionError): atomic_json(path, {'slot': FB}, private=True)
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(list(self.root.glob('*.tmp')), [], 'Failed secret write leaves a readable fake key copy')
    def test_partial_json_failure_cleans_temporary_and_preserves_original(self):
        path = self.root / 'providers.json'; atomic_json(path, {'before': True}); before = path.read_bytes()
        with self.assertRaises(ValueError): atomic_json(path, {'fake_key': FA, 'invalid': float('nan')}, private=True)
        self.assertEqual(path.read_bytes(), before); self.assertEqual(list(self.root.glob('*.tmp')), [])
    def test_fsync_failure_cleans_temporary_and_preserves_original(self):
        path = self.root / 'providers.json'; atomic_json(path, {'before': True}); before = path.read_bytes()
        with patch('h3_adapter.config.os.fsync', side_effect=OSError('injected fsync failure')):
            with self.assertRaises(OSError): atomic_json(path, {'fake_key': FA}, private=True)
        self.assertEqual(path.read_bytes(), before); self.assertEqual(list(self.root.glob('*.tmp')), [])
    def setup_merchants(self, same_url=False):
        peer = Peer(); self.addCleanup(peer.close); self.peer = peer
        self.old = provider('slot', peer.url + '/old'); self.keeper = provider('keeper', peer.url + '/keeper')
        self.new = provider('slot', self.old['base_url'] if same_url else peer.url + '/new')
        self.store.save(configuration([self.old, self.keeper])); self.store.save_key('slot', FA)
        self.engine = Engine(self.store, self.root / 'runtime')
        self.first = self.edit(0); self.assertEqual(self.first['report']['status'], 'awaiting_result')
        self.store.save(configuration([self.keeper])); self.store.save(configuration([self.new, self.keeper]))
    def edit(self, nonce):
        return self.engine.edit([self.peer.png], prompt='independent merchant audit', model_alias='edit', request_nonce=nonce)
    def test_delete_recreate_different_url_has_no_old_key_or_new_post(self):
        self.setup_merchants(); result = self.edit(1)
        self.assertEqual(self.store.public()['keys']['slot'], False)
        self.assertEqual(result['report']['status'], 'no_provider')
        self.assertEqual([c['path'] for c in self.peer.calls if c['method'] == 'POST'], ['/old/images/edits'])
    def test_delete_recreate_same_url_is_a_new_credential_binding(self):
        self.setup_merchants(same_url=True); result = self.edit(1)
        self.assertFalse(self.store.public()['keys']['slot']); self.assertEqual(result['report']['status'], 'no_provider')
        self.assertEqual(sum(c['method'] == 'POST' for c in self.peer.calls), 1)
    def test_new_key_and_old_paid_task_remain_isolated_after_recreation(self):
        self.setup_merchants(); self.store.save_key('slot', FB); new = self.edit(1)
        self.assertEqual(new['report']['status'], 'awaiting_result'); self.peer.complete = True
        old = self.edit(0); self.assertEqual(old['report']['error'], 'credential_changed_no_resubmit')
        self.store.save_key('slot', FA)
        old = self.edit(0); self.assertEqual(old['report']['status'], 'success')
        old_gets = [c for c in self.peer.calls if c['method'] == 'GET' and c['path'].startswith('/old/')]
        self.assertTrue(old_gets); self.assertTrue(all(c['key'] == 'Bearer ' + FA for c in old_gets))
        new_posts = [c for c in self.peer.calls if c['method'] == 'POST' and c['path'].startswith('/new/')]
        self.assertEqual(len(new_posts), 1); self.assertEqual(new_posts[0]['key'], 'Bearer ' + FB)
        self.assertEqual(sum(c['method'] == 'POST' for c in self.peer.calls), 2)
    def test_stale_window_cannot_save_old_key_after_same_config_recreation(self):
        peer = Peer(); self.addCleanup(peer.close)
        old = provider('slot', peer.url + '/same'); keep = provider('keeper', peer.url + '/keeper')
        cfg = configuration([old, keep]); self.store.save(cfg); self.store.save_key('slot', FA)
        old_revision = self.store.public()['revision']
        self.store.save(configuration([keep])); self.store.save(cfg)
        with self.assertRaises(ConfigConflict): self.store.save_key('slot', FA, old_revision)
        self.assertFalse(self.store.public()['keys']['slot'])
    def test_legacy_task_cannot_use_recreated_same_url_new_key(self):
        self.setup_merchants(same_url=True)
        rid = self.first['report']['request_id']; row = self.engine.journal.get(rid)
        snapshot = json.loads(row['snapshot']); snapshot.pop('credential_fingerprint')
        with self.engine.journal.connection() as db:
            db.execute('UPDATE requests SET snapshot=? WHERE request_id=?', (json.dumps(snapshot), rid))
        self.store.save_key('slot', FB); self.peer.complete = True; before = len(self.peer.calls)
        result = self.edit(0)
        self.assertEqual(result['report']['error'], 'credential_changed_no_resubmit')
        self.assertEqual(len(self.peer.calls), before)

    @unittest.skipUnless(os.name == 'nt', 'Windows sharing semantics')
    def test_internal_config_reader_does_not_break_atomic_save(self):
        from concurrent.futures import ThreadPoolExecutor
        import time
        peer = Peer(); self.addCleanup(peer.close)
        cfg = configuration([provider('slot', peer.url)])
        self.store.save(cfg); entered = threading.Event(); release = threading.Event()
        original_read = Path.read_text
        def hold_read(path, *args, **kwargs):
            if path == self.store.path and threading.current_thread().name == 'held-config-reader':
                with path.open('r', encoding='utf-8') as file:
                    entered.set(); release.wait(5); return file.read()
            return original_read(path, *args, **kwargs)
        changed = copy.deepcopy(cfg); changed['currency'] = 'EUR'
        with patch.object(Path, 'read_text', hold_read):
            reader = threading.Thread(target=self.store.load, name='held-config-reader'); reader.start()
            self.assertTrue(entered.wait(3))
            with ThreadPoolExecutor(max_workers=1) as pool:
                saved = pool.submit(self.store.save, changed)
                try:
                    time.sleep(.05)
                finally:
                    release.set(); reader.join(3)
                saved.result(timeout=5)
        self.assertEqual(self.store.load()['currency'], 'EUR')

    def test_retirement_then_config_failure_blocks_new_work_but_recovers_paid_task(self):
        peer = Peer(); self.addCleanup(peer.close); self.peer = peer
        self.old = provider('slot', peer.url + '/old'); keep = provider('keeper', peer.url + '/keeper')
        cfg = configuration([self.old, keep]); self.store.save(cfg); self.store.save_key('slot', FA)
        self.engine = Engine(self.store, self.root / 'runtime')
        first = self.edit(0); self.assertEqual(first['report']['status'], 'awaiting_result')
        real_atomic = atomic_json
        def fail_config(path, value, private=False):
            if path == self.store.path: raise PermissionError('injected config publication failure')
            return real_atomic(path, value, private)
        with patch('h3_adapter.config.atomic_json', side_effect=fail_config):
            with self.assertRaises(PermissionError): self.store.save(configuration([keep]))
        self.assertEqual(self.store.load(), cfg)
        self.assertFalse(self.store.public()['keys']['slot'])
        new = self.edit(1); self.assertEqual(new['report']['status'], 'no_provider')
        peer.complete = True; recovered = self.edit(0)
        self.assertEqual(recovered['report']['status'], 'success')
        self.assertEqual(sum(c['method'] == 'POST' for c in peer.calls), 1)
        self.assertTrue(all(c['key'] == 'Bearer ' + FA for c in peer.calls))
        self.assertEqual(list(self.root.glob('*.tmp')), [])

    def test_continuous_url_edit_keeps_explicit_existing_binding(self):
        peer = Peer(); self.addCleanup(peer.close)
        p = provider('slot', peer.url + '/old'); self.store.save(configuration([p])); self.store.save_key('slot', FA)
        cfg = self.store.load(); cfg['providers'][0]['base_url'] = peer.url + '/new'; self.store.save(cfg)
        self.assertEqual(self.store.credential(cfg['providers'][0]), FA)

if __name__ == '__main__': unittest.main(verbosity=2)