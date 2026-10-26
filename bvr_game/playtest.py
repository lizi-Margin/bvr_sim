"""Resident typed Agent host and reproducible batch evaluator. No LLM key required.

python -m bvr_game.playtest serve [--render]
python -m bvr_game.playtest batch --output PATH --candidate baseline-v1
python -m bvr_game.playtest replay TAPE --output PATH [--render]

The player policy receives copied LocalObservation values ONLY. Full GameFrame,
ACMI and world trajectories are diagnostics written by the evaluator, never policy
inputs. JSONL is an optional command boundary around the in-process typed host.
"""
from __future__ import annotations
from dataclasses import dataclass,asdict,field
from pathlib import Path
import argparse,hashlib,json,math,os,subprocess,sys,time
from .app import FlightGame,serialize,native,ROOT
from .content import sha,write_json

SPEC=ROOT/'game/recipes/intercept_patrol.json'
POLICY_SHA=sha(Path(__file__))
def digest(frame):return hashlib.sha256(json.dumps(frame,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def angle(x):return math.remainder(x,2*math.pi)

@dataclass(frozen=True)
class LocalObservation:
    tick:int;time:float
    own:dict
    contacts:tuple
    warnings:tuple
    selected_target:str
    missiles:int
    radar_warning:bool
    missile_warning:bool
    rwr_mode:str
    mission:dict
    weapon_counts:dict=field(default_factory=dict)

class LocalCombatPilot:
    """Baseline strategy using own state, radar observations and warning bearings."""
    def __init__(self,seed=7,shot_interval=40.):
        if not math.isfinite(shot_interval) or shot_interval<=0:raise ValueError('Shot interval must be finite and positive')
        self.shot_interval=shot_interval
        self.side=1 if seed&1 else -1;self.last_fire=-100.;self.last_seen=-100.;self.track=None;self.last_missiles=None;self.phase='search'
    def command(self,o:LocalObservation):
        own=o.own;p=own['position'];v=own['velocity'];yaw=own['orientation'][2]
        if self.last_missiles is not None and o.missiles<self.last_missiles:self.last_fire=o.time
        self.last_missiles=o.missiles
        if o.contacts:
            self.track=min(o.contacts,key=lambda c:math.dist(p,c['position']));self.last_seen=o.time
        cruise_pitch=max(-.07,min(.16,.025+(8500-p[2])*.00008))
        c={'heading':0.,'pitch':cruise_pitch,'throttle':1.};self.phase='search'
        distance=1e20;bearing=yaw
        if self.track and o.time-self.last_seen<25:
            age=o.time-self.last_seen;target=[a+b*age for a,b in zip(self.track['position'],self.track['velocity'])]
            distance=math.dist(p,target);bearing=math.atan2(target[1]-p[1],target[0]-p[0])
            track=math.atan2(v[1],v[0]);slip=angle(yaw-track)
            c['heading']=bearing+slip;self.phase='approach' if o.contacts else 'reacquire'
            if o.contacts and o.selected_target!=self.track['uid']:c.update(lock=True,target_uid=self.track['uid'])
        if o.missile_warning:
            warning=next((w for w in o.warnings if w['missile']),None)
            if warning:
                c['heading']=yaw+warning['bearing']+self.side*math.radians(110)
                c['pitch']=-.06 if own['agl']>1800 else .15
                self.phase='defend'
        elif o.time-self.last_fire<self.shot_interval:
            c['heading']=bearing+self.side*math.radians(20);self.phase='support'
        elif o.radar_warning and distance<45000:
            c['heading']=bearing+self.side*math.radians(20);self.phase='crank'
        closing=0.
        if self.track and distance<1e19:
            radial=[(a-b)/max(distance,1) for a,b in zip(self.track['position'],p)]
            closing=sum((a-b)*r for a,b,r in zip(v,self.track['velocity'],radial))
        # Baseline evidence: waiting until 28 km ceded the first shot in all 20
        # armed duels. Use only measured head-on geometry for an earlier shot.
        ammunition=o.weapon_counts.get('AIM-120C7',0) if o.weapon_counts else o.missiles
        if o.contacts and distance<45000 and closing>150 and ammunition>0 and o.time-self.last_fire>self.shot_interval and not o.missile_warning and abs(angle(bearing-yaw))<math.radians(40):
            c.update(lock=True,fire=True,target_uid=self.track['uid']);self.phase='launch'
        return c

def observe_local(game):
    f=game.sim.frame();p=game.player(f)
    own={k:serialize(getattr(p,k)) for k in ['position','velocity','orientation','health','throttle','mach','alive']}
    own['agl']=p.position[2]-game.sim.terrain().height(p.position[0],p.position[1])
    # Do not pass native entities, source pointers, missile truth or the world frame.
    contacts=tuple({'uid':c.uid,'position':list(c.position),'velocity':list(c.velocity),'locked':c.locked} for c in f.contacts)
    warnings=tuple({'uid':w.uid,'bearing':w.bearing,'localized':w.localized,'range':w.range if w.localized else None,'missile':w.missile} for w in f.warnings)
    return LocalObservation(f.tick,f.sim_time,own,contacts,warnings,f.selected_target,f.missiles_left,f.radar_warning,f.missile_warning,f.rwr_mode,
                            {'id':f.mission,'result':f.result,'kills':f.air_kills,'wave':f.mission_wave,'total':f.mission_total,'next_wave_time':f.next_wave_time,'search_heading':0.},dict(f.weapon_counts))

class ResidentPlaytest:
    def __init__(self,output,render=False,map_path=None,visual_profile=None,*,visible=False):
        self.output=Path(output).resolve();self.output.mkdir(parents=True,exist_ok=True)
        self.spec=json.loads(SPEC.read_text());self.spec_sha=sha(SPEC)
        self.core_sha=sha(Path(native.__file__))
        presentation={'visual_profile':visual_profile} if visual_profile is not None else {}
        self.game=FlightGame(render=render,visible=visible,map_path=map_path or ROOT/self.spec['map'],output=self.output/'client',**presentation)
        self.game.quality='high'
        if self.game.renderer:self.game.renderer.set_quality('high')
        self.configured=False
    def reset(self,seed=101,model='F22'):
        if sha(SPEC)!=self.spec_sha:raise RuntimeError('Frozen evaluation scenario changed; start a new explicit experiment')
        if model not in self.spec['player_models']:raise ValueError('Frozen combat evaluation supports F22/F16; imported training remains in the hangar')
        g=self.game;g.select_aircraft(model,'intercept');g.config.mission='intercept_patrol';g.config.seed=seed;g.start()
        self.configured=True;return self.observe()
    def observe(self):return observe_local(self.game)
    def step(self,ticks=25,command=None,exact=False,player_intent=None,*,draw=True):
        if command and player_intent:raise ValueError('Choose AI command or player intent for one step')
        if command:self.game.command(**command)
        if player_intent:self.game.submit_player(**player_intent)
        self.game.step_exact(ticks) if exact else self.game.step(ticks)
        if draw and self.game.renderer:self.game.draw()
        return self.observe()
    def pause(self,paused=True):
        self.game.sim.set_paused(paused);self.game.journal.record('pause',paused,self.game.sim.frame().tick)
    def diagnostics(self):
        return {'frame':serialize(self.game.sim.frame()),'logs':self.game.log_paths(),'camera':self.game.camera_params}
    def close(self):self.game.close()

    def episode(self,seed,model,candidate,folder):
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=False)
        self.reset(seed,model);pilot=LocalCombatPilot(seed);records=[];samples=[];observations=[];started=time.perf_counter();seen=set();events=[]
        try:
            while self.game.sim.frame().result=='running':
                o=self.observe();command=pilot.command(o);f=self.step(25,command);frame=serialize(self.game.sim.frame())
                records.append({'tick':o.tick,'command':command,'ticks':frame['tick']-o.tick,'frame_sha256':digest(frame),'phase':pilot.phase})
                if len(records)%10==0 or f.missile_warning!=o.missile_warning or f.mission['result']!='running':
                    samples.append(frame);observations.append(asdict(f))
                for e in frame['events']:
                    key=(e['tick'],e['kind'],e['actor'],e['target'])
                    if key not in seen:seen.add(key);events.append(e)
                if len(records)%20==0:write_json(folder/'progress.json',{'tick':frame['tick'],'time':frame['sim_time'],'phase':pilot.phase,'logs':self.game.log_paths()})
            final=serialize(self.game.sim.frame());p=next(e for e in final['entities'] if e['uid']=='player')
            terrain_crash=any(e['kind']=='aircraft_destroyed' and e['target']=='player' and e['message']=='Terrain collision' for e in events)
            reason='success' if final['result']=='succeeded' else 'terrain_collision' if terrain_crash else 'shot_down_or_airframe_lost' if not p['alive'] else 'mission_timeout'
            report={'seed':seed,'model':model,'candidate':candidate,'policy_sha256':POLICY_SHA,'scenario_sha256':self.spec_sha,'core_sha256':self.core_sha,'result':final['result'],'success':final['result']=='succeeded','survived':p['alive'],'terrain_crash':terrain_crash,'failure_reason':reason,'sim_seconds':final['sim_time'],'missiles_used':6-final['missiles_left'],'air_kills':final['air_kills'],'elapsed_wall_s':time.perf_counter()-started,'logs':self.game.log_paths(),'events':events,'final_frame':final}
            write_json(folder/'input-tape.json',{'schema_version':1,'scenario_sha256':self.spec_sha,'config':serialize(self.game.config),'map':str(self.game.map_path),'map_sha256':self.game.scene_hash,'candidate':candidate,'policy_sha256':POLICY_SHA,'actions':records,'samples':samples,'local_observation_samples':observations,'final_frame':final})
            write_json(folder/'report.json',report);return report
        except BaseException as error:
            self.game.finish_sortie('exception',repr(error));write_json(folder/'exception.json',{'error':repr(error),'diagnostics':self.diagnostics(),'actions':records});raise

def batch_worker(output,seeds,candidate):
    host=ResidentPlaytest(Path(output)/candidate/('resident-'+str(os.getpid())))
    try:
        for seed in seeds:
            model='F22' if seed%2 else 'F16';row=host.episode(seed,model,candidate,Path(output)/candidate/str(seed))
            print(json.dumps({k:row[k] for k in ['seed','model','result','sim_seconds','failure_reason','air_kills']}),flush=True)
    finally:host.close()

def batch(output,seeds,candidate,workers,worker_timeout=600):
    output=Path(output);output.mkdir(parents=True,exist_ok=True);frozen=output/'evaluation-spec.json'
    if frozen.exists() and sha(frozen)!=sha(SPEC):raise RuntimeError('Evaluation spec changed after freeze')
    if not frozen.exists():frozen.write_bytes(SPEC.read_bytes())
    target=output/candidate;target.mkdir(parents=True,exist_ok=True)
    (target/'policy-source.py').write_bytes(Path(__file__).read_bytes())
    processes=[]
    for i in range(workers):
        chunk=seeds[i::workers]
        if not chunk:continue
        log=(target/f'worker-{i}.log').open('w',encoding='utf8')
        p=subprocess.Popen([sys.executable,'-X','utf8','-m','bvr_game.playtest','worker','--output',str(output),'--candidate',candidate,'--seeds',*map(str,chunk)],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
        processes.append((p,log))
    codes=[]
    for p,log in processes:
        try:codes.append(p.wait(timeout=worker_timeout))
        except subprocess.TimeoutExpired:
            p.terminate()
            try:p.wait(timeout=10)
            except subprocess.TimeoutExpired:p.kill();p.wait()
            codes.append('worker_wall_timeout')
            write_json(target/('timeout-'+str(p.pid)+'.json'),{'pid':p.pid,'limit_seconds':worker_timeout,'reason':'Owned worker exceeded wall timeout; partial journal and progress retained'})
        finally:log.close()
    rows=[]
    for seed in seeds:
        file=target/str(seed)/'report.json'
        if file.exists():rows.append(json.loads(file.read_text()))
        else:rows.append({'seed':seed,'success':False,'survived':False,'terrain_crash':False,'failure_reason':'worker_exception','sim_seconds':0,'missiles_used':0})
    n=len(rows);summary={'candidate':candidate,'scenario_sha256':sha(SPEC),'policy_sha256':POLICY_SHA,'seeds':seeds,'episodes':rows,'worker_exit_codes':codes,'metrics':{'count':n,'success_rate':sum(r['success'] for r in rows)/n,'survival_rate':sum(r['survived'] for r in rows)/n,'terrain_crash_rate':sum(r['terrain_crash'] for r in rows)/n,'mean_sim_seconds':sum(r['sim_seconds'] for r in rows)/n,'mean_missiles_used':sum(r['missiles_used'] for r in rows)/n}}
    write_json(target/'batch-report.json',summary);print(json.dumps(summary['metrics'],indent=2))

def replay(tape,output,render=False,video=False,window_start=None,window_end=None,video_sample_ticks=5,visual_profile=None):
    tape=Path(tape);data=json.loads(tape.read_text())
    if 'context' in data:return replay_journal(tape,output,render,video,visual_profile)
    host=ResidentPlaytest(output,render,data['map'],visual_profile);rows=[];encoder=None;video_frames=0;keyframes=[]
    if video and not render:raise ValueError('Video requires --render')
    end_time=data['final_frame']['sim_time'] if window_end is None else window_end
    start_time=max(0,end_time-20) if window_start is None else window_start
    video_path=Path(output)/'replay.mp4'
    try:
        from .ground import apply_config
        if sha(data['map'])!=data['map_sha256']:raise ValueError('Replay map version changed')
        apply_config(native,host.game.config,data['config'])
        host.game.start(start_position=data.get('initial_position'),initial_speed=data.get('initial_speed'))
        host.game.player_profiles_frozen=True
        if data.get('player_profile'):host.game.apply_recorded_player_profile(data['player_profile'])
        if video:
            import imageio_ffmpeg
            from PIL import Image
            encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','10','-i','-','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(video_path)],stdin=subprocess.PIPE)
        for index,a in enumerate(data['actions']):
            if a.get('selected_weapon') is not None:
                if a['selected_weapon'] not in ('AIM-120C7','Mk-82'):
                    raise ValueError('Unknown recorded HUD weapon selection')
                host.game.weapon=a['selected_weapon']
            now=host.game.sim.frame().sim_time
            if video and start_time-.5<=now<=end_time:
                if a.get('player_intent'):host.game.submit_player(**a['player_intent'])
                elif a.get('command'):host.game.command(**a['command'])
                remaining=a['ticks']
                while remaining:
                    count=min(remaining,video_sample_ticks);host.step(count,exact=a.get('exact',False));remaining-=count
                    if start_time<=host.game.sim.frame().sim_time<=end_time:
                        if hasattr(host.game.renderer,'capture_rgb'):
                            encoder.stdin.write(host.game.renderer.capture_rgb())
                        else:
                            image=Path(output)/'video-frame.png';host.game.renderer.capture(str(image))
                            with Image.open(image) as pixels:encoder.stdin.write(pixels.convert('RGB').tobytes())
                        if video_frames%100==0:keyframes.append({'image':host.game.capture('keyframe-'+str(video_frames)),'tick':host.game.sim.frame().tick})
                        video_frames+=1
            else:host.step(a['ticks'],a.get('command'),a.get('exact',False),a.get('player_intent'))
            same=digest(serialize(host.game.sim.frame()))==a['frame_sha256'];rows.append(same)
            if not same:break
        if encoder:encoder.stdin.close();assert encoder.wait()==0;encoder=None
        endpoint_ticks=sorted({a['ticks'] for a in data['actions']})
        first=data.get('initial_frame',{'tick':0,'sim_time':0.})
        tick_span=data['final_frame']['tick']-first['tick']
        seconds_per_tick=(data['final_frame']['sim_time']-first['sim_time'])/tick_span if tick_span else None
        interval=round(endpoint_ticks[0]*seconds_per_tick,12) if len(endpoint_ticks)==1 and seconds_per_tick is not None else None
        report={'status':'passed' if all(rows) and len(rows)==len(data['actions']) else 'failed','complete_frames_compared':len(rows),'sample_interval_s':interval,'endpoint_tick_counts':endpoint_ticks,'selected_weapon':host.game.weapon,'first_difference':next((i for i,v in enumerate(rows) if not v),None),'rendered':render,'core_sha256':host.core_sha,'tape':str(tape),'tape_sha256':sha(tape),'logs':host.game.log_paths(),'capture':host.game.capture('replay') if render else None,'shader_errors':host.game.renderer.shader_errors() if render else None}
        if video:
            movie={'file':str(video_path),'frames':video_frames,'fps':10,'sim_window_s':[start_time,end_time],'sim_sample_ticks':video_sample_ticks,'playback_speed':video_sample_ticks*.02*10,'seed':data['config']['seed'],'aircraft':data['config']['player_model'],'mission':data['config']['mission'],'resolution':[1920,1080],'quality':'high','map_sha256':host.game.scene_hash,'visual_profile':host.game.visual_profile,'keyframes':keyframes,'shader_errors':report['shader_errors']}
            movie['capture_method']='Direct sRGB backbuffer RGB readback' if hasattr(host.game.renderer,'capture_rgb') else 'Backbuffer PNG readback followed by RGB decoding'
            write_json(video_path.with_suffix('.json'),movie);report['video']=movie
        write_json(Path(output)/'replay-report.json',report);return report
    finally:
        if encoder:
            encoder.stdin.close();encoder.wait()
        host.close()

