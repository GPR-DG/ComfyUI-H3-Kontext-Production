"""Load this package with an existing official ComfyUI host; use only local Mock HTTP."""
import argparse
import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
from contextlib import closing

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--host', required=True, help='Existing ComfyUI checkout')
parser.add_argument('--work', required=True, help='Writable scratch directory')
args=parser.parse_args()
root=Path(__file__).resolve().parents[1]
work=Path(args.work).resolve()
work.mkdir(parents=True, exist_ok=True)
(work/'user').mkdir(exist_ok=True)
# The host consumes argv when its modules load. All host file output stays in scratch.
sys.argv=[sys.argv[0], '--cpu', '--disable-auto-launch', '--disable-assets', '--user-directory', str(work/'user'), '--output-directory', str(work/'output'), '--temp-directory', str(work/'temp')]
sys.path.insert(0,str(Path(args.host).resolve()))
import comfy.options
comfy.options.enable_args_parsing()
import torch
import nodes as host_nodes
import folder_paths
folder_paths.set_output_directory(str(work/'output'))
folder_paths.set_temp_directory(str(work/'temp'))
folder_paths.set_user_directory(str(work/'user'))
from server import PromptServer
loop=asyncio.new_event_loop()
asyncio.set_event_loop(loop)
from app.assets.manager import default_asset_manager
server=PromptServer(loop, default_asset_manager())
loaded=loop.run_until_complete(host_nodes.load_custom_node(str(root)))
assert loaded is True
expected_nodes={'H3ImageEdit','H3A2Recipe','H3A2BackgroundResolve',
                'H3A2BackgroundWashClaim','H3A2APISource','H3A2APIGuard',
                'H3A2PromptCapture','H3A2BackgroundFinish'}
assert expected_nodes <= host_nodes.NODE_CLASS_MAPPINGS.keys()
bridge=sys.modules[host_nodes.NODE_CLASS_MAPPINGS['H3A2Recipe'].__module__]
assert bridge.adapter() is sys.modules[host_nodes.NODE_CLASS_MAPPINGS['H3ImageEdit'].__module__]
cls=host_nodes.NODE_CLASS_MAPPINGS['H3ImageEdit']
assert cls.RETURN_TYPES==('IMAGE','STRING','STRING')
assert cls.INPUT_TYPES()['required']['image']==('IMAGE',)
assert cls.INPUT_TYPES()['optional']['mask']==('MASK',)
route_paths={route.path for route in server.routes}
assert {'/h3-adapter/config','/h3-adapter/key','/h3-adapter/models'} <= route_paths
node_module=sys.modules[cls.__module__]
sys.path.insert(0,str(root/'tests'))
from mock_api import MockAPI
store_class=node_module.ConfigStore
engine_class=node_module.Engine
results=[]
with tempfile.TemporaryDirectory(dir=work) as folder, closing(MockAPI()) as peer:
    folder=Path(folder)
    config=json.loads((root/'config/providers.example.json').read_text())
    p=config['providers'][0]
    p.update(enabled=True, base_url=peer.url('primary'), key_env='', allow_insecure_localhost=True)
    p['models']['background-edit'].update(id='synthetic-edit', supports_mask=True, price_upper_bound=0)
    store=store_class(folder/'providers.json')
    store.save(config)
    store.save_key('primary','FINAL-SYNTHETIC-HOST-KEY')
    with patch.object(node_module,'STORE',store), patch.dict(os.environ,{'H3_ADAPTER_RUNTIME':str(folder/'runtime')}):
        image=torch.zeros((1,2,2,3))
        for nonce,mask in [(0,None),(1,torch.ones((1,2,2)))]:
            params=dict(image=image,prompt='local mock edit',provider='auto',model_alias='background-edit',parameters='{}',auto_failover=True,timeout_seconds=10,max_cost=1,request_nonce=nonce,mask=mask)
            output=cls().edit(**params)
            tensor,info,text=output['result']
            report=json.loads(text)
            assert report['status']=='success',report
            assert tuple(tensor.shape)==(1,2,2,3)
            assert tensor.dtype==torch.float32
            assert not torch.equal(tensor,image)
            before=len(peer.calls(method='POST'))
            replay=cls().edit(**params)
            assert json.loads(replay['result'][2])['cached'] is True
            assert len(peer.calls(method='POST'))==before
            # Exercise the host's own SaveImage / PreviewImage consumer against the output tensor.
            saved=host_nodes.SaveImage().save_images(tensor,filename_prefix='h3_mock')
            preview=host_nodes.PreviewImage().save_images(tensor,filename_prefix='h3_mock_preview')
            assert len(saved['ui']['images'])==1 and len(preview['ui']['images'])==1
            results.append({'mask':mask is not None,'status':'success','cached_replay':True,'shape':list(tensor.shape),'host_save_preview':True})
        assert len(peer.calls(method='POST'))==2
print(json.dumps({'official_host_import':True,'registered_nodes':sorted(expected_nodes),'bridge_hashes_verified':True,'routes_registered':True,'cases':results,'edit_POSTs':2},indent=2))
loop.close()
