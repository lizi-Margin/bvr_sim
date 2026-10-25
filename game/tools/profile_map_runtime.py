"""Measure actual full-map frames, with buffered engine GPU timestamp ranges."""
from pathlib import Path
import argparse,json,os,statistics,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json
from game.tools.capture_reference_map import VIEWS,wicked

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--frames',type=int,default=16)
    p.add_argument('--warmup',type=int,default=8);p.add_argument('--views',nargs='+',choices=VIEWS,default=['reference_downlook','daylight_horizon'])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,map_path=a.map,visual_profile=a.visual_profile,output=a.output/'client')
    rows=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True)
        g.quality='high';g.renderer.set_quality('high');g.renderer.set_render_scale(1.)
        g.renderer.set_presentation_paused(True);g.renderer.set_profiling(True);g.show_hud=True
        core_before=serialize(g.sim.frame())
        for view in a.views:
            eye,target=VIEWS[view];g.set_camera(wicked(eye),wicked(target),fov=1.)
            frames=[]
            for i in range(a.warmup+a.frames):
                begin=time.perf_counter();g.draw(1/60);elapsed=(time.perf_counter()-begin)*1000
                timings=json.loads(g.renderer.frame_timings())
                if i>=a.warmup:frames.append({'wall_ms':elapsed,**timings})
                if (i+1)%4==0:print('PROFILE_FRAME',view,i+1,round(elapsed,2),flush=True)
                write_json(a.output/'progress.json',{'view':view,'frame':i+1,'wall_ms':elapsed,'timings':timings})
            wall=[f['wall_ms'] for f in frames]
            row={'view':view,'frames':frames,'median_ms':statistics.median(wall),'fps':1000/statistics.mean(wall),
                 'capture':g.capture(view),'statistics':serialize(g.renderer.statistics())}
            rows.append(row);write_json(a.output/'partial.json',{'views':rows})
        assert serialize(g.sim.frame())==core_before,'Rendering changed the paused simulation frame'
        write_json(a.output/'report.json',{'status':'measured','resolution':[1920,1080],'render_scale':1,'quality':'high','core_frame_unchanged':True,
            'map_sha256':g.scene_hash,'core_sha256':sha(Path(native.__file__)),'renderer_sha256':sha(Path(g.r.__file__)),
            'views':rows,'shader_errors':g.renderer.shader_errors(),
            'scope':'Paused simulation and fixed cameras; full source geometry retained. GPU times are delayed/smoothed engine timestamps; nested stages overlap. Other GPU workloads are not stopped.'})
        print('PROFILE_COMPLETE',flush=True)
    finally:g.close()
if __name__=='__main__':main()
