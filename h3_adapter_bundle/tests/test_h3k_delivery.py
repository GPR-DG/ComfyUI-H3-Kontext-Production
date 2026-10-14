"""H3K delivery regressions; CPU fixtures only, no network/model/API calls."""
import copy
import gc
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import weakref

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'H3KBackgroundResolve', 'H3KBackgroundWashClaim', 'H3KBackgroundFinish',
         'H3KBackgroundSource', 'H3KStageGuard', 'H3KRecipe',
         'H3KPromptCapture', 'H3KStagePreview'}


class Cache:
    def __init__(self, view):
        self.view = view
        self.closed = False
        self.claims = 0
    def get(self, view_id):
        if self.closed or view_id != self.view.view_id:
            raise ValueError('closed or foreign view')
        return self.view
    def claim_wash(self, view_id):
        self.get(view_id)
        self.claims += 1
        return 'owned-token' if self.claims == 1 else None
    def attach_clean(self, view_id, pixels, wash_token):
        self.get(view_id)
        if wash_token != 'owned-token':
            raise ValueError('foreign token')
        self.view.clean_background = pixels.copy()
        self.view.state = 'READY'
        return self.view
    def cleanup(self):
        self.closed = True


class Task:
    def __init__(self):
        self.task_id = 'task-fixture'
        self.cleaned = False
        candidate = types.SimpleNamespace(image=np.full((8, 12, 3), .4, dtype=np.float32))
        self.view = types.SimpleNamespace(task_id=self.task_id, view_id='view-fixture',
                                         state='PENDING', candidate=candidate, clean_background=None)
        self.cache = Cache(self.view)
    def cleanup(self):
        self.cache.cleanup()
        self.cleaned = True


