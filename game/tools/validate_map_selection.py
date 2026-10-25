"""Actual DX12 map dropdown, cancelled draft and confirmed baked-map switching."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.map_library import MapLibrary
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    versions=MapLibrary(a.catalog).versions();assert len(versions)>=2
    first,second=versions[:2];g=FlightGame(render=True,visible=False,runtime=a.runtime,map_path=Path(first['map']),map_catalog=a.catalog,output=a.output/'client',user_settings=a.output/'preferences.json')
    images=[];checks=[]
    def click(id):
        g.frontend.layout();_,(x,y,w,h),_=next(r for r in g.frontend.regions if r[0]==id)
        g.input(SimpleNamespace(pressed=[1],held=[],x=x+w/2,y=y+h/2,quit=False,wheel=0),.02)
    def choose(id):
        click('map_version');g.frontend.layout()
        option=next(r[0] for r in g.frontend.regions if r[2]==('option','map_version',id));click(option)
    def capture(name):
        for _ in range(3):g.draw()
        images.append(g.capture(name))
    try:
        g.select_aircraft('F16');before=serialize(g.sim.frame());config=serialize(g.config)
        g.frontend.open_preparation(True);click('map_version');capture('published-map-dropdown');click('map_version')
        choose(second['id']);capture('map-draft');click('back')
        assert g.map_path==Path(first['map']) and before==serialize(g.sim.frame()) and config==serialize(g.config)
        checks.append('map_draft_cancel_preserves_actual_map_and_complete_core_frame')
        for i,version in enumerate((second,first)):
            g.frontend.open_preparation(True);choose(version['id']);click('launch')
            assert g.mode=='flight' and g.map_path==Path(version['map']) and g.sim.frame().tick==0
            assert g.scene_hash==sha(g.map_path)
            capture('loaded-version-'+str(i))
            g.input(SimpleNamespace(pressed=[27],held=[],x=0,y=0,quit=False,wheel=0),.02)
            assert g.mode=='hangar'
        checks.append('two_baked_versions_load_and_return_in_one_native_client')
        assert not any(m in sys.modules for m in ('bvr_game.worldgen','bvr_game.map_authoring'))
        checks.append('no_offline_generator_imported_during_menu_or_sortie_loading')
        assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'passed','checks':checks,'captures':images,'versions':[first,second],
            'renderer':str(g.r.__file__),'renderer_sha256':sha(Path(g.r.__file__)),'core_sha256':sha(Path(native.__file__)),
            'shader_errors':0,'last_map_sha256':g.scene_hash,'scope':'Actual DX12 frames and client input; two complete saved maps, not recipe generation or visual reference-match certification.'})
        print('BAKED_MAP_SELECTION_PASSED',flush=True)
    finally:g.close()
if __name__=='__main__':main()
