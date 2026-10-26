"""Serial, reproducible F-16 flights across the published map catalog.

python game/tools/benchmark_map_flights.py --output work/map-flights
Each map runs in its own renderer process. Timing excludes loading, warmup,
screenshots and video encoding. Normal HUD, physics and sortie logs remain on.
"""
from pathlib import Path
import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from bvr_game.map_library import MapLibrary,DEFAULT_CATALOG


def write(path,value):
    path=Path(path)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf8')


def digest(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def gpu():
    result=subprocess.run(['nvidia-smi','--query-gpu=name,driver_version,memory.total,memory.used,utilization.gpu,temperature.gpu,power.draw',
                           '--format=csv'],capture_output=True,text=True,timeout=15)
    return result.stdout.strip() or result.stderr.strip()


def metrics(samples):
    ordered=sorted(samples)
    percentile=lambda q:ordered[min(len(ordered)-1,math.ceil(q*len(ordered))-1)]
    return {'frames':len(samples),'fps':1000/statistics.mean(samples),
            'p50_ms':statistics.median(samples),'p95_ms':percentile(.95),
            'p99_ms':percentile(.99),'max_ms':max(samples),
            'one_percent_low_fps':1000/statistics.mean(ordered[-max(1,math.ceil(len(ordered)*.01)):]),
            'over_16_67_ms':sum(t>1000/60 for t in samples),
            'over_33_33_ms':sum(t>1000/30 for t in samples)}


def worker(args):
    from bvr_game.app import FlightGame,serialize,native
    row=MapLibrary(args.catalog).versions()[args.index]
    folder=args.output
    folder.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(folder/'sorties')
    print('MAP_LOADING',row['label'],flush=True)
    manifest=Path(row['manifest'])
    if digest(manifest)!=row['manifest_sha256']:raise ValueError('Release manifest changed')
    release=json.loads(manifest.read_text(encoding='utf8'))
    before=gpu()
    started=time.perf_counter()
    game=FlightGame(render=True,visible=not args.hidden,runtime=args.runtime,
                    map_path=row['map'],output=folder/'client',visual_profile=args.visual_profile)
    try:
        if game.scene_hash!=release['map_sha256']:raise ValueError('Published map hash changed')
        game.entry_point='map_flight_benchmark'
        game.select_aircraft('F16','intercept')
        game.config.mission='training'
        game.config.enemy_attacks=False
        game.config.seed=101
        game.quality='high'
        game.renderer.set_quality('high')
        game.renderer.set_render_scale(1.)
        rows=[]
        for name,altitude in [('low',850.),('cruise',2400.)]:
            game.start(start_position=[-6500,-3000,altitude],initial_speed=250.)
            game.command(heading=.25,pitch=.03,throttle=.85)
            warm_start=time.perf_counter()
            warm_frames=0
            while (warm_frames<args.warmup or time.perf_counter()-warm_start<5) and time.perf_counter()-warm_start<60:
                game.renderer.poll()
                game.draw(1/60)
                warm_frames+=1
            warm_seconds=time.perf_counter()-warm_start
            capture_start=game.capture(name+'-start')
            records=[]
            phase_start=last=time.perf_counter()
            accumulator=0.
            next_decision=0
            while time.perf_counter()-phase_start<args.seconds:
                    index=len(records)
                    begin=time.perf_counter()
                    dt=min(begin-last,.1)
                    last=begin
                    event=game.renderer.poll()
                    if event.quit:raise RuntimeError('Benchmark window was closed')
                    own=game.player()
                    # Own altitude feedback; the simulator still owns all flight dynamics.
                    if game.sim.frame().tick>=next_decision:
                        pitch=max(-.14,min(.18,.03+(altitude-own.position[2])*.001-own.velocity[2]*.002))
                        game.command(heading=.25,pitch=pitch,throttle=.85)
                        next_decision=game.sim.frame().tick+10
                    accumulator+=dt
                    ticks=min(int(accumulator/game.config.dt),5)
                    if ticks:
                        game.step(ticks)
                        accumulator-=ticks*game.config.dt
                    game.draw(dt)
                    frame=game.sim.frame()
                    own=game.player(frame)
                    agl=own.position[2]-game._terrain.height(*own.position[:2])
                    records.append([index,frame.tick,0.,frame.sim_time,*own.position,agl,math.hypot(*own.velocity)])
                    elapsed=(time.perf_counter()-begin)*1000
                    records[-1][2]=elapsed
                    if frame.result!='running':raise RuntimeError('Flight ended early: '+frame.result)
                    if index==0 or (index+1)%100==0:
                        print('FLIGHT',name,index+1,round(time.perf_counter()-phase_start,1),'seconds',round(elapsed,2),'ms',flush=True)
            phase_seconds=time.perf_counter()-phase_start
            with (folder/(name+'-frames.csv')).open('w',newline='',encoding='utf8') as stream:
                output=csv.writer(stream)
                output.writerow(['frame','tick','wall_ms','sim_seconds','north','west','altitude','agl','speed'])
                output.writerows(records)
            snapshot=serialize(game.sim.frame())
            rows.append({'phase':name,'target_altitude_m':altitude,**metrics([r[2] for r in records]),
                         'realtime_fps':len(records)/phase_seconds,'wall_seconds':phase_seconds,
                         'warmup_frames':warm_frames,'warmup_seconds':warm_seconds,
                         'min_agl_m':min(r[7] for r in records),'distance_m':math.dist(records[0][4:6],records[-1][4:6]),
                         'final_frame':snapshot,'capture_start':capture_start,'capture_end':game.capture(name+'-end'),
                         'statistics':serialize(game.renderer.statistics()),'logs':game.log_paths(),
                         'timings':json.loads(game.renderer.frame_timings())})
            print('FLIGHT_COMPLETE',name,round(rows[-1]['fps'],2),'fps',flush=True)
            write(folder/'partial.json',rows)
        result={'label':row['label'],'id':row['id'],'map':row['map'],'map_sha256':game.scene_hash,
                'core_sha256':digest(native.__file__),'renderer_sha256':digest(game.r.__file__),
                'resolution':[1920,1080],'render_scale':1.,'quality':'high','seed':101,'aircraft':'F16',
                'warmup_min_frames_per_phase':args.warmup,'map_environment':game.visual_profile,
                'counts':game.baked_scene.document.get('counts',{}),'phases':rows,
                'shader_errors':game.renderer.shader_errors(),'gpu_before':before,'gpu_after':gpu(),
                'load_and_run_wall_s':time.perf_counter()-started,
                'scope':'Moving chase-camera training flights with physics/HUD/logging; uncapped, no video readback. Saved map weather retained. Realtime accumulator matches normal client: fixed 0.02s core dt, per-frame elapsed clamped to 0.1s, maximum 5 ticks. Every phase measures a fixed wall-time window; slow frames can slow simulation as in normal client. Short sample, not isolated GPU certification.'}
        game.finish_sortie('benchmark_finished')
        write(folder/'report.json',result)
    finally:
        game.close()


def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf8')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--catalog',type=Path,default=DEFAULT_CATALOG)
    parser.add_argument('--runtime',type=Path,default=ROOT/'game/runtime-ui.json')
    parser.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    parser.add_argument('--seconds',type=float,default=20.)
    parser.add_argument('--warmup',type=int,default=16)
    parser.add_argument('--hidden',action='store_true')
    parser.add_argument('--index',type=int)
    parser.add_argument('--indices',nargs='+',type=int)
    args=parser.parse_args()
    args.output=args.output.resolve()
    if not math.isfinite(args.seconds) or args.seconds<=0 or args.warmup<1:parser.error('Duration and warmup must be positive')
    if args.index is not None:return worker(args)
    args.output.mkdir(parents=True,exist_ok=False)
    rows=MapLibrary(args.catalog).versions()
    write(args.output/'catalog-snapshot.json',rows)
    write(args.output/'conditions.json',{'gpu_before':gpu(),'wall_seconds_per_phase':args.seconds,
          'warmup_per_phase':args.warmup,'order':args.indices or list(range(len(rows))),
          'script_sha256':digest(__file__),'runtime':json.loads(args.runtime.read_text()),
          'scope':'Serial independent processes; other user processes are left running.'})
    reports=[]
    for index in args.indices or range(len(rows)):
        name=rows[index]['id'].split('@')[0]
        directory=args.output/name
        with (args.output/(name+'.log')).open('w',encoding='utf8') as log:
            command=[sys.executable,'-X','utf8',str(Path(__file__).resolve()),'--index',str(index),'--output',str(directory),
                     '--catalog',str(args.catalog),'--runtime',str(args.runtime),'--visual-profile',str(args.visual_profile),
                     '--seconds',str(args.seconds),'--warmup',str(args.warmup)]
            if args.hidden:command.append('--hidden')
            child=subprocess.Popen(command,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
            print('BENCHMARK_MAP',index,rows[index]['label'],'pid',child.pid,flush=True)
            try:code=child.wait(timeout=900)
            except subprocess.TimeoutExpired:
                child.terminate()
                try:child.wait(timeout=15)
                except subprocess.TimeoutExpired:child.kill();child.wait()
                code='timeout'
        result={'label':rows[index]['label'],'id':rows[index]['id'],'exit_code':code}
        if (directory/'report.json').exists():result['report']=str(directory/'report.json')
        reports.append(result)
        write(args.output/'runs.json',reports)
        print('BENCHMARK_MAP_DONE',json.dumps(result,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
