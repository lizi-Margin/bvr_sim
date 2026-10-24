"""Inspect real source-FDM throttle/reheat transitions and native exhaust rendering."""
from pathlib import Path
import argparse,json,math,os,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize,DEFAULT_VISUAL_PROFILE
from bvr_game.content import write_json,sha
from bvr_game.playtest import digest
from validate_player_handler import basis_error


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline',type=Path)
    p.add_argument('--models',nargs='+',default=['FG-A-10','FG-F22','F22','F16'])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    baseline=json.loads(a.baseline.read_text()) if a.baseline else None
    g=FlightGame(render=True,visible=False,map_path=a.map,output=a.output/'client')
    initial_hashes={'core':sha(Path(native.__file__)),'renderer':sha(Path(g.r.__file__)),
        'visual_profile':sha(DEFAULT_VISUAL_PROFILE),'player_profile':g.profile_store.file_sha256,
        'validator':sha(Path(__file__))}
    rows=[]
    try:
        import imageio_ffmpeg
        g.quality='high';g.renderer.set_quality('high')
        for model in a.models:
            g.select_aircraft(model);g.config.mission='training';g.config.enemy_attacks=False
            g.config.seed=2201;g.start(start_position=[0,0,8500],initial_speed=250)
            direction=[v/math.hypot(*g.player().velocity) for v in g.player().velocity]
            encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24',
                '-s','1920x1080','-r','10','-i','-','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(a.output/(model+'.mp4'))],stdin=subprocess.PIPE)
            samples=[];captures=[];maximum_basis=0.;index=0
            try:
                for label,throttle,count in [('cruise',.85,40),('full',1.,120),('retard',.3,60)]:
                    g.submit_player(direction=direction,throttle=throttle)
                    for _ in range(count):
                        g.step(5);g.draw(.1);encoder.stdin.write(g.renderer.capture_rgb())
                        frame=serialize(g.sim.frame());maximum_basis=max(maximum_basis,basis_error(g))
                        if baseline:
                            old=next(r for r in baseline['models'] if r['model']==model)['samples'][index]
                            assert frame==old['complete_frame'],(model,index,'Existing complete core frame changed')
                        samples.append({'phase':label,'requested_throttle':throttle,'tick':frame['tick'],'complete_frame':frame,
                            'frame_sha256':digest(frame),'camera':dict(g.camera_params),
                            'exhaust_state':serialize(g.renderer.aircraft_exhaust_state()) if hasattr(g.renderer,'aircraft_exhaust_state') else None,
                            'aircraft_statistics':dict(g.renderer.aircraft_statistics())})
                        index+=1
                    captures.append({'phase':label,'file':g.capture(model+'-'+label)})
            finally:
                encoder.stdin.close();code=encoder.wait()
            assert code==0 and len(samples)==220 and maximum_basis<1e-5 and g.renderer.shader_errors()==0
            assert g.player().alive and g.sim.frame().result=='running'
            row={'model':model,'samples':samples,'captures':captures,'movie':str(a.output/(model+'.mp4')),
                'maximum_render_basis_error':maximum_basis,'shader_errors':g.renderer.shader_errors(),
                'complete_core_frames_equal_baseline':len(samples) if baseline else None}
            rows.append(row);write_json(a.output/'progress.json',{'completed_models':[r['model'] for r in rows]})
            print('EXHAUST_CAPTURED',model,len(samples),'basis',maximum_basis,flush=True)
        write_json(a.output/'report.json',{'status':'passed','hashes':initial_hashes,'map':str(a.map),'map_sha256':g.scene_hash,
            'models':rows,'baseline':str(a.baseline) if a.baseline else None,
            'scope':'Real native FDM stepped continuously per model; throttle intent phases, no pose injection. Direct DX12 backbuffer movie at10fps and complete core snapshots every5ticks. Diagnostic camera/effect inspection, not hardware input, full-envelope or performance certification.'})
    finally:g.close()


if __name__=='__main__':main()
