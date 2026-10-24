"""Fixed actual DX12 aircraft views; source data is never rewritten."""
from pathlib import Path
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    p.add_argument('--runtime',type=Path,default=ROOT/'game/runtime.json')
    p.add_argument('--views',nargs='+',choices=['rear_quarter','front_quarter','top','nozzle','canopy']);a=p.parse_args()
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,visual_profile=a.visual_profile,runtime=a.runtime,output=a.output/'client');rows=[]
    try:
        g.show_hud=False;g.renderer.set_quality('high')
        for model in ['F22','F16']:
            g.select_aircraft(model);g.config.mission='training';g.start(start_position=[-20000,0,8500],initial_speed=300)
            own=g.player();n,w,h=own.position;origin=[-w,h,n]
            for name,offset,focus in [('rear_quarter',[24,10,-26],[0,0,0]),('front_quarter',[24,9,26],[0,0,0]),
                    ('top',[.1,32,-10],[0,0,0]),('nozzle',[7,3,-17],[0,0,0]),('canopy',[4.5,3.2,7],[0,.7,4.5])]:
                if a.views and name not in a.views:continue
                eye=[a+b for a,b in zip(origin,offset)];target=[a+b for a,b in zip(origin,focus)];g.set_camera(eye,target,.72)
                for _ in range(40):g.draw()
                rows.append({'model':model,'view':name,'core_pose':serialize(own),'camera':g.camera_params,
                    'capture':g.capture(model+'-'+name),'shader_errors':g.renderer.shader_errors(),
                    'aircraft_statistics':serialize(g.renderer.aircraft_statistics())})
        write_json(a.output/'report.json',{'views':rows,'renderer_settings':json.loads(g.renderer.visual_settings()),
            'visual_profile':str(a.visual_profile),'visual_profile_sha256':sha(a.visual_profile),'shader_errors':g.renderer.shader_errors(),
            'core_sha256':sha(Path(native.__file__)),'renderer_sha256':sha(Path(g.r.__file__)),
            'scope':'Fixed real DX12 views; physical time is not advanced. Motion and performance require separate validation.'})
        print('AIRCRAFT_SURFACE_VIEWS',len(rows),'SHADER_ERRORS',g.renderer.shader_errors())
    finally:g.close()
if __name__=='__main__':main()
