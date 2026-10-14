"""A2 whole-image bridge. Delegates matching/cache to the installed H3 Core.
Only Finish has lazy costly inputs. Every display depends on Finish.
No masks are manufactured; READY means a completed pipeline, not a visual quality certificate.
"""
import hashlib,importlib,json,inspect,threading
from pathlib import Path
import numpy as np
import torch
CATEGORY='H3/A2 Background'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False,allow_nan=False,separators=(',',':')).encode()).hexdigest()

def registry():
    import nodes
    return nodes.NODE_CLASS_MAPPINGS

def core():
    cls=registry().get('H3CBackgroundResolve')
    if cls is None:raise RuntimeError('Install H3 Background Core feature/background-reference-nodes (e1516896).')
    return importlib.import_module(cls.__module__)

def adapter():
    cls=registry().get('H3ImageEdit')
    if cls is None:raise RuntimeError('Install the supplied audited ComfyUI-H3-Adapter candidate.')
    module=importlib.import_module(cls.__module__)
    pinned=json.loads((Path(__file__).parent/'adapter-required-sha256.json').read_text(encoding='utf-8'))
    root=Path(module.__file__).parent
    for name,expected in pinned.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=expected:
            raise RuntimeError('H3 adapter source differs from the audited candidate: '+name)
    return module

def state(task):
    if getattr(task,'cleaned',True):raise ValueError('Background task is closed')
    if not hasattr(task,'_a2'):
        task._a2={'exact':{},'recipes':{},'tokens':{},'api':{},'prompts':{},'lock':threading.RLock()}
    return task._a2

def image(value,name,shape=None):
    if value is None or not isinstance(value,torch.Tensor) or value.ndim!=4 or value.shape[0]!=1 or value.shape[-1]!=3:
        raise ValueError(name+' must be one RGB IMAGE, not empty/None')
    if not torch.isfinite(value).all() or value.min()<0 or value.max()>1:raise ValueError(name+' must be finite [0,1]')
    if shape is not None and tuple(value.shape[1:])!=tuple(shape):raise ValueError(name+' has wrong H/W/C')
    return value

def raw_key(candidate):
    h=hashlib.sha256()
    for array in (candidate.image,candidate.foreground_mask,candidate.depth):
        if array is None:h.update(b'None');continue
        # Exact source reuse is deliberately stronger than perceptual similarity.
        array=np.ascontiguousarray(array)
        h.update(str((array.shape,array.dtype.str)).encode());h.update(array.tobytes())
    h.update(str(candidate.background_only).encode())
    return h.hexdigest()