def replay_journal(tape,output,render=False,video=False,visual_profile=None):
    """Replay ordinary client journals without dropping input or pause records."""
    if video:raise ValueError('Journal replay supports --render; use response/route intent tapes for sampled video')
    data=json.loads(Path(tape).read_text());context=data['context']
    if 'map' not in context:raise ValueError('This standalone aircraft journal has no world map; replay through its aircraft-library entry')
    if sha(context['map'])!=context['map_sha256']:raise ValueError('Journal map version changed')
    presentation={'visual_profile':visual_profile} if visual_profile is not None else {}
    g=FlightGame(render=render,visible=False,map_path=context['map'],output=Path(output)/'client',**presentation)
    try:
        from .ground import apply_config
        apply_config(native,g.config,data['config'])
        c=data['config'];g.start(start_position=[c['player_north'],c['player_west'],c['altitude']],initial_speed=c['speed'])
        if context.get('player_flight_profile'):g.apply_recorded_player_profile(context['player_flight_profile'])
        g.player_profiles_frozen=True;steps=0
        for index,row in enumerate(data['actions']):
            if g.sim.frame().tick!=row['tick']:raise ValueError(f'Journal tick mismatch at action {index}')
            kind,value=row['kind'],row['value']
            if kind=='command':g.command(**value)
            elif kind=='player_intent':g.submit_player(**value)
            elif kind=='player_profile_reload':g.apply_recorded_player_profile(value)
            elif kind=='pause':g.sim.set_paused(value)
            elif kind=='step':
                g.step_exact(value['ticks']) if value.get('exact') else g.step(value['ticks']);steps+=1
                if render:g.draw()
            else:raise ValueError('Unsupported journal action: '+kind)
        frame=serialize(g.sim.frame());same=frame==data['final_frame']
        report={'status':'passed' if same else 'failed','journal':str(tape),'journal_sha256':sha(tape),
            'actions_replayed':len(data['actions']),'steps_replayed':steps,'full_final_frame_equal':same,
            'final_tick':frame['tick'],'core_sha256':sha(Path(native.__file__)),'rendered':render,
            'shader_errors':g.renderer.shader_errors() if render else None,'logs':g.log_paths()}
        write_json(Path(output)/'replay-report.json',report);return report
    finally:g.close()

