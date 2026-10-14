"""One stable ComfyUI IMAGE/MASK node; providers and secrets live off-workflow."""
import io
import json
import os
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from .h3_adapter.config import ConfigStore
from .h3_adapter.engine import Engine

ROOT = Path(__file__).resolve().parent
STORE = ConfigStore(Path(os.environ.get('H3_ADAPTER_CONFIG', str(ROOT / 'config' / 'providers.json'))))


def png_inputs(image, mask=None):
    array = image.detach().cpu().numpy()
    if array.ndim != 4 or not 1 <= array.shape[0] <= 16 or array.shape[-1] not in (3, 4) or not np.isfinite(array).all():
        raise ValueError('IMAGE must be finite [B,H,W,3/4], B=1..16')
    images = []
    for frame in array:
        buffer = io.BytesIO()
        Image.fromarray(np.rint(np.clip(frame[:, :, :3], 0, 1) * 255).astype(np.uint8)).save(buffer, format='PNG')
        images.append(buffer.getvalue())
    mask_png = None
    if mask is not None:
        masked = mask.detach().cpu().numpy()
        if masked.ndim == 3 and masked.shape[0] == 1:
            masked = masked[0]
        if masked.ndim != 2 or masked.shape != array.shape[1:3] or not np.isfinite(masked).all():
            raise ValueError('MASK must be one finite [H,W] or [1,H,W] matching the first IMAGE')
        # Comfy white=edit; standard image-edit PNG alpha transparent=edit.
        rgba = np.zeros((*masked.shape, 4), dtype=np.uint8)
        rgba[:, :, 3] = np.rint((1 - np.clip(masked, 0, 1)) * 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(rgba).save(buffer, format='PNG')
        mask_png = buffer.getvalue()
    return images, mask_png


def image_tensor(contents, shape):
    import torch
    frames = []
    for content in contents:
        with Image.open(io.BytesIO(content)) as image:
            array = np.array(ImageOps.exif_transpose(image).convert('RGB'), dtype=np.float32) / 255.0
            frames.append(torch.from_numpy(array).unsqueeze(0))
    # Failure is an empty IMAGE, never a silently returned unrepaired input.
    return torch.cat(frames, dim=0) if frames else torch.empty((0, shape[1], shape[2], 3), dtype=torch.float32)


class H3ImageEdit:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required': {
            'image': ('IMAGE',),
            'prompt': ('STRING', {'multiline': True, 'default': '移除图中人物，修复人物遮挡的背景，补全墙面、门窗结构，保持视角、光照和建筑纹理一致。'}),
            'provider': ('STRING', {'default': 'auto'}),
            'model_alias': ('STRING', {'default': 'background-edit'}),
            'parameters': ('STRING', {'default': '{}', 'multiline': True}),
            'auto_failover': ('BOOLEAN', {'default': True}),
            'timeout_seconds': ('INT', {'default': 120, 'min': 1, 'max': 3600}),
            'max_cost': ('FLOAT', {'default': 1.0, 'min': 0, 'max': 100000, 'step': 0.01}),
            'request_nonce': ('INT', {'default': 0, 'min': 0, 'max': 2147483647}),
        }, 'optional': {'mask': ('MASK',)}}

    RETURN_TYPES = ('IMAGE', 'STRING', 'STRING')
    RETURN_NAMES = ('edited_image', 'provider_model', 'status_report')
    CATEGORY = 'H3/API'
    FUNCTION = 'edit'

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        # Consult new config each queue; the durable journal prevents paid replays.
        return float('nan')

    def edit(self, image, prompt, provider, model_alias, parameters, auto_failover, timeout_seconds, max_cost, request_nonce, mask=None):
        try:
            params = json.loads(parameters)
            images, mask_png = png_inputs(image, mask)
            engine = Engine(STORE, Path(os.environ.get('H3_ADAPTER_RUNTIME', str(STORE.path.parent / 'runtime.private'))))
            result = engine.edit(images, mask_png, prompt, model_alias, provider, auto_failover, params, timeout_seconds, max_cost, request_nonce)
        except Exception:
            result = {'images': [], 'report': {'status': 'failed', 'error': 'invalid_node_input_or_server_configuration', 'provider': None, 'model': None}}
        report = json.dumps(result['report'], ensure_ascii=False)
        info = json.dumps({name: result['report'].get(name) for name in ('provider', 'model', 'status', 'elapsed_ms')}, ensure_ascii=False)
        if result['report'].get('status') != 'success' or not result['images']:
            try:
                from comfy_execution.graph import ExecutionBlocker
            except ModuleNotFoundError as error:
                if error.name not in ('comfy_execution', 'comfy_execution.graph'):
                    raise
                # Standalone library callers retain the explicit empty-image contract.
                output = image_tensor([], image.shape)
            else:
                output = ExecutionBlocker('H3 API: ' + result['report'].get('status', 'failed') + '/' + str(result['report'].get('error')))
        else:
            output = image_tensor(result['images'], image.shape)
        return {'ui': {'report': [report]}, 'result': (output, info, report)}


NODE_CLASS_MAPPINGS = {'H3ImageEdit': H3ImageEdit}
NODE_DISPLAY_NAME_MAPPINGS = {'H3ImageEdit': 'H3 Universal Image Edit / 通用图像编辑'}
