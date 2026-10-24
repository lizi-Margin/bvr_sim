"""Real client input, native flight and optional DX12/film evidence.

Events enter FlightGame.input. The camera follows only measured own state;
there is no pose/velocity setter and no enemy truth in the input policy.
"""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,math,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.content import write_json,sha
from bvr_game.player_profiles import PlayerProfileStore


def basis_error(g):
    r,p,y=g.player().orientation
    f=[math.cos(y)*math.cos(p),math.sin(y)*math.cos(p),-math.sin(p)]
    right=[math.sin(y),-math.cos(y),0];up=[math.cos(y)*math.sin(p),math.sin(y)*math.sin(p),math.cos(p)]
    vectors=[[right[i]*math.cos(r)-up[i]*math.sin(r) for i in range(3)],
             [up[i]*math.cos(r)+right[i]*math.sin(r) for i in range(3)],f]
    expected=[[-v[1],v[2],v[0]] for v in vectors]
    return max(abs(a-b) for row,actual in zip(expected,g.renderer.entity_basis('player')) for a,b in zip(row,actual))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--profile-file',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--model',default='F16')
    p.add_argument('--case',choices=['edge','manual'],default='edge');p.add_argument('--seconds',type=float,default=120)
    p.add_argument('--headless',action='store_true');p.add_argument('--video',action='store_true');a=p.parse_args()
    if not math.isfinite(a.seconds) or a.seconds<2: p.error('--seconds must be finite and at least two')
    if a.video and a.headless:p.error('--video requires DX12 rendering')
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=not a.headless,visible=False,map_path=a.map,
        visual_profile=ROOT/'game/recipes/player_daylight.json',output=a.output/'client')
    g.profile_store=PlayerProfileStore(a.profile_file);g.player_profiles_frozen=True
    rows=[];captures=[];phases=[];encoder=None;frames=0;failure=None;max_basis=0.;max_surface_delta=0.
    target_turn=aircraft_turn=0.;manual_checks=[]
    # Finite manual manoeuvres followed by enough time to observe actual
    # recovery. Raw held full-stick is a separate diagnostic mode.
    manual=[('neutral',2,[]),('roll_right',1,[68]),('release_roll_right',8,[]),
        ('roll_left',1,[65]),('release_roll_left',8,[]),('pull',1,[83]),('release_pull',8,[]),
        ('push',1,[87]),('release_push',8,[]),('both_pitch',1,[87,83]),('release_both',5,[]),
        ('free_pull',1,[67,83]),('release_free',8,[]),('aggressive_pull_roll',3,[68,83]),
        ('aggressive_push_roll',3,[65,87]),('release_aggressive',20,[])]
    try:
        g.select_aircraft(a.model);g.config.mission='training';g.config.seed=3301
        g.start(start_position=[-20000,0,5000],initial_speed=180 if a.model=='FG-A-10' else 250);g.throttle=.85
        if g.renderer:g.quality='high';g.renderer.set_quality('high')
        g.follow_camera(.02)
        if a.video:
            import imageio_ffmpeg
            encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo',
                '-pix_fmt','rgb24','-s','1920x1080','-r','10','-i','-','-c:v','libx264','-preset','fast','-crf','20',
                '-pix_fmt','yuv420p',str(a.output/'handler.mp4')],stdin=subprocess.PIPE)
        target_turn=aircraft_turn=0.;old_target=old_yaw=None;old_controls=None
        duration=a.seconds if a.case=='edge' else sum(x[1] for x in manual)
        current=None;phase_start=0;phase_index=0
        for tick in range(round(duration/.02)):
            t=tick*.02
            if a.case=='edge':
                label='neutral' if t<2 else 'edge_right';keys=[]
                x=960 if t<2 else 960+959*min(1,(t-2)/.5);y=540
            else:
                while t>=phase_start+manual[phase_index][1]-.000001:
                    phase_start+=manual[phase_index][1];phase_index+=1
                label,_,keys=manual[phase_index];x,y=(1300,400) if 67 in keys or label=='release_free' else (960,540)
            if label!=current:
                if current and g.renderer:captures.append({'phase':current,'capture':g.capture(current)})
                phases.append({'phase':label,'tick':g.sim.frame().tick,'own':serialize(g.player()),'intent':list(g.player_input.direction)})
                current=label
            event=SimpleNamespace(held=keys,pressed=[],x=x,y=y,wheel=0,quit=False,active=True)
            g.input(event,.02);g.step();g.follow_camera(.02,free=67 in keys)
            own=g.player();state=serialize(g.sim.player_flight_state());controls=state['controls']
            if old_controls:
                max_surface_delta=max(max_surface_delta,max(abs(controls[k]-old_controls[k]) for k in ['aileron','elevator','rudder']))
            old_controls=controls
            target_yaw=math.atan2(g.player_input.direction[1],g.player_input.direction[0]);yaw=own.orientation[2]
            if old_target is not None:
                target_turn+=math.remainder(target_yaw-old_target,2*math.pi);aircraft_turn+=math.remainder(yaw-old_yaw,2*math.pi)
            old_target,old_yaw=target_yaw,yaw
            if tick%5==0:
                if g.renderer:
                    g.draw(0);max_basis=max(max_basis,basis_error(g))
                    if encoder:encoder.stdin.write(g.renderer.capture_rgb());frames+=1
                rows.append({'time':g.sim.frame().sim_time,'tick':g.sim.frame().tick,'phase':label,'pointer':[x,y],
                    'keys':keys,'intent':list(g.player_input.direction),'target_turn_rad':target_turn,'aircraft_turn_rad':aircraft_turn,
                    'own':serialize(own),'state':state,'camera':dict(g.camera_params)})
            if not own.alive or g.sim.frame().result!='running':raise AssertionError(('Flight terminated',label,t,g.sim.frame().result))
        if g.renderer:captures.append({'phase':current,'capture':g.capture(current)})
        if a.case=='edge':
            assert -math.degrees(target_turn)>180,('Target did not continue around',math.degrees(target_turn))
            assert -math.degrees(aircraft_turn)>180,('Aircraft did not turn around',math.degrees(aircraft_turn))
        else:
            for label,axis,sign in [('roll_right',0,1),('roll_left',0,-1),('pull',1,-1),('push',1,1)]:
                initial=next(r for r in phases if r['phase']==label)['own']
                final=next(r for r in reversed(rows) if r['phase']==label)['own']
                response=math.remainder(final['orientation'][axis]-initial['orientation'][axis],2*math.pi)*sign
                manual_checks.append({'phase':label,'signed_attitude_response_deg':math.degrees(response)})
                assert response>math.radians(.5),(label,'No signed aircraft response',response)
            both=[r for r in rows if r['phase']=='both_pitch']
            assert all(r['state']['pitch_manual_weight']==1 and abs(r['state']['desired_pitch_rate'])<1e-10 for r in both),'Both pitch keys did not request owned neutral rate'
            for label in ['free_pull','release_free']:
                group=[r for r in rows if r['phase']==label]
                initial=next(r for r in phases if r['phase']=='free_pull')['intent']
                error=max(math.dist(initial,r['intent']) for r in group)
                manual_checks.append({'phase':label,'maximum_world_intent_component_distance':error})
                assert error<1e-8,(label,'Free look changed intent',error)
        if g.renderer:assert max_basis<1e-5 and g.renderer.shader_errors()==0,(max_basis,g.renderer.shader_errors())
        assert max_surface_delta<=g.player_profile['control']['surface_rate']*.02+1e-8,max_surface_delta
    except Exception as error:failure=repr(error)
    finally:
        if encoder:encoder.stdin.close();code=encoder.wait();failure=failure or (('Encoder failed: '+str(code)) if code else None)
        write_json(a.output/'report.json',{'status':'failed' if failure else 'passed','failure':failure,'model':a.model,'case':a.case,
            'core_sha256':sha(Path(native.__file__)),'renderer_sha256':sha(Path(g.r.__file__)) if g.renderer else None,
            'map_sha256':g.scene_hash,'profile_file_sha256':g.profile_store.file_sha256,'effective_profile':g.player_profile,
            'target_turn_deg':math.degrees(target_turn),'aircraft_turn_deg':math.degrees(aircraft_turn),
            'maximum_surface_step':max_surface_delta,'maximum_render_basis_error':max_basis if g.renderer else None,
            'manual_checks':manual_checks,
            'shader_errors':g.renderer.shader_errors() if g.renderer else None,'video_frames':frames,
            'phases':phases,'captures':captures,'samples':rows,
            'acceptance_scope':'This protocol checks actual signed manual response, owned neutral W/S, frozen free-look intent, surface slew, sustained edge turn and rendered basis as applicable. It does not certify the full envelope, final settling, scenery, mission success or performance.',
            'method':'Actual FlightGame.input with deterministic handler events, native FDM and own-state chase camera at50Hz; DX12/film sampled at10Hz. Not hardware input injection or a performance benchmark.'})
        g.close()
    print('HANDLER',a.model,a.case,'failed' if failure else 'passed','target',math.degrees(target_turn),'aircraft',math.degrees(aircraft_turn),'failure',failure,flush=True)
    if failure:raise SystemExit(1)


if __name__=='__main__':main()
