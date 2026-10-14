"""Task-local Kontext/Z-Image bridge; delegates cache/matching to unchanged H3 Core.
READY certifies pipeline completion, never visual person-removal quality.
"""
import copy
import hashlib
import importlib
import inspect
import json
import threading
import weakref
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

CATEGORY = 'H3/Kontext Background'
VERSION = '0.1.8'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
        allow_nan=False, separators=(',', ':')).encode()).hexdigest()


def registry():
    import nodes
    return nodes.NODE_CLASS_MAPPINGS


def core():
    cls = registry().get('H3CBackgroundResolve')
    if cls is None:
        raise RuntimeError('Install the supplied H3 Core background-node revision; H3CBackgroundResolve missing')
    module = importlib.import_module(cls.__module__)
    root = Path(module.__file__).parent
    pins = json.loads((Path(__file__).parent / 'core-required-sha256.json').read_text(encoding='utf-8'))
    for name, expected in pins.items():
        if hashlib.sha256((root / name).read_bytes().replace(b'\r\n', b'\n')).hexdigest() != expected:
            raise RuntimeError('H3 Background Core source mismatch: ' + name)
    return module


def cleanup_task_state(task):
    local = getattr(task, '_h3k', None)
    if local is not None:
        with local['lock']:
            for key in ('exact', 'recipes', 'tokens', 'canvas', 'removed', 'washed', 'prompts'):
                local[key].clear()

def state(task):
    if getattr(task, 'cleaned', True):
        cleanup_task_state(task)
        raise ValueError('Background task is closed')
    if not hasattr(task, '_h3k'):
        task._h3k = dict(exact={}, recipes={}, tokens={}, canvas={}, removed={},
                        washed={}, prompts={}, lock=threading.RLock())
        # Extend this handle's existing cleanup only; Core source/API are unchanged.
        task_ref = weakref.ref(task)
        original_cleanup = weakref.WeakMethod(task.cleanup)
        def cleanup_local_state():
            callback = original_cleanup()
            try:
                if callback is not None:
                    return callback()
            finally:
                owner = task_ref()
                if owner is not None and owner.cleaned:
                    cleanup_task_state(owner)
        task.cleanup = cleanup_local_state
    return task._h3k


def image(value, name, shape=None):
    if (not isinstance(value, torch.Tensor) or value.ndim != 4 or value.shape[0] != 1
            or value.shape[-1] != 3 or min(value.shape[1:3]) < 1 or not value.is_floating_point()):
        raise ValueError(name + ' requires one non-empty float RGB IMAGE')
    if value.shape[1] * value.shape[2] > 16777216:
        raise ValueError(name + ' exceeds 16 megapixels')
    if not torch.isfinite(value).all() or value.min() < 0 or value.max() > 1:
        raise ValueError(name + ' must be finite [0,1]')
    if shape is not None and tuple(value.shape[1:]) != tuple(shape):
        raise ValueError(name + ' has wrong H/W/C; refusing crop/stretch')
    return value


def raw_key(candidate):
    h = hashlib.sha256()
    for array in (candidate.image, candidate.foreground_mask, candidate.depth):
        if array is None:
            h.update(b'None')
        else:
            array = np.ascontiguousarray(array)
            h.update(str((array.shape, array.dtype.str)).encode())
            h.update(array.tobytes())
    h.update(str(candidate.background_only).encode())
    return h.hexdigest()


def owned(task, view, token):
    s = state(task)
    if view.task_id != task.task_id or not token or s['tokens'].get(view.view_id) != token:
        raise ValueError('Cross-task or unowned processing result')
    current = task.cache.get(view.view_id)
    if current.state != 'PENDING':
        raise ValueError('Processing branch requires PENDING, not completed/closed view')
    return s, current


