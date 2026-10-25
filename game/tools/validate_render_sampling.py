"""Direct typed renderer: frozen weather and supersampling, without frontend dependencies."""
from pathlib import Path
import argparse,copy,importlib,json,os,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.scene_runtime import BakedScene
from bvr_game.content import sha,write_json,ASSETS
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native

def snapshot(value):
    if isinstance(value,(str,int,float,bool,type(None))):return value
    if hasattr(value,'name') and hasattr(value,'value'):return value.name
    if isinstance(value,(list,tuple)):return [snapshot(x) for x in value]
    if isinstance(value,dict):return {str(k):snapshot(v) for k,v in value.items()}
    return {k:snapshot(getattr(value,k)) for k in dir(value) if not k.startswith('_') and not callable(getattr(value,k))}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('map','profile','runtime','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--crop-nwu',type=float,nargs=3,metavar=('N','W','HALF_SIZE'))
    p.add_argument('--shadow-comparison',action='store_true')
    p.add_argument('--frames',type=int,default=32);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source=BakedScene(a.map);document=copy.deepcopy(source.document)
    if a.crop_nwu:
        n,w,half=a.crop_nwu
        document['instances']=[x for x in document['instances'] if abs(x['position'][0]-n)<=half and abs(x['position'][1]-w)<=half]
        ids={x['model'] for x in document['instances']}
        document['resource_versions']={k:v for k,v in document['resource_versions'].items() if k in ids}
    scene=BakedScene(a.map,document)
    runtime=json.loads(a.runtime.read_text(encoding='utf8'));sys.path.insert(0,runtime['renderer_module'])
    dll=os.add_dll_directory(runtime['renderer_module']) if os.name=='nt' else None
    bindings=importlib.import_module('bvr_game_render');models={}
    if getattr(bindings,'GAME_API_ABI',None)!=getattr(native,'GAME_API_ABI',None):raise RuntimeError('Use matching core and renderer Game API ABI versions')
    for id,version in document['resource_versions'].items():
        for i,lod in enumerate(version['lods']):models[id if i==0 else id+'::lod'+str(i)]=str(ASSETS/'registered'/id/lod['file'])
    renderer=bindings.Renderer(1920,1080,False,runtime['engine_source'],runtime['shader_cache'],models,str(a.profile.resolve()))
    sim=native.GameSession(str(a.output/'simulation.log'));sim.set_paused(True);rows=[]
    try:
        terrain=scene.terrain(native);sim.set_terrain(terrain)
        profile=json.loads(a.profile.read_text(encoding='utf8'));scene.configure(renderer,bindings,terrain,profile)
        renderer.presentation(False);renderer.set_quality('high')
        renderer.camera([2800,2400,-3800],[-100,220,300],1.)
        frame=sim.frame();before=snapshot(frame)
        cases=[('frozen-scale1',1,True,None),('frozen-scale2',2,True,None),('animated-scale1',1,False,None)]
        if a.shadow_comparison:cases=[('shadow-default',1,True,[8,80,800]),('shadow-aviation',1,True,[96,800,4000,12000]),('shadow-distant',1,True,[1000,4000,12000,30000])]
        for name,scale,paused,cascades in cases:
            renderer.set_presentation_paused(paused);renderer.set_render_scale(scale)
            if cascades:renderer.set_shadow_cascades(cascades)
            initial=None
            for i in range(a.frames):
                renderer.render(frame,[],[])
                if i==0:initial=json.loads(renderer.visual_settings())['actual_output']
                if (i+1)%4==0:print('SAMPLING_FRAME',name,i+1,flush=True)
            settings=json.loads(renderer.visual_settings());actual=settings['actual_output']
            assert actual['render_frame_count']>initial['render_frame_count']
            assert actual['internal_resolution']==[1920*scale,1080*scale]
            if paused:assert actual['presentation_time_s']==initial['presentation_time_s']
            else:assert actual['presentation_time_s']>initial['presentation_time_s']
            assert before==snapshot(sim.frame())
            image=renderer.capture(str(a.output/(name+'.png')))
            spatial_std=np.asarray(Image.open(image).convert('RGB'),dtype=float).std(axis=(0,1)).tolist()
            assert np.mean(spatial_std)>15,('Terrain fixture rendered empty or nearly uniform',name,spatial_std)
            rows.append({'name':name,'capture':image,'settings':settings,'first_frame':initial,'image_spatial_std_rgb':spatial_std,'statistics':snapshot(renderer.statistics())})
        settings=json.loads(renderer.visual_settings())['actual_output']
        try:renderer.set_render_scale(.5)
        except ValueError:pass
        else:raise AssertionError('Invalid render scale accepted')
        assert json.loads(renderer.visual_settings())['actual_output']==settings
        assert renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'passed','map':str(a.map.resolve()),'map_sha256':sha(a.map),
            'profile_sha256':sha(a.profile),'crop_nwu':a.crop_nwu,'instances':len(document['instances']),
            'renderer_sha256':sha(Path(bindings.__file__)),'core_sha256':sha(Path(native.__file__)),
            'captures':rows,'core_frame_unchanged':True,'shader_errors':0,
            'scope':'Actual DX12 quality diagnostics with unchanged highest-detail geometry inside the declared crop. Excluded scenery is a diagnostic fixture; not whole-map acceptance or a runtime distance-culling policy.'})
        print('RENDER_SAMPLING_PASSED',flush=True)
    finally:sim.close();renderer.close()

if __name__=='__main__':main()
