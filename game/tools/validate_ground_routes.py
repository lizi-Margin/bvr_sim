"""Drive actual typed ground objects on the baked industrial roads and elevated bridge."""
from pathlib import Path
import sys,json,argparse,math
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.ground import spec_from_data
from bvr_game.content import write_json,sha
from shapely.geometry import Point,LineString
MAP=ROOT/'game/maps/training_range_v3/generated-map.json'

def run(out):
    out=Path(out);g=FlightGame(map_path=MAP,output=out/'reports/ground-routes');g.config.mission='training';g.config.enemy_attacks=False;g.start();trace=[]
    try:
        s={'uid':'route_car','kind':'vehicle','model':'WillysJeep','team':'blue','mission_target':False,'position':[4000,4300,180],
           'route':{'points':[[4000,4300],[4000,4650],[4310,4650]],'speed':7,'loop':False}}
        industrial_spec=s;g.sim.spawn_ground(spec_from_data(native,s));g.step(200);before=serialize(g.sim.frame())
        g.sim.park_ground('route_car',True);g.step(200);parked=serialize(g.sim.frame());g.step(100);held=serialize(g.sim.frame())
        car=lambda frame:next(x for x in frame['ground_units'] if x['uid']=='route_car')
        assert car(parked)['position']==car(held)['position'] and car(held)['motion']=='parked'
        g.sim.park_ground('route_car',False)
        for _ in range(100):g.step(50);trace.append(serialize(g.sim.frame()))
        assert car(trace[-1])['motion']=='arrived' and math.dist(car(trace[-1])['position'][:2],[4310,4650])<2
        g.start();d=g.baked_scene.document;b=json.loads((ROOT/'game/recipes/training_range_v3.json').read_text())['bridges'][0];road=next(r for r in d['roads'] if r['id']==b['road']);line=LineString(road['points']);station=line.project(Point(b['center']))
        points=[list(line.interpolate(station-b['length_m']/2-10+i*5).coords[0]) for i in range(int((b['length_m']+20)/5)+1)]
        t=g.sim.terrain();p=points[0]
        s={'uid':'bridge_car','kind':'vehicle','model':'WillysJeep','team':'blue','mission_target':False,'position':[*p,t.collision_height(*p)],'route':{'points':points,'speed':5,'loop':False}}
        g.sim.spawn_ground(spec_from_data(native,s));bridge_trace=[]
        for _ in range(140):
            g.step(50);f=serialize(g.sim.frame());v=next(x for x in f['ground_units'] if x['uid']=='bridge_car');bridge_trace.append(v)
            if v['motion']=='arrived':break
        assert bridge_trace[-1]['motion']=='arrived',bridge_trace[-1]
        assert all(not v['blocked_reason'] for v in bridge_trace)
        raised=[v for v in bridge_trace if v['contact_surface']==b['id'] and abs(v['position'][2]-b['deck_height_m'])<.01]
        assert raised and max(v['position'][2]-t.height(*v['position'][:2]) for v in raised)>10
        report={'status':'passed','map_sha256':sha(MAP),'industrial':{'spawn_spec':industrial_spec,'before_parking':before,'parked':parked,'held':held,'resume_trace':trace,'arrived':car(trace[-1])},'bridge':{'spawn_spec':s,'trace':bridge_trace,'raised_deck_samples':len(raised),'riverbed_at_center_m':t.height(*b['center']),'deck_height_m':b['deck_height_m']},'determinism':'Core deterministic route/reset covered by native and Python tests; render/headless mission frame parity separately reported.'}
        write_json(out/'ground-vehicle-report.json',report);return {'status':'passed','bridge_samples':len(bridge_trace),'raised_deck_samples':len(raised),'industrial_arrived':car(trace[-1])['position']}
    finally:g.close()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);print(json.dumps(run(p.parse_args().output),indent=2))