def serve(output,render):
    host=ResidentPlaytest(output,render)
    try:
        for line in sys.stdin:
            try:
                r=json.loads(line);action=r['action']
                if action=='reset':value=asdict(host.reset(r.get('seed',101),r.get('model','F22')))
                elif action=='observe':value=asdict(host.observe())
                elif action=='step':value=asdict(host.step(r.get('ticks',25),r.get('command'),r.get('exact',False),r.get('player_intent')))
                elif action=='player_profile':value={'profile':host.game.player_profile,'units':host.game.profile_store.document['units'],'file_sha256':host.game.profile_store.file_sha256}
                elif action=='pause':host.pause(r.get('paused',True));value={'paused':host.game.sim.frame().paused}
                elif action=='diagnose':value=host.diagnostics()
                elif action=='logs':value=host.game.log_paths()
                elif action=='camera':host.game.set_camera(**r['camera']);value=host.game.camera_params
                elif action=='capture':host.game.draw();value={'image':host.game.capture(r.get('name','agent'))}
                elif action=='close':break
                else:raise ValueError('Unknown action '+action)
                print(json.dumps({'ok':True,'result':value},ensure_ascii=False),flush=True)
            except Exception as error:print(json.dumps({'ok':False,'error':repr(error)}),flush=True)
    finally:host.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['serve','batch','worker','replay']);p.add_argument('tape',nargs='?',type=Path)
    p.add_argument('--worker-timeout',type=float,default=600);p.add_argument('--video',action='store_true');p.add_argument('--window-start',type=float);p.add_argument('--window-end',type=float);p.add_argument('--video-sample-ticks',type=int,default=5)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--render',action='store_true');p.add_argument('--visual-profile',type=Path);p.add_argument('--candidate',default='baseline-v1');p.add_argument('--workers',type=int,default=4);p.add_argument('--seeds',type=int,nargs='+')
    a=p.parse_args();spec=json.loads(SPEC.read_text());seeds=a.seeds or spec['seed_batch']
    if a.action=='serve':serve(a.output,a.render)
    elif a.action=='worker':batch_worker(a.output,seeds,a.candidate)
    elif a.action=='batch':batch(a.output,seeds,a.candidate,a.workers,a.worker_timeout)
    else:print(json.dumps(replay(a.tape,a.output,a.render,a.video,a.window_start,a.window_end,a.video_sample_ticks,a.visual_profile),indent=2))
if __name__=='__main__':main()
