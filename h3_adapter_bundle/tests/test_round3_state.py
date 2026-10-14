"""Round-three regressions for caller deadlines and explicit paid-task intent."""
import copy
import io
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from PIL import Image
from h3_adapter.engine import Engine
from h3_adapter.protocol import Protocol
import test_engine as engine_fixture
PNG_BYTES = engine_fixture.PNG_BYTES


class Round3StateTests(unittest.TestCase):
    setUp = engine_fixture.EngineTests.setUp
    restore_key = engine_fixture.EngineTests.restore_key
    provider = engine_fixture.EngineTests.provider
    engine = engine_fixture.EngineTests.engine
    edit = engine_fixture.EngineTests.edit

    def test_unsent_local_deadline_preserves_primary_for_same_and_new_nonce(self):
        # Break caught: a caller's expired budget cools a healthy provider despite zero POSTs.
        for phase in ('initialization', 'protocol_before_send'):
            with self.subTest(phase=phase):
                runtime = self.root / phase
                clock = [0.0]
                def factory(provider, key):
                    api = Protocol(provider, key)
                    clock[0] = 2.0
                    return api
                class ExpiredBeforeSend(Protocol):
                    def submit(self, *args):
                        # Real Protocol._remaining rejects before client.stream can send.
                        with patch('h3_adapter.protocol.monotonic', side_effect=[0.0, args[-1] + 1.0]):
                            return super().submit(*args)
                engine = Engine(self.store, runtime, factory if phase == 'initialization' else ExpiredBeforeSend)
                before = len(self.api.calls(method='POST'))
                seam = SimpleNamespace(monotonic=lambda: clock[0], sleep=time.sleep)
                with patch('h3_adapter.engine.time', seam):
                    expired = self.edit(engine, request_nonce=71, auto_failover=False)
                self.assertEqual(expired['report']['status'], 'no_provider')
                self.assertEqual(expired['report']['attempts'][0]['error'],
                                 'request_deadline_exceeded' if phase == 'initialization' else 'submit_deadline_exceeded')
                self.assertEqual(len(self.api.calls(method='POST')), before)
                row = engine.journal.get(expired['report']['request_id'])
                self.assertEqual(row['state'], 'ready')
                self.assertEqual(row['reserved_cost'], 0)
                replay = self.edit(Engine(self.store, runtime), request_nonce=71)
                self.assertEqual(replay['report']['status'], 'success')
                self.assertEqual(replay['report']['provider'], 'p0')
                self.assertEqual(replay['report']['request_id'], expired['report']['request_id'])
                new = self.edit(Engine(self.store, runtime), request_nonce=72)
                self.assertEqual(new['report']['status'], 'success')
                self.assertEqual(new['report']['provider'], 'p0')
                self.assertEqual([r['provider'] for r in self.api.calls(method='POST')[before:]], ['p0', 'p0'])
                self.assertTrue(engine.journal.available('p0'))

    def test_paid_uncertain_or_accepted_task_keeps_reservation_and_never_uses_backup(self):
        # Break caught: deadline handling releases accepted/uncertain paid claims for a new POST.
        self.config['max_total_cost'] = 0.1
        for mode in ('uncertain', 'accepted'):
            with self.subTest(mode=mode):
                provider = self.config['providers'][0]
                provider.pop('async', None)
                if mode == 'accepted':
                    self.api.set_plan('p0', **{'async': True})
                    provider['async'] = {'task_id_path': 'id', 'poll_path': '/tasks/{task_id}',
                                         'status_path': 'status', 'poll_interval': 0, 'max_polls': 1}
                else:
                    self.api.set_plan('p0', status=500)
                self.store.save(self.config)
                runtime = self.root / mode
                before = len(self.api.calls(method='POST'))
                engine = Engine(self.store, runtime)
                first = self.edit(engine, request_nonce=81)
                self.assertEqual(first['report']['status'], 'uncertain' if mode == 'uncertain' else 'awaiting_result')
                row = engine.journal.get(first['report']['request_id'])
                self.assertEqual(row['state'], mode)
                self.assertEqual(row['reserved_cost'], 0.1)
                replay = self.edit(Engine(self.store, runtime), request_nonce=81)
                self.assertEqual(replay['report']['status'], first['report']['status'])
                denied = self.edit(Engine(self.store, runtime), request_nonce=82)
                self.assertEqual(denied['report']['status'], 'blocked')
                self.assertEqual([r['provider'] for r in self.api.calls(method='POST')[before:]], ['p0'])

    def test_actual_model_change_preserves_old_intent_but_nonce_alias_and_input_create_new(self):
        # Break caught: model mapping changes silently discard paid history or auto-create a nonce.
        first = self.edit(request_nonce=91)
        self.assertEqual(first['report']['status'], 'success')
        model = self.config['providers'][0]['models']['background-edit']
        model['id'] = 'new-real-model'
        model['price_upper_bound'] = 0.7
        self.config['providers'][0]['models']['another-alias'] = copy.deepcopy(model)
        self.store.save(self.config)
        cached = self.edit(request_nonce=91)
        self.assertTrue(cached['report']['cached'])
        self.assertEqual(cached['report']['model'], 'model-p0')
        self.assertEqual(cached['report']['estimated_cost'], 0.1)
        self.assertEqual(cached['report']['request_id'], first['report']['request_id'])
        self.assertEqual(len(self.api.calls(method='POST')), 1)
        new = self.edit(request_nonce=92)
        self.assertEqual(new['report']['status'], 'success')
        self.assertEqual(new['report']['model'], 'new-real-model')
        alias = self.engine().edit([PNG_BYTES], prompt='replace background with blue', model_alias='another-alias', request_nonce=91)
        self.assertEqual(alias['report']['status'], 'success')
        buffer = io.BytesIO()
        Image.new('RGB', (2, 2), 'white').save(buffer, 'PNG')
        changed = self.engine().edit([buffer.getvalue()], prompt='replace background with blue', request_nonce=91)
        self.assertEqual(changed['report']['status'], 'success')
        self.assertEqual(len({r['report']['request_id'] for r in (first, new, alias, changed)}), 4)
        self.assertEqual(len(self.api.calls(method='POST')), 4)
        self.assertTrue(all(b'new-real-model' in r['body'] for r in self.api.calls(method='POST')[1:]))


if __name__ == '__main__':
    unittest.main()

