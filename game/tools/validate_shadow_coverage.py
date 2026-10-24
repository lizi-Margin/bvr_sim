"""Same-camera, same-tick directional shadow coverage comparison in real DX12."""
from pathlib import Path
import argparse,json,os,sys,time
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/river_valley_airfield/generated-map.json',
        visual_profile=ROOT/'game/recipes/player_daylight.json',output=a.output/'client');rows=[]
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True);g.show_hud=False;g.renderer.set_quality('high')
        cameras={'overview':([4600,1100,-4200],[2950,220,-2100]),'apron':([3400,340,-2700],[2800,225,-2100]),
            'town':([3400,600,2200],[2700,210,3500])}
        for name,(eye,target) in cameras.items():
            g.set_camera(eye,target,1.)
            for label,distances in [('default',[8,80,800]),('aviation',[96,800,4000,12000])]:
                g.renderer.set_shadow_cascades(distances)
                for _ in range(60):g.draw()
                rows.append({'view':name,'variant':label,'tick':g.sim.frame().tick,'capture':g.capture(name+'-'+label),
                    'settings':json.loads(g.renderer.visual_settings()),'scene_statistics':serialize(g.renderer.statistics()),'shader_errors':g.renderer.shader_errors()})
        write_json(a.output/'report.json',{'status':'captured_pending_pixel_review','comparison':'Same paused core tick, scene, camera, exposure and source materials; only directional shadow cascade coverage changes',
            'map_sha256':g.scene_hash,'rows':rows,'shader_errors':g.renderer.shader_errors()});print('SHADOW_COVERAGE_CAPTURED',len(rows),'shader',g.renderer.shader_errors())
    finally:g.close()
if __name__=='__main__':main()
