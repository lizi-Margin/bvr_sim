"""Real frozen loss replay; visual dissipation cannot advance core or invent events."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.playtest import ResidentPlaytest,digest
from bvr_game.ground import apply_config
from bvr_game.app import native,serialize
from bvr_game.content import write_json
out=Path(sys.argv[1]);data=json.loads((out/'reports/playtests/final-fixed20/101/input-tape.json').read_text());host=ResidentPlaytest(out/'after/result-effects',render=True)
try:
 apply_config(native,host.game.config,data['config']);host.game.start();matched=0
 for action in data['actions']:
  host.step(action['ticks'],action['command']);assert digest(serialize(host.game.sim.frame()))==action['frame_sha256'];matched+=1
 g=host.game;frame=serialize(g.sim.frame());hash_before=digest(frame);rows=[];before=g.capture('instantaneous-real-impact')
 for i in range(451):
  if i in [0,12,60,300,450]:rows.append({'presentation_frame':i,'effect_count':g.renderer.effect_count(),'core_tick':g.sim.frame().tick})
  if i<450:g.draw(1/60)
 assert digest(serialize(g.sim.frame()))==hash_before and rows[-1]['effect_count']==0
 after=g.capture('settled-result');write_json(out/'reports/result-effects-parity.json',{'status':'passed','complete_loss_frames_compared':matched,'after_result_draws':450,'presentation_seconds':7.5,'core_tick_unchanged':frame['tick'],'complete_core_frame_unchanged':True,'counts':rows,'instantaneous_capture':before,'settled_capture':after,'shader_errors':g.renderer.shader_errors(),'logs':g.log_paths()})
 print('Result FX dissipated without core tick/state changes',rows)
finally:host.close()
