"""Actual DX12 candidate frames and keyboard/core/model response evidence."""
from pathlib import Path
import argparse,json,math,os,sys
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--action',choices=['map','input'],default='map');a=p.parse_args()
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/river_valley_airfield/generated-map.json',
        visual_profile=ROOT/'game/recipes/player_daylight.json',output=a.output/'client')
    rows=[]
    try:
        g.quality='high';g.renderer.set_quality('high');g.select_aircraft('F16');g.config.mission='training';g.start()
        if a.action=='map':
            cameras={
                'airfield_overview':([4600,1100,-4200],[2950,220,-2100]),
                'runway_approach':([3550,280,-4400],[3500,220,-1400]),
                'airport_apron':([3400,340,-2700],[2800,225,-2100]),
                'river_valley':([1100,500,500],[-650,120,2850]),
                'town_roads':([3400,600,2200],[2700,210,3500]),
                'industry_frontage':([2400,520,1700],[1400,180,2650]),
                'regional_transition':([3500,4200,-7000],[0,170,6000])}
            g.show_hud=False
            for name,(eye,target) in cameras.items():
                g.set_camera(eye,target,fov=1.)
                for _ in range(40):g.draw()
                rows.append({'view':name,'capture':g.capture(name),'shader_errors':g.renderer.shader_errors()})
            g.select_aircraft('F22');g.config.mission='training';g.start(start_position=[-20000,0,8500],initial_speed=300)
            g.set_camera([32,8511,-20032],[0,8501,-20000],.92)
            for _ in range(40):g.draw()
            rows.append({'view':'fixed_high_horizon','capture':g.capture('fixed_high_horizon'),'shader_errors':g.renderer.shader_errors()})
        else:
            for model in ['F22','F16','FG-A-10']:
                g.select_aircraft(model);g.config.mission='training';g.config.speed=180 if model=='FG-A-10' else 300;g.config.altitude=8500
                for key in ['W','S']:
                    g.start(start_position=[-20000,0,8500],initial_speed=180 if model=='FG-A-10' else 300);initial=serialize(g.player())
                    for _ in range(20):g.draw()
                    for i in range(50):
                        g.input(SimpleNamespace(held=[ord(key)],pressed=[],x=960,y=540,wheel=0,quit=False,active=True),.02);g.step();g.draw(.02)
                    actual=g.player();forward=list(g.renderer.entity_forward('player'));state=serialize(g.sim.player_flight_state())
                    expected_up=key=='S';assert (actual.orientation[1]<initial['orientation'][1])==expected_up,(model,key,actual.orientation)
                    assert (forward[1]>0)==expected_up,(model,key,forward)
                    rows.append({'model':model,'key':key,'initial':initial,'core':serialize(actual),'player_state':state,
                        'rendered_forward':forward,'capture':g.capture(model+'_'+key),'shader_errors':g.renderer.shader_errors(),
                        'input_path':'Real FlightGame.input handler with explicit deterministic events; not a claim of physical keyboard hardware injection'})
        write_json(a.output/'report.json',{'captures':rows,'visual_settings':json.loads(g.renderer.visual_settings()),'statistics':serialize(g.renderer.statistics()),
            'map_sha256':g.scene_hash,'shader_errors':g.renderer.shader_errors(),'native_core':str(__import__('bvr_game.app',fromlist=['native']).native.__file__)})
        print('GPU_CANDIDATE_CAPTURED',a.action,len(rows),'shader',g.renderer.shader_errors(),flush=True)
    finally:g.close()
if __name__=='__main__':main()
