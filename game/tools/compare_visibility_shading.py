"""Compare full source raster and visibility shading in one real DX12 scene."""
from pathlib import Path
import argparse,json,os,statistics,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json
from game.tools.capture_reference_map import VIEWS,wicked

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--visual-profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--views',nargs='+',choices=VIEWS,default=['bridge_oblique','reference_downlook','daylight_horizon'])
    p.add_argument('--warmup',type=int,default=6);p.add_argument('--frames',type=int,default=4);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,map_path=a.map,visual_profile=a.visual_profile,output=a.output/'client',map_environment=False)
    rows=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True);before=serialize(g.sim.frame())
        g.show_hud=False;g.quality='high';g.renderer.set_quality('high');g.renderer.set_presentation_paused(True);g.renderer.set_profiling(True)
        for view in a.views:
            eye,target=VIEWS[view];g.set_camera(wicked(eye),wicked(target),fov=1.)
            for mode in [False,True]:
                g.renderer.set_visibility_compute(mode);frames=[]
                label=view+('-visibility' if mode else '-raster');print('VISIBILITY_BEGIN',label,flush=True)
                for i in range(a.warmup+a.frames):
                    begin=time.perf_counter();g.draw(1/60);ms=(time.perf_counter()-begin)*1000
                    sample={'wall_ms':ms,'timings':json.loads(g.renderer.frame_timings())}
                    if i>=a.warmup:frames.append(sample)
                    write_json(a.output/'progress.json',{'view':view,'mode':mode,'frame':i+1,**sample})
                    if (i+1)%2==0:print('VISIBILITY_FRAME',label,i+1,round(ms,2),flush=True)
                row={'view':view,'visibility':mode,'frames':frames,'median_ms':statistics.median(f['wall_ms'] for f in frames),
                    'fps':1000/statistics.mean(f['wall_ms'] for f in frames),'capture':g.capture(label),
                    'depth':json.loads(g.renderer.depth_coverage()),'statistics':serialize(g.renderer.statistics()),
                    'shader_errors':g.renderer.shader_errors(),'settings':json.loads(g.renderer.visual_settings())}
                assert row['shader_errors']==0
                assert row['settings']['actual_output']['visibility_compute_shading']==mode
                assert frames[-1]['timings']['descriptors']['allocation_failures']==0
                rows.append(row);write_json(a.output/'partial.json',{'views':rows})
        assert serialize(g.sim.frame())==before
        write_json(a.output/'report.json',{'status':'captured_not_visual_acceptance','views':rows,'map_sha256':g.scene_hash,
            'renderer_sha256':sha(Path(g.r.__file__)),'core_sha256':sha(Path(native.__file__)),'core_frame_unchanged':True,
            'scope':'Same loaded source geometry and cameras, paired raster/compute toggles. Actual image review required; GPU timestamp stages are delayed/smoothed.'})
        print('VISIBILITY_COMPARISON_COMPLETE',flush=True)
    finally:g.close()
if __name__=='__main__':main()