class H3A2Recipe:
    @classmethod
    def INPUT_TYPES(cls):
        return {'required':{'denoise':('FLOAT',{'forceInput':True}),
            'removal_prompt':('STRING',{'multiline':True,'default':'移除所有人物及其携带的随身物品，完整重建遮挡的墙壁、门窗、地板和家具。保持原始布局、镜头视角、透视、光照与真实材质；不新增人物、人体、倒影或文字。'}),
            'api_node_id':('STRING',{'default':'7300'}),'z_node_id':('STRING',{'default':'7411'}),
            'base_nonce':('INT',{'default':0,'min':0,'max':2147483647})},
            'hidden':{'prompt':'PROMPT'}}
    RETURN_TYPES=('STRING','STRING','INT')
    RETURN_NAMES=('revision','api_prompt','request_nonce')
    FUNCTION='run';CATEGORY=CATEGORY
    @classmethod
    def IS_CHANGED(cls,**kwargs):return float('nan')
    def run(self,denoise,removal_prompt,api_node_id,z_node_id,base_nonce,prompt):
        ad=adapter();store=ad.STORE;cfg=store.load()
        spec=prompt[str(api_node_id)];api_inputs={k:v for k,v in spec['inputs'].items() if k not in {'image','mask','prompt','request_nonce'}}
        if any(isinstance(v,list) and len(v)==2 for v in api_inputs.values()):
            raise ValueError('Recipe must inspect literal API settings; keep provider/model/parameters widgets on H3ImageEdit')
        selected=api_inputs.get('provider','auto')
        pid=cfg['primary'] if selected=='auto' else selected
        provider=next((p for p in cfg['providers'] if p['id']==pid),None)
        key=store.credential(provider,expected_revision=cfg.revision) if provider else ''
        # The primary request contract excludes unused backups, keys and budget controls.
        # A successful backup is still authorized against its own saved credential by Engine.
        contract={k:provider.get(k) for k in ('id','base_url','protocol','edit_path','request','upload','async','result','auth','account_id')} if provider else {'id':pid}
        model=provider.get('models',{}).get(api_inputs.get('model_alias','background-edit')) if provider else None
        contract['model']={k:model.get(k) for k in ('id','defaults','mask_encoding')} if model else None
        settings={k:v for k,v in api_inputs.items() if k not in {'timeout_seconds','max_cost','auto_failover'}}
        if 'parameters' in settings:
            settings['parameters']=json.loads(settings['parameters'])
        request_revision=digest({'settings':settings,'contract':contract,'base_nonce':base_nonce})
        account=[store.credential_fingerprint(key) if key else '',cfg.credential_generations.get(pid,0)]
        api_revision=digest({'request':request_revision,'account':account,'prompt':removal_prompt})
        # Identity travels through the INT connection, never through the editing instruction.
        api_prompt=removal_prompt
        seen=set()
        def snapshot(nid):
            nid=str(nid)
            if nid in seen:raise ValueError('Cycle in Z-Image recipe')
            seen.add(nid);spec=prompt[nid];inputs={}
            for key,value in spec['inputs'].items():
                if key in {'task','view','wash_token','completion','unique_id'}:continue
                if isinstance(value,list) and len(value)==2 and str(value[0]) in prompt:
                    parent=prompt[str(value[0])]
                    if parent['class_type'] in {'H3A2APIGuard','H3A2BackgroundResolve','H3A2Recipe','H3A2StageImages'}:continue
                    inputs[key]={'node':snapshot(value[0]),'output':value[1]}
                else:inputs[key]=value
            cls=registry().get(spec['class_type']);implementation='unavailable'
            if cls:
                filename=inspect.getsourcefile(cls)
                if filename and Path(filename).is_file():implementation=hashlib.sha256(Path(filename).read_bytes()).hexdigest()
            # Same model filename with updated local weights invalidates the result.
            models={}
            try:
                import folder_paths
                for field,category in [('unet_name','diffusion_models'),('clip_name','text_encoders'),('vae_name','vae')]:
                    if field in inputs:
                        model_path=folder_paths.get_full_path(category,inputs[field])
                        if model_path:
                            st=Path(model_path).stat();models[field]=[str(Path(model_path).resolve()),st.st_size,st.st_mtime_ns]
            except (ImportError,KeyError):pass
            seen.remove(nid)
            return {'class':spec['class_type'],'inputs':inputs,'implementation':implementation,'model_files':models}
        z=snapshot(z_node_id)
        revision=digest({'bridge_version':1,'bridge_source':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'api':api_revision,'z':z,'denoise':float(denoise)})
        return revision,api_prompt,int(request_revision,16)

