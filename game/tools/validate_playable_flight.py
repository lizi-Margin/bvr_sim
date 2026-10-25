"""Bounded real client flight with typed input, moving camera and wall FPS.

Uses the actual interactive-frame scheduler; no screen clicks or frozen core.
Reports performance honestly, while retaining unrelated external GPU workloads.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,math,os,statistics,sys,time
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json
from game.tools.capture_reference_map import check_grounding

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['map','runtime','visual-profile','output']:p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--frames',type=int,default=360);p.add_argument('--models',nargs='+',default=['F16','F22'])
    p.add_argument('--quality',choices=['medium','high'],default='high')
    p.add_argument('--input-mode',choices=['level','pointer'],default='level')
    p.add_argument('--ground-check',action='store_true');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,map_path=a.map,visual_profile=a.visual_profile,output=a.output/'client',map_environment=False)
    cases=[]
    try:
        g.renderer.set_quality(a.quality);g.quality=a.quality;g.show_hud=True;g.renderer.set_profiling(True)
        original_input=g.input
        def flight_input(event,dt):
            result=original_input(event,dt)
            if a.input_mode=='level' and g.mode=='flight':
                angle=.08*math.sin(g.sim.frame().sim_time/8)
                g.submit_player(mode='assisted',direction=[math.cos(angle),math.sin(angle),0],throttle=.9)
            return result
        g.input=flight_input
        for model in a.models:
            g.select_aircraft(model);g.config.mission='training';g.config.seed=7;g.start(record=True,initial_speed=300)
            # Starting/selecting an aircraft reapplies persistent preferences.
            # Set the measured preset afterwards and verify its actual flags.
            g.renderer.set_quality(a.quality);g.quality=a.quality
            actual=json.loads(g.renderer.visual_settings())['actual_output']
            if 'ssgi'in actual:assert actual['ssgi']==(a.quality=='high')
            initial=serialize(g.sim.frame());start_position=list(g.player().position)
            for _ in range(32):g.draw(1/60)
            g.interactive=True;accumulator=0.;dt=1/30;frames=[];captures=[]
            for i in range(a.frames):
                event=SimpleNamespace(pressed=[],held=[],x=g.width/2+(70*math.sin(i/55)if a.input_mode=='pointer'else 0),y=g.height/2+(8*math.sin(i/80)if a.input_mode=='pointer'else 0),quit=False,wheel=0)
                begin=time.perf_counter();alive,accumulator=g.run_client_frame(event,dt,accumulator);elapsed=time.perf_counter()-begin;dt=elapsed
                frame=g.sim.frame();player=g.player(frame)
                assert alive and player and player.alive and g.mode=='flight',('Flight ended',model,frame.result)
                assert all(math.isfinite(v)for v in [*player.position,*player.velocity,*player.orientation])
                frames.append({'wall_ms':elapsed*1000,'tick':frame.tick,'sim_time':frame.sim_time,'position':list(player.position),
                    'orientation':list(player.orientation),'speed_mps':math.dist(player.velocity,[0,0,0])})
                if i in [0,a.frames//2,a.frames-1]:captures.append(g.capture(model+'-live-'+str(i)))
                if (i+1)%60==0:
                    write_json(a.output/'progress.json',{'aircraft':model,'frame':i+1,'recent_fps':1000/statistics.mean(f['wall_ms']for f in frames[-60:]),'tick':frame.tick})
                    print('LIVE_FLIGHT',model,i+1,round(1000/statistics.mean(f['wall_ms']for f in frames[-60:]),2),flush=True)
            ms=np.asarray([f['wall_ms']for f in frames]);final=serialize(g.sim.frame());state=json.loads(g.renderer.vegetation_state())
            assert final['tick']>initial['tick']and math.dist(start_position,frames[-1]['position'])>100
            assert state['distance_hidden_trees']==0
            timing=json.loads(g.renderer.frame_timings());assert timing['descriptors']['allocation_failures']==0
            case={'aircraft':model,'frames':frames,'average_fps':1000/float(ms.mean()),'median_fps':1000/float(np.median(ms)),
                'one_percent_low_fps':1000/float(np.percentile(ms,99)),'p95_frame_ms':float(np.percentile(ms,95)),
                'maximum_frame_ms':float(ms.max()),'captures':captures,'initial_tick':initial['tick'],'final_tick':final['tick'],
                'sim_time_advanced':final['sim_time']-initial['sim_time'],'distance_flown_m':math.dist(start_position,frames[-1]['position']),
                'vegetation':state,'timings':timing,'actual_settings':json.loads(g.renderer.visual_settings())}
            cases.append(case);write_json(a.output/'partial.json',{'cases':cases});print('LIVE_FLIGHT_COMPLETE',model,case['average_fps'],case['one_percent_low_fps'],flush=True)
        g.sim.set_paused(True)
        grounding=check_grounding(g,40000,a.output)if a.ground_check else None
        assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'status':'measured','target_30fps_met':all(c['average_fps']>=30 for c in cases),
            'cases':cases,'grounding':grounding,'map_sha256':g.scene_hash,'renderer_sha256':sha(Path(g.r.__file__)),
            'core_sha256':sha(Path(native.__file__)),'shader_errors':g.renderer.shader_errors(),
            'quality':a.quality,'input_mode':a.input_mode,
            'scope':'1920x1080/native scale1; actual client input and fixed core ticks with moving aircraft/camera. Captures outside frame samples. Other GPU tasks retained. A short run does not prove long-session stability.'})
    finally:g.close()

if __name__=='__main__':main()
