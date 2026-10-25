"""Actual DX12 page capture and real FlightGame.input navigation acceptance."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,os,sys,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.content import sha,write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,output=a.output/'client',
                 width=a.width,height=a.height,user_settings=a.output/'preferences.json')
    f=g.frontend;captures={};checks=[]
    def event(keys=(),x=960,y=540,held=()):
        return g.input(SimpleNamespace(pressed=list(keys),held=list(held),x=x*a.width/1920,y=y*a.height/1080,quit=False,wheel=0),.02)
    def click(id):
        f.layout();_,(x,y,w,h),_=next(r for r in f.regions if r[0]==id)
        assert event([1],x+w/2,y+h/2)
    def choose(id,value):
        click(id);f.layout();key=next(r[0] for r in f.regions if r[2][:2]==('option',id) and r[2][2]==value);click(key)
    def capture(name):
        for _ in range(6):g.draw()
        captures[name]=g.capture(name)
    try:
        before=serialize(g.sim.frame());capture('hangar-F22')
        click('menu');capture('hangar-menu');click('menu')
        click('settings');capture('settings-general')
        click('nav_flight');click('pref_mouse_sensitivity');capture('settings-dropdown');click('pref_mouse_sensitivity')
        choose('pref_mouse_sensitivity',1.25);capture('settings-flight')
        click('cancel');assert f.settings.values['mouse_sensitivity']==1.
        assert serialize(g.sim.frame())==before;checks.append('cancel_settings_keeps_complete_core_frame_and_preferences')
        event([113]);click('nav_flight');choose('pref_mouse_sensitivity',1.25);click('apply')
        assert f.settings.values['mouse_sensitivity']==1.25
        assert json.loads((a.output/'preferences.json').read_text())['preferences']['mouse_sensitivity']==1.25
        assert g.player_input.profile['input']['sensitivity']==g.player_profile['input']['sensitivity']*1.25
        checks.append('apply_settings_persists_and_changes_client_input_only')
        click('settings');click('tab_graphics');capture('settings-graphics');click('tab_controls');capture('settings-controls');click('cancel')
        assert serialize(g.sim.frame())==before
        event([50]);assert g.current_aircraft()['id']=='F16';capture('hangar-F16')
        before=serialize(g.sim.frame());config=serialize(g.config)
        click('battle');click('mission');capture('prepare-mission-dropdown');click('mission')
        choose('mission','strike');choose('loadout','strike');capture('prepare-strike')
        assert serialize(g.sim.frame())==before and serialize(g.config)==config
        click('back');assert serialize(g.config)==config
        checks.append('prepare_drafts_and_cancel_preserve_config_and_full_core_frame')
        tree_before=serialize(g.sim.frame());tree_config=serialize(g.config)
        click('country_usa');capture('tree-usa-early');event([35]);capture('tree-usa-late');event([27])
        click('search');event([70]);event([50]);event([50]);event([13]);f.layout()
        family=next(r[0] for r in f.regions if r[0].startswith('family_'));click(family);capture('tree-family-F22')
        event([27]);click('search');event([27])
        click('country_germany');capture('tree-germany');click('country_joint');capture('tree-joint')
        click('country_fictional');capture('tree-fictional')
        assert serialize(g.sim.frame())==tree_before and serialize(g.config)==tree_config
        checks.append('country_tree_family_expansion_and_search_preserve_complete_core_frame')
        click('country_usa');click('search');event([65]);event([49]);event([48]);event([13])
        assert any(r['id']=='FG-A-10' for r in f.rows())
        click('tree_aircraft_FG-A-10');capture('hangar-A10')
        click('testflight');capture('prepare-imported-training')
        assert f.missions()==['training'] and f.preparation['loadout']=='unarmed'
        assert not f.preparation['enemy_attacks'];click('back');checks.append('imported_aircraft_training_capabilities_are_enforced')
        g.aircraft_search='';f.country='usa';f.offset=0;f.select('F16')
        g.config.mission='air';g.config.enemy_attacks=False;g.config.enemy_range=3500
        event([13]);assert f.page=='prepare' and g.mode=='hangar';capture('prepare-air')
        click('launch');assert g.mode=='flight' and g.sim.frame().tick==0
        assert g.config.player_model=='F16' and g.config.mission=='air'
        checks.append('join_battle_prepare_confirm_starts_real_configured_sortie')
        g.step(10);event([82]);g.step();event([32]);g.step();capture('sortie-weapon-away')
        assert g.sim.frame().missiles_left==3
        g.step(1500);assert g.sim.frame().result=='succeeded';capture('sortie-result')
        event([27]);assert g.mode=='hangar' and f.page=='hangar';capture('hangar-return')
        checks.append('real_lock_launch_hit_result_and_return_to_new_hangar')
        report={'status':'passed','scope':'Actual nativeDX12 backbuffer with real client input handlers; no OS mouse/keyboard injection. This is page/layout/function acceptance, not map visual acceptance or FPS certification.',
                'checks':checks,'captures':captures,'resolution':[a.width,a.height],
                'shader_errors':g.renderer.shader_errors(),'core_sha256':sha(Path(native.__file__)),
                'renderer_sha256':sha(Path(g.r.__file__)),'preferences':f.settings.values,
                'configuration':serialize(g.config),'final_frame':serialize(g.sim.frame()),'logs':g.log_paths()}
        assert report['shader_errors']==0;write_json(a.output/'report.json',report)
        print(json.dumps({'status':report['status'],'captures':len(captures),'checks':len(checks),'shader_errors':report['shader_errors']}),flush=True)
    except BaseException as error:
        write_json(a.output/'failure.json',{'error':repr(error),'captures':captures,'checks':checks,'page':f.page,'frame':serialize(g.sim.frame())})
        raise
    finally:g.close()
if __name__=='__main__':main()
