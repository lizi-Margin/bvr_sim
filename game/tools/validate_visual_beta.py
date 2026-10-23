"""Measured baseline/visual/performance evidence for the visual Agent beta."""
from pathlib import Path
import argparse,hashlib,json,math,statistics,subprocess,sys,time
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.content import sha,write_json
MAP=ROOT/'game/maps/training_range_v3/generated-map.json'

def cameras(g):
    n,w,h=g.player().position
    return {
      '01_high_horizon':{'eye':[-w+32,h+11,n-32],'target':[-w,h+1,n],'fov':.92},
      '02_aircraft_backlight':{'eye':[-w-24,h+5,n+25],'target':[-w,h+1,n],'fov':.92},
      '03_cockpit':{'eye':[-w+8,h+4,n+10],'target':[-w,h+1.5,n+1],'fov':.8},
      '04_mid_terrain':{'eye':[-5000,1600,3000],'target':[-4500,180,4500],'fov':1.05},
      '05_low_sample':{'eye':[-4850,320,3700],'target':[-4500,185,4500],'fov':1.05},
      '06_road_building':{'eye':[-4475,186,4290],'target':[-4500,185,4340],'fov':1.05},
      '07_vegetation':{'eye':[-3780,370,3640],'target':[-3930,280,3780],'fov':1.05},
      '08_radar_sa':None}

def snapshots(out,stage):
    g=FlightGame(render=True,visible=False,map_path=MAP,output=out/stage/'visuals')
    try:
        g.quality='high';g.renderer.set_quality('high');g.config.enemy_attacks=True;g.start()
        views=cameras(g)
        frozen=out/'reports/fixed-cameras.json'
        if frozen.exists():views=json.loads(frozen.read_text())
        else:write_json(frozen,views)
        rows=[]
        for name,camera in views.items():
            g.camera_manual=False
            if camera:g.set_camera(**camera)
            g.show_hud=name=='08_radar_sa'
            for _ in range(20):g.draw()
            rows.append({'id':name,'image':g.capture(name),'camera':g.camera_params,'tick':g.sim.frame().tick})
        g.show_hud=True;g.camera_manual=False
        # Independent real, armed quick engagement for dynamic visual evidence.
        g.config.enemy_range=3500;g.config.enemy_evasion=False;g.start();g.step(10)
        g.command(lock=True,fire=True,target_uid='bandit');g.step();g.draw()
        rows.append({'id':'09_missile_launch','image':g.capture('09_missile_launch')})
        import imageio_ffmpeg
        from PIL import Image
        video=out/'videos'/(stage+'-flight.mp4')
        encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','10','-i','-','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(video)],stdin=subprocess.PIPE)
        frames=[];tape=[]
        try:
            for i in range(80):
                command={'heading':0.,'pitch':.02,'throttle':.85};g.command(**command);g.step(5);g.draw(.1)
                file=out/stage/'visuals/video-frame.png';g.renderer.capture(str(file))
                encoder.stdin.write(Image.open(file).convert('RGB').tobytes())
                frames.append(serialize(g.sim.frame()));tape.append({'command':command,'ticks':5})
        finally:encoder.stdin.close();assert encoder.wait()==0
        while g.sim.frame().result=='running' and g.sim.frame().tick<4000:
            g.command(heading=0.,pitch=0.,throttle=.85);g.step(5);g.draw()
        rows.append({'id':'10_combat_result','image':g.capture('10_combat_result')})
        write_json(out/'input-tapes'/(stage+'-quick-armed.json'),{'config':serialize(g.config),'frames':frames,'actions':tape,'final_frame':serialize(g.sim.frame()),'scope':'8-second film samples plus real engagement outcome; initial lock/fire at tick10'})
        write_json(video.with_suffix('.json'),{'video':str(video),'seed':g.config.seed,'mission':g.config.mission,'aircraft':g.config.player_model,'tick_range':[frames[0]['tick'],frames[-1]['tick']],'resolution':[1920,1080],'quality':'high','fps':10,'camera':'measured velocity chase; same configuration before/after','map_sha256':g.scene_hash,'shader_errors':g.renderer.shader_errors(),'frames':len(frames)})
        write_json(out/'reports'/(stage+'-visuals.json'),{'captures':rows,'shader_errors':g.renderer.shader_errors(),'video':str(video),'combat_result':serialize(g.sim.frame())})
    finally:g.close()

