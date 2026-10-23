"""Capture a paused scene through the explicit camera API, without clicking."""
import argparse,json
from pathlib import Path
from bvr_game.app import FlightGame
def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('game/captures/scene'));a=p.parse_args()
    game=FlightGame(render=True,visible=False,output=a.output)
    try:
        game.start();game.sim.set_paused(True)
        game.set_camera([-70,25,6055],[-12,5,6015],fov=1.05)
        for _ in range(20):game.draw()
        result={'capture':game.capture('depot_and_registered_barrier'),'tick':game.sim.frame().tick,'shader_errors':game.renderer.shader_errors()}
        print(json.dumps(result),flush=True)
    finally:game.close()
if __name__=='__main__':main()
