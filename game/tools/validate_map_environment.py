"""Actual saved-weather switching on an isolated sky fixture, with core held paused."""
from pathlib import Path
from types import SimpleNamespace
import argparse,copy,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json
from bvr_game.map_library import ENVIRONMENT_KEYS
from bvr_game.scene_runtime import BakedScene

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','profile','runtime','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    source=BakedScene(a.source);doc=copy.deepcopy(source.document)
    doc['terrain']['file']=str(source.height_file)
    if doc['terrain'].get('ground_atlas'):
        doc['terrain']['ground_atlas']['file']=str((a.source.parent/doc['terrain']['ground_atlas']['file']).resolve())
    doc.update(instances=[],surfaces=[],resource_versions={},chunks={})
    doc['environment']={'contact_surfaces':[],'obstacles':[],'water_regions':[],'decorative_instance_ids':[]}
    doc.pop('baked_environment',None)
    doc['validation_fixture']={'source_map_sha256':sha(a.source),'scope':'Isolated environment switching, no whole-map art acceptance'}
    clear=a.output/'clear.json';cloudy=a.output/'cloudy.json';write_json(clear,doc)
    profile=json.loads(a.profile.read_text(encoding='utf8'))
    doc['baked_environment']={'schema_version':1,'profile':{k:profile[k] for k in ENVIRONMENT_KEYS if k in profile}}
    write_json(cloudy,doc)
    versions=[{'id':str(path.resolve()),'label':path.stem,'map':str(path.resolve()),'quality':'external'} for path in (clear,cloudy)]
    g=FlightGame(render=True,visible=False,width=1280,height=720,runtime=a.runtime,map_path=clear,output=a.output/'client',user_settings=a.output/'preferences.json')
    g.map_library=SimpleNamespace(versions=lambda:versions)
    captures=[];checks=[]
    def observe(name):
        g.sim.set_paused(True);g.show_hud=False;g.set_camera([3000,2200,-4000],[-2000,8000,1000],fov=1.)
        for _ in range(8):g.draw(1/60)
        captures.append(g.capture(name));return json.loads(g.renderer.visual_settings())
    def choose(path):
        g.frontend.open_preparation(True);g.frontend.action(('option','map_version',str(path.resolve())))
    try:
        base=copy.deepcopy(g.visual_profile);before=serialize(g.sim.frame());config=serialize(g.config)
        choose(cloudy);g.frontend.action(('cancel',))
        assert g.visual_profile==base and serialize(g.sim.frame())==before and serialize(g.config)==config
        checks.append('cancel_keeps_weather_map_config_and_complete_core_frame')
        choose(cloudy);g.frontend.launch();cloud_settings=observe('saved-clouds')
        assert g.map_path==cloudy.resolve() and g.sim.frame().tick==0
        assert cloud_settings['actual_environment']['volumetric_clouds']
        assert abs(cloud_settings['actual_environment']['sky_exposure']-profile['sky_exposure'])<1e-5
        for key in ('ray_steps','step_distribution_m','initial_step_scale','coverage'):
            assert abs(cloud_settings['actual_cloud_layer'][key]-profile['cloud_layer'][key])<1e-5
        assert all(g.visual_profile.get(k)==base.get(k) for k in base if k not in ENVIRONMENT_KEYS)
        checks.append('confirmed_map_restores_actual_saved_weather_and_preserves_client_material_settings')
        before=serialize(g.sim.frame());settings=copy.deepcopy(cloud_settings['actual_environment'])
        try:g.renderer.apply_environment(json.dumps({'cloud_layer':{'ray_steps':0}}))
        except ValueError:pass
        else:raise AssertionError('Invalid cloud sampling accepted')
        for _ in range(2):g.draw(1/60)
        assert json.loads(g.renderer.visual_settings())['actual_environment']==settings
        assert serialize(g.sim.frame())==before
        checks.append('invalid_native_weather_rejected_without_partial_change_or_core_step')
        g.input(SimpleNamespace(pressed=[27],held=[],x=0,y=0,quit=False,wheel=0),.02)
        assert g.mode=='hangar'
        choose(clear);g.frontend.launch();clear_settings=observe('legacy-default-weather')
        assert g.visual_profile==base and g.map_path==clear.resolve() and g.sim.frame().tick==0
        assert not clear_settings['actual_environment']['volumetric_clouds']
        assert abs(clear_settings['actual_environment']['sky_exposure']-base['sky_exposure'])<1e-5
        assert clear_settings['actual_cloud_layer']['ray_steps']==96
        checks.append('legacy_map_restores_base_sky_and_engine_cloud_sampling_defaults')
        assert not any(m in sys.modules for m in ('bvr_game.worldgen','bvr_game.map_authoring'))
        assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'passed','checks':checks,'captures':captures,'saved_settings':cloud_settings,
            'restored_settings':clear_settings,'source_map_sha256':sha(a.source),'renderer_sha256':sha(Path(g.r.__file__)),
            'core_sha256':sha(Path(native.__file__)),'shader_errors':0,'scope':'Real DX12 weather and confirmed/cancelled client selections on an isolated sky fixture. No whole-map visual acceptance.'})
        print('SAVED_MAP_ENVIRONMENT_PASSED',flush=True)
    finally:g.close()

if __name__=='__main__':main()
