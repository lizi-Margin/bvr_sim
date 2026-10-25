"""Actual F22/F16 material review for the opt-in visibility shading path."""
from pathlib import Path
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--visual-profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    g=FlightGame(render=True,visible=False,runtime=a.runtime,visual_profile=a.visual_profile,
                 map_path=ROOT/'game/maps/training.json',output=a.output/'client')
    rows=[]
    try:
        g.renderer.set_presentation_paused(True);g.renderer.set_quality('high');g.hud=lambda:([],[])
        for model in ['F22','F16']:
            g.select_aircraft(model);g.mode='hangar';g.sim.set_paused(True);before=serialize(g.sim.frame())
            for mode in [False,True]:
                g.renderer.set_visibility_compute(mode)
                for _ in range(12):g.draw(1/60)
                rows.append({'aircraft':model,'visibility':mode,'capture':g.capture(model+('-visibility' if mode else '-raster')),
                             'settings':json.loads(g.renderer.visual_settings()),'timings':json.loads(g.renderer.frame_timings())})
                assert g.renderer.shader_errors()==0
                assert serialize(g.sim.frame())==before
                print('AIRCRAFT_VISIBILITY',model,mode,flush=True)
        write_json(a.output/'report.json',{'status':'captured_not_visual_acceptance','captures':rows,'core_frames_unchanged':True,
            'scope':'Actual source aircraft in the same hangar/camera. Raster and visibility material parity requires image review.'})
    finally:g.close()
if __name__=='__main__':main()
