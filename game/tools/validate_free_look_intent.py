"""Real client-handler/GPU evidence for mouse intent across free-look release."""
from pathlib import Path
from types import SimpleNamespace
import argparse,json,math,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json,sha
from bvr_game.player_profiles import PlayerProfileStore


def angle(a,b):return math.degrees(math.acos(max(-1,min(1,sum(x*y for x,y in zip(a,b))))))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--profile-file',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=a.map,visual_profile=ROOT/'game/recipes/player_daylight.json',output=a.output/'client')
    g.profile_store=PlayerProfileStore(a.profile_file);g.player_profiles_frozen=True;rows=[];captures=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start(start_position=[-20000,0,8500],initial_speed=300);g.throttle=.85
        phases=[('neutral',50,[],960,540),('manual_pitch',100,[83],960,540),
                ('free_look',75,[67],1300,400),('free_look_pitch',50,[67,83],1300,400),
                ('release_no_pointer_motion',150,[],1300,400)]
        locked=None
        for label,ticks,keys,x,y in phases:
            if label=='free_look':locked=list(g.player_input.direction)
            for i in range(ticks):
                g.input(SimpleNamespace(held=keys,pressed=[],x=x,y=y,wheel=0,quit=False,active=True),.02);g.step()
                if i%5==0:g.draw(.1)
                rows.append({'phase':label,'tick':g.sim.frame().tick,'pointer':[x,y],'direction':list(g.player_input.direction),
                    'chase_free':list(g.chase.free),'core':serialize(g.sim.player_flight_state())})
            g.draw(.02);captures.append({'phase':label,'capture':g.capture(label)})
        hold=[r for r in rows if r['phase'].startswith('free_look')]
        after=[r for r in rows if r['phase']=='release_no_pointer_motion']
        held_error=max(angle(r['direction'],locked) for r in hold)
        released_error=max(angle(r['direction'],locked) for r in after)
        write_json(a.output/'report.json',{'status':'passed' if held_error<1e-5 and released_error<.1 else 'failed',
            'held_direction_change_deg':held_error,'released_without_pointer_motion_change_deg':released_error,
            'map_sha256':sha(a.map),'profile_file_sha256':g.profile_store.file_sha256,'shader_errors':g.renderer.shader_errors(),
            'captures':captures,'samples':rows,'method':'Actual FlightGame.input, native player control and DX12 camera. Deterministic handler events, not hardware input injection.'})
        print('FREE_LOOK_INTENT','held_change_deg',held_error,'release_change_deg',released_error,'shader',g.renderer.shader_errors())
        assert held_error<1e-5 and released_error<.1,(held_error,released_error)
    finally:g.close()


if __name__=='__main__':main()
