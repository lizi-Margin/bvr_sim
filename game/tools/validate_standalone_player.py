"""Run the real standalone interactive entry using deterministic typed events."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,math,os,sys,subprocess
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.aircraft import aircraft,aircraft_catalog
from bvr_game.aircraft_library import fly_interactive,player_test_flight
from bvr_game.app import serialize,native
from bvr_game.content import write_json,sha
from bvr_game.playtest import replay
from validate_player_handler import basis_error

def catalog_smoke(output,map_path):
    rows=[]
    for original in aircraft_catalog(include_library=True)['aircraft']:
        game=None
        try:
            row=aircraft(original['id'],require_available=True)
            game=player_test_flight(row,output/'clients'/row['id'],render=False,map_path=map_path)
            own=game.player();length=math.hypot(*own.velocity)
            game.submit_player(direction=[v/length for v in own.velocity],throttle=.85);game.step(10)
            frame=game.sim.frame();own=game.player();state=game.sim.player_flight_state()
            assert own.alive and frame.result=='running' and state.active and state.configured
            rows.append({'id':row['id'],'status':'passed','fdm':row['fdm']['type'],'library_aircraft':game.config.library_aircraft,
                'tick':frame.tick,'speed_mps':math.hypot(*own.velocity),'altitude_m':own.position[2],
                'player_profile_sha256':game.player_profile['effective_sha256'],'tuning_status':game.player_profile['tuning_status'],
                'appearance_sha256':row['appearance']['glb_sha256']})
        except Exception as error:rows.append({'id':original['id'],'status':'failed','error':repr(error)})
        finally:
            if game:game.close()
        write_json(output/'catalog-smoke-progress.json',{'checked':len(rows),'rows':rows})
    failed=[r for r in rows if r['status']!='passed']
    write_json(output/'report.json',{'status':'failed' if failed else 'passed','rows':rows,'checked':len(rows),'failed':failed,
        'core_sha256':sha(Path(native.__file__)),'map_sha256':sha(map_path),
        'scope':'All selectable registered models hash-checked, started through the standalone player factory and advanced10actualcoreticks. Basic readiness only, not per-model tuning, stable300sflight, visual correctness or performance.'})
    print('STANDALONE_CATALOG',len(rows),'FAILED',len(failed),flush=True)
    if failed:raise SystemExit(1)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--model',default='FG-A-10');p.add_argument('--map',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--video',action='store_true')
    p.add_argument('--catalog-smoke',action='store_true',help='Headless10tickreadiness for the complete selectable catalog, not flight tuning');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    if a.catalog_smoke:return catalog_smoke(a.output,a.map)
    samples=[];captures=[];phases=[];encoder=None;movie_frames=0;maximum_basis=0.;previous=None
    boundaries=[(0,'neutral'),(100,'pull'),(150,'release_pull'),(250,'push'),(300,'release_push'),(400,'roll_left'),(425,'release_left'),
        (475,'roll_right'),(500,'release_right'),(600,'free_pull'),(650,'release_free'),(750,'zoom'),(800,'resize'),(850,'pause'),
        (875,'resume'),(900,'raw_manual'),(950,'mouse_resume'),(1050,'release_mouse')]
    def label(index):return next(name for start,name in reversed(boundaries) if start<=index)
    if a.video:
        import imageio_ffmpeg
        encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','10','-i','-',
            '-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(a.output/'standalone.mp4')],stdin=subprocess.PIPE)
    def source(game,index):
        nonlocal maximum_basis,previous,movie_frames
        if index==0:
            for _ in range(20):game.draw(0)
        if index and (index-1)%5==0:
            frame=game.sim.frame();maximum_basis=max(maximum_basis,basis_error(game))
            samples.append({'client_frame':index-1,'phase':label(index-1),'tick':frame.tick,'time':frame.sim_time,
                'intent':list(game.player_input.direction),'state':serialize(game.sim.player_flight_state()),'own':serialize(game.player()),
                'camera':dict(game.camera_params),'viewport':[game.width,game.height],'dynamic_contact_label_count':len(game.hud_layout)})
            if encoder:
                pixels=game.renderer.capture_rgb()
                if [game.width,game.height]!=[1920,1080]:
                    # Preserve every source pixel when displaying resize tests
                    # in the fixed-size movie; black padding, no resampling.
                    from PIL import Image
                    canvas=Image.new('RGB',(1920,1080));canvas.paste(Image.frombytes('RGB',(game.width,game.height),pixels),(0,0));pixels=canvas.tobytes()
                encoder.stdin.write(pixels);movie_frames+=1
        current=label(min(index,1099))
        if current!=previous:
            if previous:captures.append({'phase':previous,'capture':game.capture(previous)})
            phases.append({'phase':current,'tick':game.sim.frame().tick,'own':serialize(game.player()),'intent':list(game.player_input.direction)})
            previous=current
        if index>=1100:return SimpleNamespace(held=[],pressed=[27],x=960,y=540,quit=False)
        if index==800:game.renderer.resize(1600,1000)
        if index==850:game.renderer.resize(1920,1080)
        width,height=(1600,1000) if 800<=index<850 else (1920,1080)
        keys=[83] if 100<=index<150 else [87] if 250<=index<300 else [65] if 400<=index<425 else [68] if 475<=index<500 else [67,83] if 600<=index<650 else [2] if 750<=index<800 else []
        pressed={850:[80],855:[117],860:[190],875:[80],900:[116],950:[116]}.get(index,[])
        x,y=(width*.68,height*.3) if 600<=index<850 else (width*.93,height*.42) if 950<=index<1050 else (width*.5,height*.5)
        return SimpleNamespace(held=keys,pressed=pressed,x=x,y=y,width=width,height=height,wheel=0,quit=False,active=True,pad_connected=False,pad_axes=[])
    try:
        flight=fly_interactive(aircraft(a.model),a.output/'client',map_path=a.map,event_source=source,frame_dt=.02,visible=False)
    finally:
        if encoder:encoder.stdin.close();code=encoder.wait();assert code==0,code
    write_json(a.output/'raw-protocol.json',{'flight':flight,'samples':samples,'phases':phases,'captures':captures,
        'maximum_render_basis_error':maximum_basis,'video_frames':movie_frames})
    assert flight['frame']['result']=='running' and all(row['own']['alive'] for row in samples),'Aircraft terminated during the protocol'
    assert flight['shader_errors']==0 and maximum_basis<1e-5
    checks=[]
    for name,axis,sign in [('pull',1,-1),('push',1,1),('roll_left',0,-1),('roll_right',0,1)]:
        begin=next(row for row in phases if row['phase']==name)['own']['orientation'][axis]
        end=next(row for row in reversed(samples) if row['phase']==name)['own']['orientation'][axis]
        change=math.remainder(end-begin,2*math.pi)*sign;checks.append({'phase':name,'signed_attitude_change_deg':math.degrees(change)})
        assert change>math.radians(.5),(name,change)
    for name in ['zoom','resize']:
        values=[row for row in samples if row['phase']==name];start=next(row for row in phases if row['phase']==name)['intent']
        error=max(math.dist(start,row['intent']) for row in values);checks.append({'phase':name,'maximum_intent_distance':error});assert error<1e-8,(name,error)
    paused=[row for row in samples if row['phase']=='pause'];assert max(row['tick'] for row in paused)-min(row['tick'] for row in paused)==1
    assert all(row['state']['mode']=='raw_manual' for row in samples if row['phase']=='raw_manual')
    tapes=list((a.output/'sortie-logs').glob('*/input-tape.json'));assert len(tapes)==1
    comparison=replay(tapes[0],a.output/'headless-replay');assert comparison['full_final_frame_equal']
    write_json(a.output/'report.json',{'status':'passed','model':a.model,'flight':flight,'checks':checks,'samples':samples,'phases':phases,'captures':captures,
        'maximum_render_basis_error':maximum_basis,'video_frames':movie_frames,'nominal_client_seconds':22,'core_seconds':flight['frame']['sim_time'],
        'headless_replay':comparison,'core_sha256':sha(Path(native.__file__)),'source_sha256':sha(ROOT/'bvr_game/aircraft_library.py'),
        'scope':'Real fly_interactive entry, shared run_client_frame, native FDM/DX12. Exercises pitch/roll,free-look,zoom,actualwindowresize,pause/exactstep,reload,rawmode andresumedmouse. Resize movie frames are padded without resampling. No performance or complete-envelope claim.'})
    print('STANDALONE_PLAYER',a.model,'passed',flight['frame']['tick'],movie_frames,maximum_basis)

if __name__=='__main__':main()
