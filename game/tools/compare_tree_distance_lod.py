"""Actual full-map geometry LOD comparison, retaining all source tree positions."""
from pathlib import Path
import argparse,json,os,statistics,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json
from game.tools.capture_reference_map import VIEWS,wicked

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--runtime',type=Path,required=True);p.add_argument('--visual-profile',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--warmup',type=int,default=4);p.add_argument('--frames',type=int,default=4)
    p.add_argument('--views',nargs='+',choices=VIEWS,default=['reference_downlook','daylight_horizon','bridge_oblique','woodland_low'])
    p.add_argument('--only-lod',action='store_true');p.add_argument('--reflection-pair',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,map_path=a.map,visual_profile=a.visual_profile,output=a.output/'client',map_environment=False)
    rows=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True);before=serialize(g.sim.frame())
        g.show_hud=False;g.renderer.set_quality('high');g.renderer.set_presentation_paused(True);g.renderer.set_profiling(True)
        for name in a.views:
            eye,target=VIEWS[name];g.set_camera(wicked(eye),wicked(target),fov=1.)
            modes=[(1200,True),(1200,False)]if a.reflection_pair else [(v,None)for v in ([1200]if a.only_lod else [1e9,1200])]
            for distance,reflection in modes:
                if reflection is not None:g.renderer.set_planar_reflections(reflection)
                g.renderer.set_vegetation_lod_distance(distance);samples=[];label=name+('-lod'if distance==1200 else '-source')
                if reflection is not None:label+='-reflection'if reflection else '-sky-ssr'
                for i in range(a.warmup+a.frames):
                    start=time.perf_counter();g.draw(1/60);ms=(time.perf_counter()-start)*1000
                    if i>=a.warmup:samples.append(ms)
                    write_json(a.output/'progress.json',{'case':label,'frame':i+1,'wall_ms':ms})
                state=json.loads(g.renderer.vegetation_state());assert state['distance_hidden_trees']==0
                row={'case':label,'lod_distance_m':distance,'wall_ms':samples,'median_ms':statistics.median(samples),
                    'fps':1000/statistics.mean(samples),'vegetation':state,'statistics':serialize(g.renderer.statistics()),
                    'depth':json.loads(g.renderer.depth_coverage()),'timings':json.loads(g.renderer.frame_timings()),'capture':g.capture(label),
                    'actual_settings':json.loads(g.renderer.visual_settings())}
                assert row['timings']['descriptors']['allocation_failures']==0
                rows.append(row);write_json(a.output/'partial.json',{'cases':rows});print('TREE_LOD_CASE',label,row['fps'],state,flush=True)
        assert before==serialize(g.sim.frame());assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'captured_requires_visual_review','cases':rows,'map_sha256':g.scene_hash,
            'renderer_sha256':sha(Path(g.r.__file__)),'core_sha256':sha(Path(native.__file__)),'core_unchanged':True,'shader_errors':g.renderer.shader_errors(),
            'scope':'Same full-map placements and source near meshes; only geometry LOD threshold changes. Every tree remains instantiated. Pixel visibility still requires actual image review; other GPU workloads remain running.'})
    finally:g.close()

if __name__=='__main__':main()
