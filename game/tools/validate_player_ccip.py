"""Actual player-intent release, CCIP prediction and core Mk82 contact comparison."""
from pathlib import Path
import argparse,json,math,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import sha,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--river-case',action='store_true',help='Also release over the authored physical channel and require an actual below-water bed contact')
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(map_path=a.map,output=a.output/'client');rows=[]
    cases=[('low_airfield','F16',[-4500,-3500,500],180,[1,0,0]),
           ('valley_slope','F16',[-6000,-2300,2000],250,[1,.1,-.04]),
           ('far_offset','F22',[150000,-50000,8500],500,[1,0,0])]
    if a.river_case:cases.append(('river_bed','F16',[-6500,380,500],180,[1,0,0]))
    try:
        for name,model,position,speed,direction in cases:
            g.select_aircraft(model,'strike');g.config.mission='training';g.config.enemy_attacks=False;g.config.seed=2201
            g.start(start_position=position,initial_speed=speed);g.submit_player(direction=direction,throttle=.95);g.step(100)
            before=serialize(g.sim.frame());predicted=before['bomb_impact'];assert predicted is not None
            g.submit_player(direction=direction,throttle=.95,drop_bomb=True);g.step();trace=[];impact=None
            for _ in range(1200):
                frame=serialize(g.sim.frame());trace.append(frame)
                impact=next((e for e in frame['events'] if e['kind']=='bomb_impact'),None)
                if impact:break
                assert frame['result']=='running',frame['result']
                g.step(5)
            assert impact is not None,'Released bomb never contacted the core environment'
            actual=impact['position'];terrain=g.sim.terrain();contact=terrain.collision_height(actual[0],actual[1])
            row={'case':name,'model':model,'configured_position':position,'configured_speed':speed,'direction':direction,
                'release_frame':before,'impact':impact,'predicted':predicted,'actual_contact_height':contact,
                'position_error_m':math.dist(predicted,actual),'actual_contact_height_error_m':abs(actual[2]-contact),
                'predicted_actual_height_difference_m':abs(predicted[2]-actual[2]),'final_frame':frame}
            if name=='river_bed':
                from shapely.geometry import Point,LineString
                document=g.baked_scene.document
                assert document.get('landscape',{}).get('river_channel'),'River case requires a shared physical channel map'
                river=min(document['rivers'],key=lambda r:LineString(r['points']).distance(Point(*actual[:2])))
                distance=LineString(river['points']).distance(Point(*actual[:2]))
                # The map's authored level is carried by its immutable recipe.
                recipe_dir=a.map.parent/'versions'/document['data_version'] if document.get('data_version') else a.map.parent
                level=json.loads((recipe_dir/'scene-recipe.json').read_text())['terrain']['river_level_m']
                row.update(river_center_distance_m=distance,water_surface_m=level,bed_below_water_m=level-contact,
                    water_interaction_scope='Existing core collision reaches the shared bed; this is not fluid drag, buoyancy or water-surface detonation physics')
                assert distance<river['width_m']/2 and level-contact>1.,row
            rows.append(row);write_json(a.output/(name+'-trace.json'),trace)
            print(name,'prediction_error_m',row['position_error_m'],'contact_height_error_m',row['actual_contact_height_error_m'],flush=True)
        maximum=max(r['position_error_m'] for r in rows);height=max(r['actual_contact_height_error_m'] for r in rows)
        write_json(a.output/'report.json',{'status':'passed' if maximum<=.1 and height<=.1 else 'failed',
            'map_sha256':sha(a.map),'core_sha256':sha(Path(native.__file__)),'cases':rows,'maximum_position_error_m':maximum,
            'maximum_actual_contact_height_error_m':height,
            'method':'Typed player intent, actual release and source/core integration until real impact; no teleports after spawn, injected damage or fabricated events. Prediction is read immediately before the same-tick release.'})
        assert maximum<=.1 and height<=.1,(maximum,height)
    finally:g.close()


if __name__=='__main__':main()