def resample(value, h, w, scale_x, scale_y, offset_x, offset_y):
    # One affine mapping with equal X/Y scale; grid_sample uses mature Torch
    # resampling. Float geometry avoids integer aspect-ratio rounding/cropping.
    value = value.detach().cpu().float()
    sy, sx = value.shape[1:3]
    x = ((torch.arange(w, dtype=torch.float32) + .5) * scale_x + offset_x) / sx * 2 - 1
    y = ((torch.arange(h, dtype=torch.float32) + .5) * scale_y + offset_y) / sy * 2 - 1
    yy, xx = torch.meshgrid(y, x, indexing='ij')
    grid = torch.stack((xx, yy), -1).unsqueeze(0)
    return F.grid_sample(value.movedim(-1, 1), grid, mode='bilinear',
                         padding_mode='border', align_corners=False).movedim(1, -1).contiguous()


def geometry(h, w):
    from comfy_extras.nodes_flux import PREFERRED_KONTEXT_RESOLUTIONS
    bw, bh = min(PREFERRED_KONTEXT_RESOLUTIONS, key=lambda r: abs(w / h - r[0] / r[1]))
    scale = min(bw / w, bh / h)
    return dict(h=h, w=w, bh=bh, bw=bw, scale=scale,
                x=(bw-w*scale)/2, y=(bh-h*scale)/2)


def prepared(value, g):
    return resample(value, g['bh'], g['bw'], 1/g['scale'], 1/g['scale'],
                    -g['x']/g['scale'], -g['y']/g['scale'])


def restored(value, g):
    image(value, 'decoded model canvas', (g['bh'], g['bw'], 3))
    return image(resample(value, g['h'], g['w'], g['scale'], g['scale'], g['x'], g['y']),
                 'restored original frame', (g['h'], g['w'], 3))


class H3KRecipe:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'denoise': ('FLOAT', {'forceInput': True}),
            'removal_prompt': ('STRING', {'multiline': True}),
            'kontext_node_id': ('STRING', {'default': '7523'}),
            'z_node_id': ('STRING', {'default': '7411'})}, 'hidden': {'prompt': 'PROMPT'}}
    RETURN_TYPES = ('STRING', 'STRING')
    RETURN_NAMES = ('revision', 'removal_prompt')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float('nan')
    def run(self, denoise, removal_prompt, kontext_node_id, z_node_id, prompt):
        if not isinstance(removal_prompt, str) or not removal_prompt.strip() or not 0 <= float(denoise) <= 1:
            raise ValueError('Invalid removal prompt/denoise')
        active = set()
        source_hashes = {}  # Invocation-local: never reuse hashes after source changes.
        boundaries = {'H3KBackgroundSource', 'H3KStageGuard', 'H3KRecipe', 'H3KBackgroundResolve'}
        def snapshot(nid):
            nid = str(nid)
            if nid in active or nid not in prompt:
                raise ValueError('Cycle/missing node in local processing recipe')
            active.add(nid)
            spec = prompt[nid]; inputs = {}
            for key, val in spec['inputs'].items():
                if key in {'task', 'view', 'wash_token', 'completion', 'unique_id'}:
                    continue
                if isinstance(val, list) and len(val) == 2 and str(val[0]) in prompt:
                    parent = prompt[str(val[0])]
                    if parent['class_type'] in boundaries:
                        continue
                    inputs[key] = {'node': snapshot(val[0]), 'output': val[1]}
                else:
                    inputs[key] = val
            cls = registry().get(spec['class_type'])
            filename = inspect.getsourcefile(cls) if cls else None
            if not filename or not Path(filename).is_file():
                raise RuntimeError('Recipe node implementation unavailable: ' + spec['class_type'])
            if filename not in source_hashes:
                source_hashes[filename] = hashlib.sha256(Path(filename).read_bytes()).hexdigest()
            models = {}
            import folder_paths
            for field, category in [('unet_name', 'diffusion_models'), ('clip_name', 'text_encoders'),
                    ('clip_name1', 'text_encoders'), ('clip_name2', 'text_encoders'), ('vae_name', 'vae')]:
                if field in inputs and isinstance(inputs[field], str):
                    model_path = folder_paths.get_full_path(category, inputs[field])
                    if model_path:
                        st = Path(model_path).stat()
                        models[field] = [inputs[field], st.st_size, st.st_mtime_ns]
            active.remove(nid)
            return dict(type=spec['class_type'], inputs=inputs,
                        source=source_hashes[filename], models=models)
        revision = digest(dict(version=VERSION, source=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            core=json.loads((Path(__file__).parent/'core-required-sha256.json').read_text(encoding='utf-8')),
            kontext=snapshot(kontext_node_id), z=snapshot(z_node_id),
            prompt=removal_prompt, denoise=float(denoise), geometry='uniform-affine-border-v1'))
        return revision, removal_prompt


