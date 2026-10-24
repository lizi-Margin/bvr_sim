"""Exercise the same input handler as the interactive window, then capture it."""
import argparse,json,os,sys,time
from types import SimpleNamespace
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import write_json,sha
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('game/captures/ui'))
    p.add_argument('--map',type=Path);p.add_argument('--visual-profile',type=Path);p.add_argument('--open-logs',action='store_true',help='Exercise the real F9 handler and open its sortie directory')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    options={k:v for k,v in [('map_path',a.map),('visual_profile',a.visual_profile)] if v is not None}
    game=FlightGame(render=True,visible=False,output=a.output/'client',**options);game.player_profiles_frozen=True
    report={'status':'running','scope':'Bounded controlled air mission using actual client input handlers and DX12 draws, with ordinary logs/HUD. No OS keyboard injection, hostile AI acceptance, all-mission coverage or FPS certification. Seed7 is a reused regression seed, not heldout.','images':[],'samples':[]}
    def key(k):return game.input(SimpleNamespace(held=[k],pressed=[k],x=960,y=540,quit=False),.02)
    try:
        game.quality='high';game.renderer.set_quality('high')
        game.config.enemy_attacks=False;game.config.enemy_range=3500;game.config.mission='air';game.config.seed=7
        for _ in range(20):game.draw()
        images=report['images'];images.append(game.capture('hangar'))
        key(50);key(13) # Select F16 in the hangar, then launch.
        assert game.config.player_model=='F16' and game.mode=='flight'
        initial=game.sim.frame().missiles_left
        deadline=time.monotonic()+180
        while not game.sim.frame().contacts and game.sim.frame().sim_time<10:
            game.step(5);game.draw()
        assert game.sim.frame().contacts,'No observed radar contact for client lock'
        key(82);game.step();key(32);game.step()
        assert game.sim.frame().missiles_left==initial-1
        images.append(game.capture('f16_locked_weapon_away'))
        key(80);paused=serialize(game.sim.frame());game.step(5)
        for _ in range(10):game.draw(.05)
        assert paused==serialize(game.sim.frame()),'Ordinary paused stepping/drawing changed core frame'
        images.append(game.capture('paused_weapon_away'));key(190)
        assert game.sim.frame().tick==paused['tick']+1 and game.sim.frame().paused
        report['pause']={'ordinary_step_and_draw_full_frame_exact':True,'exact_step_tick_delta':1,'paused_after_exact_step':True}
        key(80)
        while game.mode=='flight' and game.sim.frame().sim_time<120 and time.monotonic()<deadline:
            game.step(5);game.draw();report['samples'].append(serialize(game.sim.frame()))
            if len(report['samples'])%100==0:write_json(a.output/'partial-report.json',report)
        assert game.sim.frame().result=='succeeded';images.append(game.capture('f16_debrief'))
        report['result_flight_marks']=game.flight_marks;assert not game.flight_marks
        report['final_frame']=serialize(game.sim.frame());report['logs']=game.log_paths();report['effect_count_before_decay']=game.renderer.effect_count()
        before=serialize(game.sim.frame())
        for _ in range(240):game.draw(.05)
        assert serialize(game.sim.frame())==before,'Result presentation changed core state'
        report['effect_count_after_decay']=game.renderer.effect_count();assert report['effect_count_after_decay']==0
        images.append(game.capture('f16_debrief_effects_decayed'))
        sortie=Path(report['logs']['recent']);report['sortie_files']={p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in sortie.iterdir() if p.is_file()}
        for name in ['battle.acmi','core.log','input-tape.json','sortie.json']:assert (sortie/name).stat().st_size>0
        if a.open_logs:
            key(120);report['F9_opened_directory']=game.last_log_opened;assert Path(game.last_log_opened).resolve()==sortie.resolve()
        key(13);assert game.sim.frame().tick==0 and game.mode=='flight'
        report['retry_reset_tick']=game.sim.frame().tick;assert game.sim.frame().missiles_left==initial
        key(27);assert game.mode=='hangar';images.append(game.capture('back_to_hangar'))
        report.update(status='passed',ui_loop='passed',shader_errors=game.renderer.shader_errors(),core_sha256=sha(Path(native.__file__)),renderer_sha256=sha(Path(game.r.__file__)),map_sha256=game.scene_hash,profile_file_sha256=game.profile_store.file_sha256,visual_settings=json.loads(game.renderer.visual_settings()),tool_sha256=sha(__file__))
        assert report['shader_errors']==0;write_json(a.output/'report.json',report)
    except BaseException as error:
        report.update(status='failed',error=repr(error));write_json(a.output/'report.json',report);raise
    finally:game.close()
    from bvr_game.playtest import replay_journal
    try:
        report['journal_replay']=replay_journal(sortie/'input-tape.json',a.output/'headless-replay')
        assert report['journal_replay']['full_final_frame_equal'];write_json(a.output/'report.json',report)
    except BaseException as error:
        report.update(status='failed',error=repr(error));write_json(a.output/'report.json',report);raise
    print(json.dumps({'ui_loop':report['ui_loop'],'images':images,'shader_errors':report['shader_errors'],'journal_replay':report['journal_replay']['status']}),flush=True)
if __name__=='__main__':main()