def inputs(out,stage):
    g=FlightGame(output=out/stage/'input-probes');rows=[]
    try:
        for model in ['F22','F16','FG-A-10']:
            g.select_aircraft(model);g.config.mission='training';g.config.enemy_attacks=False
            for label,keys,x,y in [('W',[87],960,540),('S',[83],960,540),('WS',[87,83],960,540),('WA',[87,65],960,540),('SD',[83,68],960,540),('mouse_up',[],960,230),('mouse_down',[],960,780),('mouse_right',[],1200,540)]:
                g.start();initial=serialize(g.sim.frame());samples=[]
                for tick in range(50):
                    g.input(SimpleNamespace(held=keys,pressed=[],x=x,y=y,wheel=0,quit=False),.02);g.step()
                    if tick%10==9:samples.append(serialize(g.sim.frame()))
                g.input(SimpleNamespace(held=[],pressed=[],x=960,y=540,wheel=0,quit=False),.02);g.step(5)
                rows.append({'model':model,'case':label,'keys':keys,'initial':initial,'samples':samples,'released':serialize(g.sim.frame())})
        write_json(out/'reports'/(stage+'-input-probes.json'),rows)
    finally:g.close()

def perf(out,stage,frames):
    g=FlightGame(render=True,visible=False,map_path=MAP,output=out/stage/'performance');rows={}
    try:
        g.quality='high';g.renderer.set_quality('high')
        for name in ['normal_bvr','sample_low_flight','combat_effects']:
            g.config.mission='air';g.config.enemy_attacks=True;g.config.enemy_range=3500 if name=='combat_effects' else 50000;g.start()
            if name=='sample_low_flight':g.set_camera(**cameras(g)['05_low_sample'])
            for _ in range(80):g.draw()
            g.step(10)
            if name=='combat_effects':g.command(lock=True,fire=True,target_uid='bandit');g.step()
            samples=[];stats=[]
            for i in range(frames):
                if g.sim.frame().result!='running':break
                start=time.perf_counter();g.command(heading=g.player().orientation[2],pitch=0.,throttle=.85);g.step();g.draw();samples.append((time.perf_counter()-start)*1000)
                if i%300==0:stats.append({'scene':serialize(g.renderer.statistics()),'aircraft':serialize(g.renderer.aircraft_statistics()),'tick':g.sim.frame().tick})
            rows[name]={'fps':1000/statistics.mean(samples),'p95_ms':sorted(samples)[int(len(samples)*.95)],'frames':len(samples),'requested_frames':frames,'terminal_result':g.sim.frame().result,'samples_ms':samples,'shader_errors':g.renderer.shader_errors(),'statistics_samples':stats,'capture':g.capture(name)}
            print(name,rows[name]['fps'],rows[name]['p95_ms'],flush=True)
        write_json(out/('performance-1080p-high.json' if stage=='after' else 'before/performance.json'),{'profiles':rows,'resolution':[1920,1080],'quality':'high','includes':'typed command, core tick, enabled default logs, HUD, complete render/Present','excludes':'warmup, encoding, periodic statistics','map_sha256':g.scene_hash})
    finally:g.close()