class H3A2BackgroundResolve:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'candidate':('BACKGROUND_CANDIDATE',),'revision':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('BACKGROUND_VIEW','BACKGROUND_DECISION','IMAGE','STRING','STRING','BOOLEAN')
    RETURN_NAMES=('view','decision','clean_background','view_id','state','ready')
    FUNCTION='run';CATEGORY=CATEGORY
    def run(self,task,candidate,revision):
        c=core();s=state(task)
        if candidate.task_id!=task.task_id:raise ValueError('Cross-task candidate')
        if not revision:raise ValueError('Recipe revision missing')
        key=(revision,raw_key(candidate))
        with s['lock']:
            if key in s['exact']:
                view=task.cache.get(s['exact'][key])
                contracts=importlib.import_module(c.BackgroundView.__module__)
                matcher_module=importlib.import_module(type(task.matcher).__module__)
                decision=contracts.EnvironmentDecision(task.task_id,candidate.key,'REUSE_EXISTING',view.environment_id,view.view_id,
                    confidence=1.,reason='Exact raw pixels, aligned evidence and full processing recipe match',
                    report={'reuse_basis':'exact_source_and_recipe','physical_identity_proven':False},
                    decision_key=matcher_module.production_request_key(candidate,revision))
            else:
                allowed={v for v,r in s['recipes'].items() if r==revision}
                class FilteredMatcher:
                    def match_for_production(self,query,views,revision='default'):
                        return task.matcher.match_for_production(query,[v for v in views if v.view_id in allowed],revision=revision)
                decision,view=task.cache.resolve(candidate,FilteredMatcher(),revision)
                s['exact'][key]=view.view_id;s['recipes'][view.view_id]=revision
            clean=c._image_output(view.clean_background) if view.state=='READY' else None
            if clean is not None:image(clean,'cached background',view.candidate.image.shape)
            return view,decision,clean,view.view_id,view.state,clean is not None

class H3A2BackgroundWashClaim:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'view':('BACKGROUND_VIEW',)}}
    RETURN_TYPES=('STRING','BOOLEAN','STRING');RETURN_NAMES=('wash_token','claimed','view_id');FUNCTION='run';CATEGORY=CATEGORY
    def run(self,task,view):
        s=state(task)
        if view.task_id!=task.task_id:raise ValueError('Cross-task view')
        with s['lock']:
            current=task.cache.get(view.view_id)
            if current.state=='READY':return '',False,view.view_id
            token=s['tokens'].get(view.view_id)
            if token is None:
                token=task.cache.claim_wash(view.view_id)
                if not token:raise RuntimeError('View already claimed by another owner; no duplicate dispatch')
                s['tokens'][view.view_id]=token
            return token,True,view.view_id

class H3A2APISource:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'view':('BACKGROUND_VIEW',),'wash_token':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('IMAGE',);RETURN_NAMES=('original_candidate',);FUNCTION='run';CATEGORY=CATEGORY
    def run(self,task,view,wash_token):
        s=state(task)
        if view.task_id!=task.task_id or not wash_token or s['tokens'].get(view.view_id)!=wash_token:raise ValueError('Unowned wash')
        if task.cache.get(view.view_id).state!='PENDING':raise ValueError('API input requested for a completed view')
        return (image(core()._image_output(view.candidate.image),'source candidate'),)

class H3A2APIGuard:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'view':('BACKGROUND_VIEW',),'api_image':('IMAGE',),'status_report':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('IMAGE',);RETURN_NAMES=('valid_api_background',);FUNCTION='run';CATEGORY=CATEGORY
    def run(self,task,view,api_image,status_report):
        s=state(task)
        if view.task_id!=task.task_id:raise ValueError('Cross-task API result')
        report=json.loads(status_report)
        if report.get('status')!='success':raise RuntimeError('API background unavailable: '+str(report.get('status'))+'/'+str(report.get('error')))
        value=image(api_image,'API background')
        # Preserve scene geometry: only same-aspect resolution changes may resize.
        source_h,source_w=value.shape[1:3]
        target_h,target_w=view.candidate.image.shape[:2]
        if source_w*target_h!=target_w*source_h:
            raise ValueError('API background aspect ratio differs from source; require provider output with the original aspect ratio')
        if tuple(value.shape[1:])!=tuple(view.candidate.image.shape):
            value=torch.nn.functional.interpolate(value.movedim(-1,1),size=view.candidate.image.shape[:2],mode='bilinear',align_corners=False).movedim(1,-1)
        s['api'][view.view_id]=value.detach().cpu().clone()
        return (image(value,'aligned API background',view.candidate.image.shape),)