class H3KBackgroundResolve:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'candidate': ('BACKGROUND_CANDIDATE',),
                             'revision': ('STRING', {'forceInput': True})}}
    RETURN_TYPES = ('BACKGROUND_VIEW', 'BACKGROUND_DECISION', 'IMAGE', 'STRING', 'STRING', 'BOOLEAN')
    RETURN_NAMES = ('view', 'decision', 'clean_background', 'view_id', 'state', 'ready')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def run(self, task, candidate, revision):
        c = core(); s = state(task)
        if candidate.task_id != task.task_id or not revision:
            raise ValueError('Cross-task candidate or missing recipe')
        key = (revision, raw_key(candidate))
        with s['lock']:
            if key in s['exact']:
                view = task.cache.get(s['exact'][key])
                contracts = importlib.import_module(c.BackgroundView.__module__)
                matcher = importlib.import_module(type(task.matcher).__module__)
                decision = contracts.EnvironmentDecision(task.task_id, candidate.key, 'REUSE_EXISTING',
                    view.environment_id, view.view_id, confidence=1.,
                    reason='Exact raw pixels, aligned evidence and full local recipe match',
                    report={'reuse_basis':'exact_source_and_recipe', 'physical_identity_proven':False},
                    decision_key=matcher.production_request_key(candidate, revision))
            else:
                allowed = {v for v, r in s['recipes'].items() if r == revision}
                class FilteredMatcher:
                    def match_for_production(self, query, views, revision='default'):
                        return task.matcher.match_for_production(query,
                            [v for v in views if v.view_id in allowed], revision=revision)
                decision, view = task.cache.resolve(candidate, FilteredMatcher(), revision)
                s['exact'][key] = view.view_id
                s['recipes'][view.view_id] = revision
            clean = c._image_output(view.clean_background) if view.state == 'READY' else None
            if clean is not None:
                image(clean, 'cached background', view.candidate.image.shape)
            return view, decision, clean, view.view_id, view.state, clean is not None


class H3KBackgroundWashClaim:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',)}}
    RETURN_TYPES = ('STRING', 'BOOLEAN', 'STRING')
    RETURN_NAMES = ('wash_token', 'claimed', 'view_id')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def run(self, task, view):
        s = state(task)
        if view.task_id != task.task_id:
            raise ValueError('Cross-task view')
        with s['lock']:
            if task.cache.get(view.view_id).state == 'READY':
                return '', False, view.view_id
            token = s['tokens'].get(view.view_id)
            if token is None:
                token = task.cache.claim_wash(view.view_id)
                if not token:
                    raise RuntimeError('View already claimed; no duplicate processing dispatch')
                s['tokens'][view.view_id] = token
            return token, True, view.view_id


