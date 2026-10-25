"""Exercise a published candidate through actual preparation input and DX12."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.map_library import MapLibrary
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--visual-profile',type=Path,required=True)
    p.add_argument('--catalog',type=Path,required=True);p.add_argument('--version',required=True)
    p.add_argument('--roundtrip-version',help='Also choose another saved map,then return through actual UI input')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--warmup-frames',type=int,default=8);a=p.parse_args()
    if a.warmup_frames<3:p.error('At least three native frames are required for a loaded-scene check')
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    row=MapLibrary(a.catalog).resolve(a.version)
    g=FlightGame(render=True,visible=False,runtime=a.runtime,visual_profile=a.visual_profile,
        map_path=ROOT/'game/maps/training_range_v3/generated-map.json',map_catalog=a.catalog,
        output=a.output/'client',user_settings=a.output/'preferences.json')
    def click(id):
        g.frontend.layout();_,(x,y,w,h),_=next(r for r in g.frontend.regions if r[0]==id)
        g.input(SimpleNamespace(pressed=[1],held=[],x=x+w/2,y=y+h/2,quit=False,wheel=0),.02)
    def check_loaded_scene(label):
        if not hasattr(g.renderer,'depth_coverage'):
            raise RuntimeError('Rebuild renderer with actual GPU depth coverage diagnostics before certifying map switching')
        depth=json.loads(g.renderer.depth_coverage())
        timings=json.loads(g.renderer.frame_timings())
        write_json(a.output/(label+'-integrity.json'),{'depth':depth,'timings':timings})
        assert depth['invalid_pixels']==0 and depth['occupied_fraction']>.97,('Missing ground geometry after map selection',depth)
        assert timings['descriptors']['allocation_failures']==0,('GPU resource descriptor allocation failed',timings['descriptors'])
        return depth
    try:
        g.select_aircraft('F16');before=serialize(g.sim.frame());g.frontend.open_preparation(True)
        click('map_version');g.frontend.layout()
        option=next(r[0] for r in g.frontend.regions if r[2]==('option','map_version',row['id']))
        for _ in range(3):g.draw()
        dropdown=g.capture('candidate-map-dropdown')
        click(option)
        assert g.frontend.preparation['map_version']==row['id']
        assert serialize(g.sim.frame())==before
        for _ in range(3):g.draw()
        selected=g.capture('candidate-map-selected')
        click('launch')
        assert g.mode=='flight' and g.map_path==Path(row['map'])
        assert g.scene_hash==sha(g.map_path) and g.sim.frame().tick==0
        g.sim.set_paused(True);g.set_camera([1200,2482,-1500],[0,0,0],fov=1.)
        for _ in range(a.warmup_frames):g.draw(1/60)
        loaded=g.capture('candidate-map-loaded')
        loaded_depth=check_loaded_scene('first-load')
        loaded_settings=json.loads(g.renderer.visual_settings())
        roundtrip=[]
        if a.roundtrip_version:
            for number,id in enumerate([a.roundtrip_version,row['id']]):
                g.input(SimpleNamespace(pressed=[27],held=[],x=0,y=0,quit=False,wheel=0),.02)
                assert g.mode=='hangar'
                g.frontend.open_preparation(True);click('map_version');g.frontend.layout()
                option=next(r[0] for r in g.frontend.regions if r[2]==('option','map_version',id));click(option);click('launch')
                expected=MapLibrary(a.catalog).resolve(id)
                assert g.mode=='flight' and g.map_path==Path(expected['map']) and g.sim.frame().tick==0
                g.sim.set_paused(True);g.set_camera([1200,2482,-1500],[0,0,0],fov=1.)
                for _ in range(a.warmup_frames):g.draw(1/60)
                roundtrip.append({'id':id,'capture':g.capture('map-roundtrip-'+str(number)),
                    'depth':check_loaded_scene('roundtrip-'+str(number)),
                    'actual_settings':json.loads(g.renderer.visual_settings()),
                    'map_sha256':g.scene_hash,'primitive_id_state':json.loads(g.renderer.primitive_id_state()) if hasattr(g.renderer,'primitive_id_state') else None})
                print('MAP_UI_ROUNDTRIP',number,id,flush=True)
        assert g.renderer.shader_errors()==0
        assert not any(name in sys.modules for name in ('bvr_game.worldgen','bvr_game.map_authoring'))
        write_json(a.output/'report.json',{'status':'passed','version':row,'captures':[dropdown,selected,loaded],
            'first_load_depth':loaded_depth,
            'first_load_settings':loaded_settings,
            'roundtrip':roundtrip,
            'core_sha256':sha(Path(native.__file__)),'renderer_sha256':sha(Path(g.r.__file__)),
            'checks':['candidate present in actual dropdown','selection preserves paused core frame',
                      'confirmation loads exact published map at tick0','no runtime map generator imported',
                      'GPU depth covers the downlooking frame after each selection','zero descriptor allocation failures'],
            'shader_errors':0,'scope':'Actual UI input and DX12 rendering; visual reference match is not certified.'})
        print('CANDIDATE_MAP_UI_PASSED',flush=True)
    finally:g.close()
if __name__=='__main__':main()
