"""Real input, core motion, imported hangar and radar regression evidence."""
import argparse,json,math,sys
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize

def event(game,held=(),pressed=(),x=960,y=540,wheel=0):
    return game.input(SimpleNamespace(held=list(held),pressed=list(pressed),x=x,y=y,wheel=wheel,quit=False),.02)

def controls(out):
    game=FlightGame(output=out/'controls');rows=[]
    try:
        game.config.enemy_attacks=False;game.config.mission='training'
        for id in ['F22','F16','F15','F18','F4N','FG-A-10','FG-YF-23','FG-737-800']:
            game.select_aircraft(id)
            for name,key,mouse_y in [('W',87,540),('S',83,540),('mouse_up',None,230),('mouse_down',None,780)]:
                game.start();initial=serialize(game.player());frames=[]
                for tick in range(100):
                    event(game,held=([key] if key else []),y=mouse_y);game.step()
                    if tick%10==9:frames.append(serialize(game.sim.frame()))
                final=serialize(game.player());sign=1 if name in ['S','mouse_up'] else -1
                row={'id':id,'input':name,'initial':initial,'final':final,'frames':frames,'pitch_change_deg':-math.degrees(final['orientation'][1]-initial['orientation'][1]),'altitude_change_m':final['position'][2]-initial['position'][2]}
                assert final['alive'],(id,name,'died')
                if key:assert final['animation_properties']['controls/flight/elevator']==-sign
                rows.append(row)
        (out/'controls.json').write_text(json.dumps({'status':'passed','cases':rows},indent=2),encoding='utf8')
    finally:game.close()

def gpu(out,limit=None):
    game=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/training_range_v3/generated-map.json',output=out/'gpu')
    records=[];retained={'F22','F16','F15','F18','F4N','FG-737-800','FG-A-10','FG-YF-23','FG-B29','FG-An-225'}
    try:
        game.quality='high';game.renderer.set_quality('high');game.config.enemy_attacks=False
        # Independent radar and SA labels must coexist, using the real HUD builder.
        game.start();game.step(10);game.draw()
        texts,_=game.hud();labels=[t.text for t in texts]
        assert any(t.startswith('RADAR / ') for t in labels) and 'RWR / SA' in labels
        radar=game.capture('radar_and_sa')
        for row in game.aircraft_rows[:limit]:
            id=row['id'];game.select_aircraft(id)
            for _ in range(3):game.draw()
            preview=game.capture('hangar_'+id) if id in retained else None
            assert game.renderer.aircraft_statistics()['instances']==1,(id,'stale preview')
            event(game,pressed=[13]);game.step(100);game.draw()
            assert game.player().alive,(id,'test flight died')
            flight=game.capture('flight_'+id) if id in retained else None
            assert game.renderer.shader_errors()==0,id
            records.append({'id':id,'model':game.player().model,'backend':game.config.fdm,'library':game.config.library_aircraft,'tick':game.sim.frame().tick,'alive':game.player().alive,'preview':preview,'flight':flight,'shader_errors':0,'statistics':serialize(game.renderer.aircraft_statistics())})
            print(id,'passed',flush=True)
            (out/'hangar-progress.json').write_text(json.dumps(records,indent=2),encoding='utf8')
            event(game,pressed=[27])
        # Real mouse/key path and frame parity with manual elevator commands.
        game.select_aircraft('F22');game.config.mission='training';game.start();frames=[]
        for _ in range(50):event(game,held=[83]);game.step();game.draw();frames.append(serialize(game.sim.frame()))
        up=game.capture('S_pull_real_motion')
        up_forward=list(game.renderer.entity_forward('player'))
        assert up_forward[1]>0,'Rendered nose points down during measured nose-up'
        game.start()
        for _ in range(50):event(game,held=[87]);game.step();game.draw()
        down=game.capture('W_push_real_motion')
        down_forward=list(game.renderer.entity_forward('player'))
        assert down_forward[1]<0,'Rendered nose points up during measured nose-down'
        game.start()
        for index in range(50):
            event(game,held=[83]);game.step()
            assert serialize(game.sim.frame())==frames[index]
        report={'status':'passed','aircraft_count':len(records),'records':records,'radar_and_sa':radar,'pitch_captures':[up,down],'rendered_nose_forward':{'S':up_forward,'W':down_forward},'manual_pitch_frame_samples_equal':50,'shader_errors':game.renderer.shader_errors()}
        (out/'hangar-report.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    finally:game.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['controls','gpu']);p.add_argument('--output',type=Path,required=True);p.add_argument('--limit',type=int);a=p.parse_args();a.output.mkdir(parents=True,exist_ok=True)
    controls(a.output) if a.action=='controls' else gpu(a.output,a.limit)