class H3KBackgroundSource:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',),
                             'wash_token': ('STRING', {'forceInput': True})}}
    RETURN_TYPES = ('IMAGE', 'H3K_CANVAS')
    RETURN_NAMES = ('letterboxed_candidate', 'canvas')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def run(self, task, view, wash_token):
        s, current = owned(task, view, wash_token)
        value = image(core()._image_output(current.candidate.image), 'source candidate')
        g = geometry(*value.shape[1:3])
        canvas = dict(task=task.task_id, view=view.view_id, token=wash_token,
                      recipe=s['recipes'][view.view_id], geometry=g)
        with s['lock']:
            s['canvas'][view.view_id] = copy.deepcopy(canvas)
        return image(prepared(value, g), 'Kontext prepared canvas'), canvas


class H3KStageGuard:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',),
            'wash_token': ('STRING', {'forceInput': True}), 'pixels': ('IMAGE',),
            'canvas': ('H3K_CANVAS',), 'stage': (['kontext', 'z_image'],)}}
    RETURN_TYPES = ('IMAGE', 'IMAGE', 'STRING')
    RETURN_NAMES = ('model_canvas', 'original_size_result', 'report')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def run(self, task, view, wash_token, pixels, canvas, stage):
        s, current = owned(task, view, wash_token)
        if stage not in {'kontext', 'z_image'}:
            raise ValueError('Unknown local processing stage')
        with s['lock']:
            if canvas != s['canvas'].get(view.view_id):
                raise ValueError('Canvas geometry/ownership evidence mismatch')
            if stage == 'z_image' and view.view_id not in s['removed']:
                raise ValueError('Z-Image completion without Kontext evidence')
            g = canvas['geometry']
            value = image(pixels, stage + ' decoded canvas', (g['bh'], g['bw'], 3)).detach().cpu().clone()
            original = restored(value, g)
            record = dict(token=wash_token, recipe=canvas['recipe'], canvas=value, original=original)
            target = s['removed'] if stage == 'kontext' else s['washed']
            old = target.get(view.view_id)
            if old is not None and not torch.equal(old['canvas'], value):
                raise ValueError('Completed local stage cannot silently replace its pixels; change Recipe')
            target[view.view_id] = record
        report = json.dumps(dict(stage=stage, technical_completion=True, visual_quality_verified=False,
                                 original_hw=[g['h'], g['w']], canvas_hw=[g['bh'], g['bw']]))
        # Downstream in-place IMAGE operations must not mutate private stage proof.
        return value.clone(), original.clone(), report


class H3KPromptCapture:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',),
                             'text': ('STRING', {'forceInput': True})}}
    RETURN_TYPES = ('STRING',); RETURN_NAMES = ('scene_prompt',)
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def run(self, task, view, text):
        s = state(task)
        # The pinned Qwen3_VQA upstream returns batch_decode's one-item list
        # inside a STRING output. Normalize only that documented single-image case.
        if isinstance(text, (list, tuple)) and len(text) == 1 and isinstance(text[0], str):
            text = text[0]
        if view.task_id != task.task_id or not isinstance(text, str) or not text.strip():
            raise ValueError('Cross-task/empty scene prompt')
        with s['lock']:
            if task.cache.get(view.view_id).state != 'PENDING':
                raise ValueError('Completed view prompt is immutable; change Recipe')
            old = s['prompts'].get(view.view_id)
            if old is not None and old != text:
                raise ValueError('Completed Qwen stage cannot replace its prompt; change Recipe')
            s['prompts'][view.view_id] = text
        return (text,)