class H3KDeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        folder = ROOT / 'h3_kontext_bridge'
        spec = importlib.util.spec_from_file_location('_h3k_delivery_tests', folder / '__init__.py',
                                                      submodule_search_locations=[str(folder)])
        cls.plugin = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cls.plugin
        spec.loader.exec_module(cls.plugin)
        cls.k = sys.modules[spec.name + '.nodes']

    def setUp(self):
        self.task = Task(); self.view = self.task.view
        self.core = types.SimpleNamespace(_image_output=lambda x: torch.from_numpy(x.copy())[None])
        self.patches = [patch.object(self.k, 'core', return_value=self.core),
                        patch.object(self.k, 'geometry', side_effect=lambda h, w:
                                     dict(h=h, w=w, bh=h, bw=w, scale=1., x=0., y=0.))]
        for p in self.patches:p.start();self.addCleanup(p.stop)
        self.k.state(self.task)['recipes'][self.view.view_id] = 'recipe-fixture'
        self.token = self.k.H3KBackgroundWashClaim().run(self.task, self.view)[0]
        self.pixels, self.canvas = self.k.H3KBackgroundSource().run(self.task, self.view, self.token)
        self.addCleanup(self.task.cleanup)

    def stage(self):
        return self.k.H3KStageGuard().run(self.task, self.view, self.token,
                                         self.pixels, self.canvas, 'kontext')

    def finish(self):
        b, original, _ = self.stage()
        _, z, _ = self.k.H3KStageGuard().run(self.task, self.view, self.token, b, self.canvas, 'z_image')
        self.k.H3KPromptCapture().run(self.task, self.view, 'empty room')
        return self.k.H3KBackgroundFinish().run(self.task, self.view, z, self.token, original)['result']

    def test_all_eight_registered_and_target_port_schema_unchanged(self):
        self.assertEqual(set(self.plugin.NODE_CLASS_MAPPINGS), NAMES)
        contract = json.loads((ROOT / 'docs/H3K-TARGET-PORTS.json').read_text(encoding='utf-8'))
        self.assertEqual({n['type'] for n in contract['nodes']}, NAMES)
        for n in contract['nodes']:
            node = self.plugin.NODE_CLASS_MAPPINGS[n['type']]
            schema = node.INPUT_TYPES()
            ports = {**schema.get('required', {}), **schema.get('optional', {})}
            for port in n['inputs']:
                self.assertIn(port['name'], ports)
                actual = ports[port['name']][0]
                self.assertTrue(port['type'] == actual or isinstance(actual, list) and port['type'] == 'COMBO')
            self.assertEqual(tuple(p['type'] for p in n['outputs']), node.RETURN_TYPES)
            self.assertEqual(tuple(p['name'] for p in n['outputs']), node.RETURN_NAMES)

    def test_mutated_canvas_geometry_is_blocked(self):
        self.canvas['geometry']['x'] += 2
        with self.assertRaisesRegex(ValueError, 'geometry/ownership'):
            self.stage()

    def test_guard_outputs_do_not_alias_private_proof(self):
        b, original, _ = self.stage(); expected_b=b.clone(); expected_o=original.clone()
        b.zero_(); original.zero_()
        preview = self.k.H3KStagePreview().run(self.task, self.view, self.token)
        self.assertTrue(torch.equal(preview[0], expected_b))
        self.assertTrue(torch.equal(preview[1], expected_o))

    def test_inplace_Z_cannot_commit_changed_pixels(self):
        b, original, _ = self.stage()
        _, z, _ = self.k.H3KStageGuard().run(self.task, self.view, self.token, b, self.canvas, 'z_image')
        self.k.H3KPromptCapture().run(self.task, self.view, 'empty room');z.zero_()
        with self.assertRaisesRegex(ValueError, 'completion evidence'):
            self.k.H3KBackgroundFinish().run(self.task, self.view, z, self.token, original)
        self.assertEqual(self.view.state, 'PENDING')

    def test_READY_prompt_is_immutable_and_skips_costly_inputs(self):
        first = self.finish()
        self.assertEqual(self.k.H3KBackgroundFinish().check_lazy_status(self.task,self.view), [])
        again = self.k.H3KBackgroundFinish().run(self.task,self.view)['result']
        self.assertTrue(torch.equal(first[1],again[1]))
        with self.assertRaisesRegex(ValueError, 'immutable'):
            self.k.H3KPromptCapture().run(self.task,self.view,'different room')

    def test_pending_prompt_is_idempotent_but_not_replaceable(self):
        self.stage();capture=self.k.H3KPromptCapture()
        self.assertEqual(capture.run(self.task,self.view,['empty room']),('empty room',))
        capture.run(self.task,self.view,'empty room')
        with self.assertRaisesRegex(ValueError,'cannot replace'):
            capture.run(self.task,self.view,'different room')

    def test_READY_releases_Z_proof_but_preserves_B_preview(self):
        self.finish();local=self.k.state(self.task)
        self.assertNotIn(self.view.view_id,local['washed'])
        self.assertIn(self.view.view_id,local['removed'])
        self.k.H3KStagePreview().run(self.task,self.view)

    def test_cleanup_releases_private_tensors_and_preserves_core_cleanup(self):
        self.stage();local=self.k.state(self.task);self.task.cleanup()
        self.assertTrue(self.task.cleaned);self.assertTrue(self.task.cache.closed)
        for name in ('exact','recipes','tokens','canvas','removed','washed','prompts'):
            self.assertFalse(local[name])
        self.task.cleanup()
        with self.assertRaisesRegex(ValueError,'closed'):self.k.state(self.task)

    def test_cleanup_hook_does_not_keep_task_alive(self):
        task=Task();self.k.state(task);ref=weakref.ref(task);del task;gc.collect()
        self.assertIsNone(ref())

    def test_claim_fanout_is_idempotent_and_READY_does_not_dispatch(self):
        repeated=self.k.H3KBackgroundWashClaim().run(self.task,self.view)
        self.assertEqual(repeated[0],self.token);self.assertEqual(self.task.cache.claims,1)
        self.finish()
        self.assertEqual(self.k.H3KBackgroundWashClaim().run(self.task,self.view)[:2],('',False))

    def test_stale_token_and_Z_without_B_fail_closed(self):
        with self.assertRaises(ValueError):
            self.k.H3KStageGuard().run(self.task,self.view,'stale',self.pixels,self.canvas,'kontext')
        with self.assertRaisesRegex(ValueError,'without Kontext'):
            self.k.H3KStageGuard().run(self.task,self.view,self.token,self.pixels,self.canvas,'z_image')

    def test_invalid_images_fail_before_commit(self):
        for value in (torch.zeros((0,8,12,3)),torch.full_like(self.pixels,float('nan')),
                      self.pixels+2,self.pixels[:,:7],self.pixels.repeat(2,1,1,1)):
            with self.assertRaises(ValueError):
                self.k.H3KStageGuard().run(self.task,self.view,self.token,value,self.canvas,'kontext')
        self.assertEqual(self.view.state,'PENDING')

    def test_recipe_shared_source_reads_once_per_invocation(self):
        class LocalNode:
            pass
        prompt={'shared':{'class_type':'LocalNode','inputs':{'text':'empty room'}},
                'k':{'class_type':'LocalNode','inputs':{'image':['shared',0]}},
                'z':{'class_type':'LocalNode','inputs':{'image':['shared',0]}}}
        real_read=Path.read_bytes;reads=[]
        def counted(path):
            reads.append(path);return real_read(path)
        with patch.object(self.k,'registry',return_value={'LocalNode':LocalNode}), \
                patch.dict(sys.modules,{'folder_paths':types.ModuleType('folder_paths')}), \
                patch.object(Path,'read_bytes',counted):
            one=self.k.H3KRecipe().run(.86,'remove people','k','z',prompt)[0]
            self.assertEqual(reads.count(Path(__file__)),1)
            reads.clear()
            two=self.k.H3KRecipe().run(.86,'remove people','k','z',prompt)[0]
            self.assertEqual(one,two)
            self.assertEqual(reads.count(Path(__file__)),1)
            three=self.k.H3KRecipe().run(.5,'remove people','k','z',prompt)[0]
            self.assertNotEqual(one,three)

    def test_cross_task_nodes_are_blocked(self):
        foreign=Task();foreign.task_id='other-task';self.addCleanup(foreign.cleanup)
        calls=[lambda:self.k.H3KBackgroundResolve().run(foreign,self.view.candidate,'r'),
               lambda:self.k.H3KBackgroundWashClaim().run(foreign,self.view),
               lambda:self.k.H3KBackgroundSource().run(foreign,self.view,self.token),
               lambda:self.k.H3KStagePreview().run(foreign,self.view,self.token),
               lambda:self.k.H3KPromptCapture().run(foreign,self.view,'room'),
               lambda:self.k.H3KBackgroundFinish().run(foreign,self.view)]
        self.view.candidate.task_id=self.task.task_id
        for call in calls:
            with self.assertRaises(ValueError):call()

    def test_core_LF_CRLF_accepted_but_source_tamper_blocked(self):
        # Stop only the Core test double; execute the actual pin checker.
        self.patches[0].stop()
        pins=json.loads((ROOT/'h3_kontext_bridge/core-required-sha256.json').read_text())
        core_root=Path(__file__).resolve().parents[2]/'core'
        if not all((core_root/f).is_file() for f in pins):
            # Standalone package: create audited-content fixtures through explicit env path.
            import os
            core_root=Path(os.environ.get('H3K_CORE_TEST_ROOT','__no_core_fixture__'))
        if not all((core_root/f).is_file() for f in pins):
            self.skipTest('Set H3K_CORE_TEST_ROOT to audited Core to test pin bytes')
        with tempfile.TemporaryDirectory() as tmp:
            module=types.ModuleType('_h3k_pin_fixture');module.__file__=str(Path(tmp)/'h3_background_nodes.py')
            cls=type('Resolve',(),{'__module__':module.__name__})
            with patch.dict(sys.modules,{module.__name__:module}),patch.object(self.k,'registry',return_value={'H3CBackgroundResolve':cls}):
                for ending in (b'\n',b'\r\n'):
                    for f,h in pins.items():
                        data=(core_root/f).read_bytes().replace(b'\r\n',b'\n')
                        self.assertEqual(hashlib.sha256(data).hexdigest(),h)
                        (Path(tmp)/f).write_bytes(data.replace(b'\n',ending))
                    self.assertIs(self.k.core(),module)
                (Path(tmp)/'h3_background_nodes.py').write_bytes(b'# tampered\n')
                with self.assertRaisesRegex(RuntimeError,'source mismatch'):self.k.core()


if __name__ == '__main__':
    unittest.main()
