"""Reproducible native player-intent response experiments, without renderer truth inputs."""
from pathlib import Path
import argparse,hashlib,json,math,os,sys,time,shutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.player_input import body_forward,unit
from bvr_game.content import sha,write_json

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def direction(az,el=0):
    az,el=math.radians(az),math.radians(el)
    return [math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)]
def angle(a,b):return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(unit(a),unit(b)))))))
def intent_values(case,t,recovery_at=20):
    az=el=0
    if t>=4:
        if case.startswith('turn_'):az=float(case.split('_')[1])
        elif case=='fine':az=2;el=1
        elif case=='up':el=10
        elif case=='down':el=-10
        elif case=='down_pulse':el=-10 if t<recovery_at else 0
        elif case=='vertical':el=85
        elif case=='circle':az=(t-4)*3
        elif case=='reversal':az=60 if t<65 else -60
        elif case=='climb_turn':az=60;el=12
        elif case=='dive_recovery':el=-25 if t<recovery_at else 5
        elif case=='sustained':az=25*math.sin((t-4)/20);el=4*math.sin((t-4)/15)
    return {'direction':direction(az,el),'throttle':.95,'mode':'assisted'}

def run(a):
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(map_path=a.map,output=a.output/'client');g.player_profiles_frozen=True
    if a.profile_file:
        from bvr_game.player_profiles import PlayerProfileStore
        g.profile_store=PlayerProfileStore(a.profile_file)
    snapshot=a.output/'candidate-snapshot';snapshot.mkdir()
    shutil.copy2(native.__file__,snapshot/Path(native.__file__).name)
    for relative in ['game/config/player_flight_profiles.json','game/tools/player_flight_response.py',
        'bvr_sim/src_cxx/simulator/aircraft/player_flight.hxx','bvr_sim/src_cxx/simulator/aircraft/player_flight_types.hxx',
        'bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.cxx','bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.hxx',
        'bvr_sim/src_cxx/simulator/aircraft/fdm/ac_fdm.hxx','bvr_sim/src_cxx/simulator/aircraft/fighter.cxx',
        'bvr_sim/src_cxx/simulator/aircraft/fighter.hxx','bvr_sim/src_cxx/simulator/aircraft/base.cxx',
        'bvr_sim/src_cxx/simulator/aircraft/base.hxx']:
        dest=snapshot/relative;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(g.profile_store.path if relative=='game/config/player_flight_profiles.json' else ROOT/relative,dest)
    summaries=[];started=time.perf_counter()
    plan=[]
    for model in a.models:
        for speed in a.speeds or ([180] if model=='FG-A-10' else [300]):
            for case in a.cases:
                seconds=300 if case=='sustained' else 150 if case=='turn_180' else 120 if case in ['circle','reversal'] else 30 if case=='down' else 90
                if a.seconds is not None:seconds=a.seconds
                plan.append({'model':model,'speed_mps':speed,'case':case,'seconds':seconds,'seed':a.seed if a.seed is not None else 2201+len(plan)%9,'altitude_m':a.altitude,
                    'recovery_at_s':a.recovery_at if case in ['down_pulse','dive_recovery'] else None})
    write_json(a.output/'plan.json',{'phase':'candidate diagnostics; not final held-out evaluation','cases':plan,'profile_sha256':g.profile_store.file_sha256,
        'core_sha256':sha(Path(native.__file__)),'map_sha256':g.scene_hash,'sample_ticks':5,'intent_ticks':25,'units':'NWU metres; orientation radians; body rates rad/s; alpha/beta radians; normal_g dimensionless; density kg/m^3'})
    try:
        for spec in plan:
            assert sha(g.profile_store.path)==g.profile_store.file_sha256,'Profile changed during frozen experiment'
            g.select_aircraft(spec['model']);g.config.mission='training';g.config.seed=spec['seed']
            g.start(start_position=[-20000,0,spec['altitude_m']],initial_speed=spec['speed_mps'])
            initial=serialize(g.sim.frame());samples=[];actions=[];last_tick=0
            for j in range(int(spec['seconds']/.5)):
                values=intent_values(spec['case'],j*.5,a.recovery_at)
                g.submit_player(**values)
                for _ in range(5):
                    g.step(5)
                    f=g.sim.frame();p=g.player(f);s=serialize(g.sim.player_flight_state());v=list(p.velocity)
                    samples.append({'time':f.sim_time,'tick':f.tick,'target':values['direction'],'direction_error_deg':angle(values['direction'],v),
                        'limited_direction_error_deg':angle(s['limited_direction'],v),
                        'body_error_deg':angle(values['direction'],body_forward(p.orientation)),'state':s,'alive':p.alive,
                        'actuators':dict(p.animation_properties)})
                    if not p.alive or f.result!='running':break
                actions.append({'tick':last_tick,'ticks':f.tick-last_tick,'player_intent':values,'frame_sha256':digest(serialize(f))});last_tick=f.tick
                if not p.alive or f.result!='running':break
            tail=samples[-min(200,len(samples)):]
            error=[x['direction_error_deg'] for x in tail]
            steady=spec['case'] in ['fine','up','down','turn_45','turn_90','turn_180']
            settled=next((x['time']-4 for i,x in enumerate(samples) if x['time']>=4 and len(samples[i:])>=20 and all(y['direction_error_deg']<2 for y in samples[i:])),None) if steady else None
            summary={**spec,'actual_duration_s':f.sim_time,'alive':p.alive,'result':f.result,'final_error_deg':error[-1],
                'tail_max_error_deg':max(error),'settle_to_2deg_seconds':settled,'final_speed_mps':math.sqrt(sum(x*x for x in v)),
                'minimum_speed_mps':min(x['state']['measured']['speed'] for x in samples),'minimum_height_m':min(x['state']['measured']['position'][2] for x in samples),
                'maximum_abs_roll_rad':max(abs(x['state']['measured']['orientation'][0]) for x in samples),
                'maximum_sampled_abs_body_roll_rate':max(abs(x['state']['measured']['body_rates'][0]) for x in samples if x['state']['measured']['body_rates'] is not None),
                'maximum_sampled_abs_body_pitch_rate':max(abs(x['state']['measured']['body_rates'][1]) for x in samples if x['state']['measured']['body_rates'] is not None),
                'final_limited_direction_error_deg':samples[-1]['limited_direction_error_deg'],
                'maximum_height_m':max(x['state']['measured']['position'][2] for x in samples),
                'alpha_range_rad':[min(y),max(y)] if (y:=[x['state']['measured']['alpha'] for x in samples if x['state']['measured']['alpha'] is not None]) else None,
                'normal_g_range':[min(y),max(y)] if (y:=[x['state']['measured']['normal_g'] for x in samples if x['state']['measured']['normal_g'] is not None]) else None,
                'saturation_sample_fraction':sum(x['state']['saturated'] for x in samples)/len(samples),'profile_sha256':g.player_profile['effective_sha256']}
            name=f"{spec['model']}-{spec['speed_mps']}-{spec['case']}";folder=a.output/name
            write_json(folder/'samples.json',samples)
            write_json(folder/'intent-tape.json',{'schema':2,'kind':'player_intent','map':str(a.map.resolve()),'map_sha256':g.scene_hash,
                'config':serialize(g.config),'initial_position':[-20000,0,spec['altitude_m']],'initial_speed':spec['speed_mps'],
                'player_profile':g.player_profile,'profile_file_sha256':g.profile_store.file_sha256,'initial_frame':initial,'actions':actions,'final_frame':serialize(f)})
            summaries.append(summary);write_json(a.output/'summary.json',{'phase':'candidate','cases':summaries,'wall_seconds':time.perf_counter()-started})
            print(json.dumps(summary),flush=True)
    finally:g.close()
    return summaries

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--map',type=Path,default=ROOT/'game/maps/training_range_v3/generated-map.json')
    p.add_argument('--models',nargs='+',default=['F22','F16','FG-A-10']);p.add_argument('--speeds',nargs='+',type=float)
    p.add_argument('--altitude',type=float,default=8500,help='Configured initial altitude in NWU metres; recorded in the frozen plan')
    p.add_argument('--seed',type=int,help='Explicit same development seed for controlled candidate comparisons; omission retains the original rotating development seeds')
    p.add_argument('--recovery-at',type=float,default=20,help='Explicit down-pulse/dive recovery onset in simulation seconds; recorded with the plan. Original20s protocol stays the default.')
    p.add_argument('--profile-file',type=Path,help='Explicit candidate profile file; freeze, snapshot and record its actual hash')
    p.add_argument('--seconds',type=float,help='Explicit development duration override, recorded in every case; omission preserves the original protocol durations')
    p.add_argument('--cases',nargs='+',default=['turn_45','turn_90','turn_180','vertical']);a=p.parse_args()
    if a.seconds is not None and (not math.isfinite(a.seconds) or a.seconds<5):p.error('--seconds must be finite and at least five')
    run(a)
if __name__=='__main__':main()