def perf_final(out,frames):
    if frames<1800:raise ValueError('Final performance requires at least 1800 frames per scene')
    from bvr_game.playtest import LocalCombatPilot,ResidentPlaytest
    host=ResidentPlaytest(out/'after/performance',render=True);g=host.game;rows={}
    try:
        for name in ['normal_bvr','sample_low_flight','combat_effects']:
            model='F16' if name=='combat_effects' else 'F22';host.reset(102 if model=='F16' else 101,model);pilot=LocalCombatPilot(g.config.seed)
            if name=='sample_low_flight':g.set_camera(**cameras(g)['05_low_sample'])
            if name=='combat_effects':
                # Real armed patrol, keep the fixed successful F16 input policy.
                # Begin the view after both sides actually launch; no injected FX.
                while g.sim.frame().sim_time<90 and g.sim.frame().result=='running':
                    host.step(25,pilot.command(host.observe()))
            for _ in range(180):g.draw()
            samples=[];phases=[];stats=[];last_command={};start_tick=g.sim.frame().tick
            for i in range(frames):
                if g.sim.frame().result!='running':raise RuntimeError(name+' ended before the required sample count')
                begin=time.perf_counter()
                if g.sim.frame().tick%25==0:last_command=pilot.command(host.observe());g.command(**last_command)
                after_command=time.perf_counter();g.step();after_tick=time.perf_counter()
                if name=='combat_effects':
                    missiles=[e for e in g.sim.frame().entities if e.kind=='missile' and e.alive]
                    if missiles:
                        e=missiles[0];n,w,h=e.position;g.set_camera(eye=[-w+18,h+10,n-65],target=[-w,h,n],fov=1.05)
                    else:g.camera_manual=False
                g.draw();end=time.perf_counter()
                samples.append((end-begin)*1000);phases.append([(after_command-begin)*1000,(after_tick-after_command)*1000,(end-after_tick)*1000])
                if i%300==0:stats.append({'scene':serialize(g.renderer.statistics()),'aircraft':g.renderer.aircraft_statistics(),'vram':g.renderer.memory_usage(),'tick':g.sim.frame().tick})
                if name=='combat_effects' and i==205:g.capture('combat-actual-impact-window')
            rows[name]={'fps':1000/statistics.mean(samples),'p95_ms':sorted(samples)[int(len(samples)*.95)],'frames':len(samples),'samples_ms':samples,'phase_ms':phases,'phase_columns':['policy_and_typed_command','tick_and_incremental_logs','camera_hud_full_render_present'],'tick_range':[start_tick,g.sim.frame().tick],'shader_errors':g.renderer.shader_errors(),'statistics_samples':stats,'capture':g.capture(name),'logs':g.log_paths(),'camera':'measured weapon chase' if name=='combat_effects' else 'fixed low camera' if name=='sample_low_flight' else 'player chase'}
            print(name,rows[name]['fps'],rows[name]['p95_ms'],flush=True)
        report={'profiles':rows,'resolution':[1920,1080],'quality':'high','warmup_frames_per_scene':180,'includes':'fixed core dt .02, 0.5s local policy, typed commands, real core ACMI/log and incremental input journal, HUD, full render/Present','excludes':'warmup, image capture/encoding, periodic scene/VRAM queries','draw_metric':'visible_mesh_subset_groups is the counted visible mesh/material subset groups, an explicit submission-equivalent estimate; it is not a hardware API draw-call counter','visual_settings':json.loads(g.renderer.visual_settings()),'map_sha256':g.scene_hash,'targets':{'mean_fps':120,'p95_ms':8.33,'shader_errors':0}}
        report['external_gpu_load']=bool(__import__('os').environ.get('BVR_PERF_EXTERNAL_GPU_LOAD'))
        report['isolation_status']='external GPU workload present; diagnostic only' if report['external_gpu_load'] else 'No other agent-started workload; see preflight process/GPU record'
        report['hardware']='NVIDIA GeForce RTX2080Ti 22528MiB, Ryzen5950X; Windows WDDM'
        report['core_sha256']=sha(Path(native.__file__));report['renderer_sha256']=sha(Path(g.r.__file__))
        dest=out/'performance-1080p-high.json'
        if dest.exists():__import__('shutil').copy2(dest,out/'reports'/('performance-preserved-'+str(time.time_ns())+'.json'))
        write_json(dest,report)
    finally:host.close()

def control_gpu(out):
    g=FlightGame(render=True,visible=False,map_path=MAP,output=out/'after/input-controls');rows=[]
    try:
        g.quality='high';g.renderer.set_quality('high');g.config.mission='training'
        for model in ['F22','F16','FG-A-10']:
            g.select_aircraft(model)
            for key,up in [(87,False),(83,True)]:
                g.start();initial=serialize(g.player())
                for _ in range(50):
                    g.input(SimpleNamespace(held=[key],pressed=[],x=960,y=540,wheel=0,quit=False),.02);g.step();g.draw()
                p=g.player();forward=list(g.renderer.entity_forward('player'))
                assert (forward[1]>0)==up,(model,key,forward)
                assert (p.orientation[1]<initial['orientation'][1])==up
                assert (p.velocity[2]>0)==up
                image=g.capture(model+'_'+chr(key))
                rows.append({'id':model,'key':chr(key),'expected':'pull_up' if up else 'push_down','initial':initial,'final':serialize(p),'rendered_forward':forward,'capture':image,'shader_errors':g.renderer.shader_errors(),'logs':g.log_paths()})
        write_json(out/'input-controls-report.json',{'status':'passed','gpu_cases':rows,'keyboard_contract':'W=-1/push/down; S=+1/pull/up; positive typed pitch_input unchanged','mouse_and_horizontal_contract':'F22/F16 curves unchanged; imported YASim roll-rate fix coordinated with its active user thread','input_matrix':str(out/'reports/after-input-probes.json')})
    finally:g.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['snapshots','inputs','perf','control-gpu']);p.add_argument('--stage',choices=['before','after'],default='before');p.add_argument('--output',type=Path,required=True);p.add_argument('--frames',type=int,default=600);a=p.parse_args()
    {'snapshots':lambda:snapshots(a.output,a.stage),'inputs':lambda:inputs(a.output,a.stage),'perf':lambda:perf_final(a.output,a.frames) if a.stage=='after' else perf(a.output,a.stage,a.frames),'control-gpu':lambda:control_gpu(a.output)}[a.action]()