class H3A2PromptCapture:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'view':('BACKGROUND_VIEW',),'text':('STRING',{'forceInput':True})}}
    RETURN_TYPES=('STRING',);RETURN_NAMES=('scene_prompt',);FUNCTION='run';CATEGORY=CATEGORY
    def run(self,task,view,text):
        if view.task_id!=task.task_id or not isinstance(text,str) or not text.strip():raise ValueError('Invalid scene prompt')
        state(task)['prompts'][view.view_id]=text
        return (text,)

class H3A2BackgroundFinish:
    @classmethod
    def INPUT_TYPES(cls):return {'required':{'task':('BACKGROUND_TASK',),'view':('BACKGROUND_VIEW',),'clean_background':('IMAGE',{'lazy':True}),'wash_token':('STRING',{'forceInput':True}),'api_background':('IMAGE',{'lazy':True})}}
    RETURN_TYPES=('BACKGROUND_VIEW','IMAGE','STRING','BOOLEAN','IMAGE','STRING','IMAGE')
    RETURN_NAMES=('view','clean_background','report','ready','A_original','scene_prompt','B_api')
    FUNCTION='run';CATEGORY=CATEGORY
    def check_lazy_status(self,task,view,clean_background=None,wash_token='',api_background=None):
        if view.task_id!=task.task_id:raise ValueError('Cross-task finish')
        current=task.cache.get(view.view_id)
        if current.state=='READY':return []
        if current.state!='PENDING':raise RuntimeError('Invalid background state')
        s=state(task)
        if not wash_token or s['tokens'].get(view.view_id)!=wash_token:raise ValueError('Finish requires own claim')
        # Request API first. No Qwen/Z-Image dependency is made until it succeeds.
        if api_background is None:return ['api_background']
        image(api_background,'API prerequisite',view.candidate.image.shape)
        return ['clean_background'] if clean_background is None else []
    def run(self,task,view,clean_background=None,wash_token='',api_background=None):
        if view.task_id!=task.task_id:raise ValueError('Cross-task finish')
        s=state(task);c=core();current=task.cache.get(view.view_id);hit=current.state=='READY'
        api=s['api'].get(view.view_id)
        if api is None:raise RuntimeError('Completed pipeline API evidence missing')
        image(api,'recorded API evidence',view.candidate.image.shape)
        if not hit:
            if current.state!='PENDING':raise RuntimeError('Invalid background state')
            image(api_background,'API prerequisite',view.candidate.image.shape)
            result=image(clean_background,'Z-Image decoded result',view.candidate.image.shape)
            if not wash_token or s['tokens'].get(view.view_id)!=wash_token:raise ValueError('Unowned result')
            current=task.cache.attach_clean(view.view_id,result.detach().cpu().numpy()[0],wash_token=wash_token)
        if current.state!='READY' or current.clean_background is None:raise RuntimeError('No completed background')
        clean=image(c._image_output(current.clean_background),'READY result',view.candidate.image.shape)
        api=s['api'].get(view.view_id)
        if api is None:raise RuntimeError('Completed pipeline API evidence missing')
        packet=(c._image_output(current.candidate.image),api,clean)
        report=json.dumps({'view_id':view.view_id,'state':'READY','pipeline':'API+Z-Image','cache_hit':hit,
            'quality_verified':False,'reuse_basis':'exact_source_or_core_verified_geometry'},ensure_ascii=False)
        return {'ui':{'text':[report]},'result':(current,clean,report,True,packet[0],s['prompts'].get(view.view_id,''),packet[1])}

NODE_CLASS_MAPPINGS={cls.__name__:cls for cls in (H3A2Recipe,H3A2BackgroundResolve,H3A2BackgroundWashClaim,H3A2APISource,H3A2APIGuard,H3A2PromptCapture,H3A2BackgroundFinish)}
NODE_DISPLAY_NAME_MAPPINGS={k:k.replace('H3A2','A2 ') for k in NODE_CLASS_MAPPINGS}
