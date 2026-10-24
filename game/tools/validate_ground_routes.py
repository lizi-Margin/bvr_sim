"""Drive actual typed ground objects on the baked industrial roads and elevated bridge."""
from pathlib import Path
import sys,json,argparse,math
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.ground import spec_from_data
from bvr_game.content import write_json,sha
from shapely.geometry import Point,LineString
from shapely.ops import substring
MAP=ROOT/'game/maps/training_range_v3/generated-map.json'

def run(out,map_path=MAP):
    map_path=Path(map_path).resolve();out=Path(out);g=FlightGame(map_path=map_path,output=out/'reports/ground-routes');g.select_aircraft('F16');g.config.mission='training';g.config.enemy_attacks=False;trace=[]
    def reset():
        # A ground-route test can outlast an unattended aircraft's low spawn.
        # Fly level through the real controller; never bypass terminal physics.
        g.start(start_position=[-20000,0,8500],initial_speed=300)
        g.submit_player(direction=[1,0,0],throttle=.85)
    reset();bridge_trace=[]
    try:
        d=g.baked_scene.document
        # Read this immutable map's own public recipe and routes. Do not test
        # training_range_v3 coordinates and label that as river-valley evidence.
        recipe_file=map_path.parent/'scene-recipe.json'
        if not recipe_file.exists() and d.get('data_version'):recipe_file=map_path.parent/'versions'/d['data_version']/'scene-recipe.json'
        recipe=json.loads(recipe_file.read_text(encoding='utf-8'))
        industrial=next(r for r in d['roads'] if r['id']=='industrial_service')
        route_points=industrial['points'];t=g.sim.terrain();p=route_points[0]
        s={'uid':'route_car','kind':'vehicle','model':'WillysJeep','team':'blue','mission_target':False,'position':[*p,t.collision_height(*p)],
           'route':{'points':route_points,'speed':7,'loop':False}}
        industrial_spec=s;g.sim.spawn_ground(spec_from_data(native,s));g.step(200);before=serialize(g.sim.frame())
        g.sim.park_ground('route_car',True);g.step(200);parked=serialize(g.sim.frame());g.step(100);held=serialize(g.sim.frame())
        car=lambda frame:next(x for x in frame['ground_units'] if x['uid']=='route_car')
        assert car(parked)['position']==car(held)['position'] and car(held)['motion']=='parked'
        g.sim.park_ground('route_car',False)
        for _ in range(math.ceil(LineString(route_points).length/7)+30):
            g.step(50);trace.append(serialize(g.sim.frame()))
            assert trace[-1]['result']=='running',('Ground test aircraft terminated',trace[-1]['result'],trace[-1]['tick'])
            if car(trace[-1])['motion']=='arrived':break
        assert car(trace[-1])['motion']=='arrived' and math.dist(car(trace[-1])['position'][:2],route_points[-1])<2,car(trace[-1])
        reset();b=recipe['bridges'][0];road=next(r for r in d['roads'] if r['id']==b['road']);line=LineString(road['points']);station=line.project(Point(b['center']))
        # Keep actual road corners, rather than commanding a braking waypoint
        # every5m on straight approaches. Mesh sampling is not route semantics.
        points=list(map(list,substring(line,station-b['length_m']/2-10,station+b['length_m']/2+10).coords))
        t=g.sim.terrain();p=points[0]
        s={'uid':'bridge_car','kind':'vehicle','model':'WillysJeep','team':'blue','mission_target':False,'position':[*p,t.collision_height(*p)],'route':{'points':points,'speed':5,'loop':False}}
        g.sim.spawn_ground(spec_from_data(native,s));bridge_trace=[]
        for _ in range(math.ceil((b['length_m']+20)/5)+30):
            g.step(50);f=serialize(g.sim.frame());v=next(x for x in f['ground_units'] if x['uid']=='bridge_car');bridge_trace.append(v)
            assert f['result']=='running',('Ground test aircraft terminated',f['result'],f['tick'])
            if v['motion']=='arrived':break
        assert bridge_trace[-1]['motion']=='arrived',bridge_trace[-1]
        assert all(not v['blocked_reason'] for v in bridge_trace)
        raised=[v for v in bridge_trace if v['contact_surface']==b['id'] and abs(v['position'][2]-b['deck_height_m'])<.01]
        assert raised and max(v['position'][2]-t.height(*v['position'][:2]) for v in raised)>10
        report={'status':'passed','map':str(map_path),'map_sha256':sha(map_path),'recipe_sha256':sha(recipe_file),'industrial':{'spawn_spec':industrial_spec,'before_parking':before,'parked':parked,'held':held,'resume_trace':trace,'arrived':car(trace[-1])},'bridge':{'spawn_spec':s,'trace':bridge_trace,'raised_deck_samples':len(raised),'riverbed_at_center_m':t.height(*b['center']),'deck_height_m':b['deck_height_m']},'determinism':'Core deterministic route/reset covered by native and Python tests; render/headless mission frame parity separately reported.'}
        write_json(out/'ground-vehicle-report.json',report);return {'status':'passed','bridge_samples':len(bridge_trace),'raised_deck_samples':len(raised),'industrial_arrived':car(trace[-1])['position']}
    except Exception as error:
        write_json(out/'ground-vehicle-report.json',{'status':'failed','map':str(map_path),'map_sha256':sha(map_path),
            'error':str(error),'industrial_trace':trace,'bridge_trace':bridge_trace,'last_frame':serialize(g.sim.frame())})
        raise
    finally:g.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--map',type=Path,default=MAP);a=p.parse_args();print(json.dumps(run(a.output,a.map),indent=2))
