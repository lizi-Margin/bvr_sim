"""Actual DX12 preparation/input/fire capture plus identical headless input replay."""
from pathlib import Path
from types import SimpleNamespace
import argparse,hashlib,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.player_input import native_intent
from bvr_game.content import write_json

def run(output,runtime,width,height,render,replay=None):
    g=FlightGame(render=render,visible=False,runtime=runtime,width=width,height=height,
                 output=output/'client',user_settings=output/'preferences.json')
    g.logs_enabled=False;f=g.frontend;captures={};trace=[];inputs=[]
    original_dispatch=g._dispatch_player_intent
    def dispatch(intent):
        # Identical pointer events can produce different intents with different cameras.
        # Compare physics using the exact typed intents recorded at the core boundary.
        if replay is not None:
            assert len(inputs)<len(replay),'Unexpected additional headless input'
            intent=native_intent(native,replay[len(inputs)])
        inputs.append(serialize(intent));original_dispatch(intent)
    g._dispatch_player_intent=dispatch
    def event(keys=(),x=960,y=540):
        return g.input(SimpleNamespace(pressed=list(keys),held=[],x=x*width/1920,y=y*height/1080,quit=False,wheel=0),.02)
    def click(id):
        f.layout();_,(x,y,w,h),_=next(r for r in f.regions if r[0]==id)
        event([1],x+w/2,y+h/2)
    def capture(name):
        if render:
            for _ in range(3):g.draw()
            captures[name]=g.capture(name)
    def cycle(weapon):
        for _ in range(5):
            if g.weapon==weapon:return
            event([86])
        raise AssertionError(('cannot select',weapon,g.weapon))
    try:
        for model in ['F22','F15']:
            g.select_aircraft(model);click('battle');capture('prepare-'+model)
            click('back')
        g.select_aircraft('F16');g.config.mission='air';g.config.enemy_attacks=False;g.config.enemy_range=3500
        before=serialize(g.sim.frame());config=serialize(g.config)
        click('battle');click('station_1');click('mount_empty');click('mirror');click('back')
        assert serialize(g.sim.frame())==before and serialize(g.config)==config
        click('battle');click('station_1');click('mount_AIM-9M');click('mirror')
        click('station_2');click('mount_AIM-120C7');click('mirror')
        click('station_3');click('mount_Mk-82');click('mirror');capture('prepare-F16-mixed')
        mounts=dict(f.preparation['mounts']);click('launch')
        assert g.mode=='flight' and dict(g.config.loadout)==mounts
        for weapon in ['AIM-9M','AIM-120C7']:
            if trace:g.start(record=False)
            g.step(10);cycle(weapon);event([82]);g.step();capture('selected-'+weapon)
            before=g.sim.frame().missiles_left;event([32]);g.step();capture('launch-'+weapon)
            frame=g.sim.frame();assert frame.missiles_left==before-1
            assert any(e.kind=='missile_launched' and e.weapon==weapon for e in frame.events)
            assert any(e.kind=='missile' and e.model==weapon for e in frame.entities)
            trace.append(serialize(frame))
            g.step(1500);frame=g.sim.frame();capture('result-'+weapon)
            assert frame.air_kills==1 and frame.result=='succeeded'
            assert sum(e.kind=='missile_hit' and e.weapon==weapon for e in frame.events)==1
            trace.append(serialize(frame))
        g.config.mission='strike';g.config.enemy_attacks=False;g.start(record=False);cycle('Mk-82')
        released=False
        for _ in range(3000):
            frame=g.sim.frame()
            if frame.bomb_impact and abs(frame.bomb_impact[0]-g.config.ground_north)<20 and abs(frame.bomb_impact[1]-g.config.ground_west)<20:
                before=frame.bombs_left;capture('selected-Mk-82');event([66]);g.step()
                assert g.sim.frame().bombs_left==before-1;capture('release-Mk-82')
                trace.append(serialize(g.sim.frame()));released=True;break
            g.step(2)
        assert released,'No real-flight CCIP release solution reached'
        g.step(3000);frame=g.sim.frame();capture('result-Mk-82')
        assert frame.ground_kills==1 and frame.result=='succeeded'
        assert sum(e.kind=='bomb_impact' for e in frame.events)==1
        trace.append(serialize(frame))
        if replay is not None:assert len(inputs)==len(replay),'Headless replay did not consume every recorded intent'
        report={'status':'passed','render':render,'resolution':[width,height],'captures':captures,'typed_inputs':inputs,
                'mounts':mounts,'trace':trace,'core_module':native.__file__,
                'core_sha256':hashlib.sha256(Path(native.__file__).read_bytes()).hexdigest(),
                'checks':['draft_cancel_preserves_world_and_config','compatible_station_selection','mirror_fill',
                          'mixed_loadout_committed','V_cycles_mounted_types','AIM9_real_input_launch_hit_once',
                          'AIM120_real_input_launch_hit_once','Mk82_B_release_CCiP_impact_ground_kill_once']}
        if render:
            report['renderer_module']=g.r.__file__;report['shader_errors']=g.renderer.shader_errors()
            assert report['shader_errors']==0
        write_json(output/'report.json',report);return report
    except BaseException as error:
        write_json(output/'failure.json',{'error':repr(error),'captures':captures,'frame':serialize(g.sim.frame())})
        raise
    finally:g.close()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    rendered=run(a.output/'rendered',a.runtime,a.width,a.height,True)
    headless=run(a.output/'headless',a.runtime,a.width,a.height,False,rendered['typed_inputs'])
    assert rendered['trace']==headless['trace'],'Rendered/headless core state mismatch'
    write_json(a.output/'acceptance.json',{'status':'passed','checks':rendered['checks']+['identical_typed_input_rendered_headless_core_states'],
        'captures':rendered['captures'],'resolution':[a.width,a.height],'core_sha256':rendered['core_sha256'],
        'shader_errors':rendered['shader_errors'],
        'scope':'Real DX12 and FlightGame input handlers. Headless replays exact typed intents recorded at the core boundary, avoiding camera-dependent pointer transforms. No OS input injection or exclusive GPU performance claim.'})
    print(json.dumps({'status':'passed','captures':len(rendered['captures']),'checks':9,'parity':True}),flush=True)
if __name__=='__main__':main()