class H3KBackgroundFinish:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',),
            'clean_background': ('IMAGE', {'lazy': True}), 'wash_token': ('STRING', {'forceInput': True}),
            'removal_background': ('IMAGE', {'lazy': True})}}
    RETURN_TYPES = ('BACKGROUND_VIEW', 'IMAGE', 'STRING', 'BOOLEAN', 'IMAGE', 'STRING', 'IMAGE')
    RETURN_NAMES = ('view', 'clean_background', 'report', 'ready', 'A_original', 'scene_prompt', 'B_kontext')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def check_lazy_status(self, task, view, clean_background=None, wash_token='', removal_background=None):
        s = state(task)
        if view.task_id != task.task_id:
            raise ValueError('Cross-task finish')
        if task.cache.get(view.view_id).state == 'READY':
            return []
        owned(task, view, wash_token)
        if removal_background is None and view.view_id not in s['removed']:
            return ['removal_background']
        if removal_background is not None:
            image(removal_background, 'Kontext prerequisite', view.candidate.image.shape)
        return ['clean_background'] if clean_background is None else []
    def run(self, task, view, clean_background=None, wash_token='', removal_background=None):
        s = state(task); c = core()
        if view.task_id != task.task_id:
            raise ValueError('Cross-task finish')
        with s['lock']:
            current = task.cache.get(view.view_id); hit = current.state == 'READY'
            b = s['removed'].get(view.view_id)
            if b is None or b['recipe'] != s['recipes'].get(view.view_id):
                raise ValueError('Kontext completion evidence missing')
            if not hit:
                owned(task, view, wash_token)
                z = s['washed'].get(view.view_id)
                result = image(clean_background, 'Z-Image restored result', current.candidate.image.shape)
                if (b['token'] != wash_token or z is None or z['token'] != wash_token
                        or z['recipe'] != b['recipe'] or not torch.equal(result.detach().cpu(), z['original'])
                        or not s['prompts'].get(view.view_id)):
                    raise ValueError('Full local pipeline completion evidence missing/mismatched')
                current = task.cache.attach_clean(view.view_id, result.detach().cpu().numpy()[0], wash_token=wash_token)
            if current.state != 'READY' or current.clean_background is None:
                raise RuntimeError('No completed background')
            # SQLite owns the committed Z result; only B remains needed for previews.
            s['washed'].pop(view.view_id, None)
            clean = image(c._image_output(current.clean_background), 'READY', current.candidate.image.shape)
            report = json.dumps(dict(view_id=view.view_id, state='READY', pipeline='Kontext6+Qwen+Z-Image',
                                     cache_hit=hit, visual_quality_verified=False))
            return {'ui': {'text': [report]}, 'result': (current, clean, report, True,
                c._image_output(current.candidate.image), s['prompts'][view.view_id], b['original'].clone())}


class H3KStagePreview:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {'task': ('BACKGROUND_TASK',), 'view': ('BACKGROUND_VIEW',),
            'wash_token': ('STRING', {'forceInput': True}), 'removal_background': ('IMAGE', {'lazy': True})}}
    RETURN_TYPES = ('IMAGE', 'IMAGE'); RETURN_NAMES = ('model_canvas', 'kontext_result')
    FUNCTION = 'run'; CATEGORY = CATEGORY
    def check_lazy_status(self, task, view, wash_token='', removal_background=None):
        s = state(task)
        if view.task_id != task.task_id:
            raise ValueError('Cross-task preview')
        if view.view_id in s['removed']:
            return []
        owned(task, view, wash_token)
        return ['removal_background'] if removal_background is None else []
    def run(self, task, view, wash_token='', removal_background=None):
        s = state(task)
        if view.task_id != task.task_id:
            raise ValueError('Cross-task preview')
        with s['lock']:
            record = s['removed'].get(view.view_id)
            if record is None or record['recipe'] != s['recipes'].get(view.view_id):
                raise ValueError('No validated Kontext stage result')
            return record['canvas'].clone(), image(record['original'].clone(), 'Kontext preview', view.candidate.image.shape)


NODE_CLASS_MAPPINGS = {cls.__name__: cls for cls in (H3KRecipe, H3KBackgroundResolve,
    H3KBackgroundWashClaim, H3KBackgroundSource, H3KStageGuard, H3KPromptCapture,
    H3KBackgroundFinish, H3KStagePreview)}
NODE_DISPLAY_NAME_MAPPINGS = {name: name.replace('H3K', 'H3 Kontext ') for name in NODE_CLASS_MAPPINGS}
