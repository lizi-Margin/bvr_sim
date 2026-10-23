"""Exercise the same input handler as the interactive window, then capture it."""
import argparse,json,time
from types import SimpleNamespace
from pathlib import Path
from bvr_game.app import FlightGame
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('game/captures/ui'));a=p.parse_args()
    game=FlightGame(render=True,visible=False,output=a.output)
    def key(k):return game.input(SimpleNamespace(held=[k],pressed=[k],x=960,y=540,quit=False),.02)
    try:
        game.config.enemy_attacks=False;game.config.enemy_range=3500
        for _ in range(20):game.draw()
        images=[game.capture('hangar')]
        key(50);key(13) # Select F16 in the hangar, then launch.
        assert game.config.player_model=='F16' and game.mode=='flight'
        game.step(10);key(82);game.step();key(32);game.step()
        assert game.sim.frame().missiles_left==3
        images.append(game.capture('f16_locked_weapon_away'))
        while game.mode=='flight':game.step(2);game.draw()
        assert game.sim.frame().result=='succeeded';images.append(game.capture('f16_debrief'))
        key(13);assert game.sim.frame().tick==0 and game.mode=='flight'
        key(27);assert game.mode=='hangar';images.append(game.capture('back_to_hangar'))
        print(json.dumps({'ui_loop':'passed','images':images,'shader_errors':game.renderer.shader_errors()}),flush=True)
    finally:game.close()
if __name__=='__main__':main()
