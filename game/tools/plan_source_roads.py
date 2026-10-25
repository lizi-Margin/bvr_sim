"""Save terrain-cost dry-road routes and shared forest corridor policy offline."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from shapely import from_wkb
from shapely.geometry import LineString,box
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.road_authoring import DryRoadPlanner


def soften(points):
    p=np.asarray(points,dtype=float)
    for _ in range(2):
        q=.75*p[:-1]+.25*p[1:];r=.25*p[:-1]+.75*p[1:]
        p=np.vstack([p[0],np.stack([q,r],axis=1).reshape(-1,2),p[-1]])
    return np.asarray(LineString(p).simplify(1).coords)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--road-materials',type=Path,required=True,help='Pinned road_asphalt/road_dirt/road_shoulder PBR declarations')
    p.add_argument('--bridge-asset',default='WT-MoskvoretskyBridge-v224');p.add_argument('--bridge-deck',type=Path,required=True);a=p.parse_args()
    scene=BakedScene(a.source);water=from_wkb((a.source.parent/'water-footprint.wkb').read_bytes());planner=DryRoadPlanner(scene,water)
    specs=[('arterial_west',14,40,[[-40000,-12000],[-10000,-1300],[-5500,200],[-2500,300],[-1400,300],[-300,300]]),
        ('arterial_east',14,40,[[200,300],[2400,300],[6000,1000],[10000,2000],[25000,6000],[40000,13000]]),
        ('west_collector',12,38,[[-22000,22000],[-10000,-2800],[-2500,-1000],[-1400,300],[-2300,4000],[-3500,4400]]),
        ('east_collector',12,38,[[1400,-10000],[2200,-8000],[2600,-5000],[2200,-2000],[2400,300],[2200,3000],[1000,6500],[500,10000]]),
        ('west_trail',5,25,[[-2500,-1000],[-5000,800],[-6500,1200],[-7200,3000]]),
        ('east_trail',5,25,[[2400,300],[4000,2500],[6500,3500],[9000,4500]])]
    roads=[]
    for name,width,clearance,waypoints in specs:
        points=[]
        for start,end in zip(waypoints,waypoints[1:]):points.extend(planner.route(start,end)[:-1])
        points.append(waypoints[-1]);smoothed=soften(points);line=LineString(smoothed)
        if line.buffer(width/2+3).intersects(water):
            line=LineString(points)
            if line.buffer(width/2+3).intersects(water):raise ValueError('Dry route crosses original water: '+name)
        roads.append({'id':name,'points':[list(p) for p in line.coords],'width_m':width,'shoulder_m':3 if width>5 else 1,
            'material':'road_asphalt' if width>5 else 'road_dirt','forest_clearance_m':clearance})
        print('DRY_ROAD_PLANNED',name,round(line.length),len(line.coords),flush=True)
    # Only this short surveyed channel crossing is deliberately bridged.
    crossing=LineString([[-300,300],[200,300]]);wet=crossing.intersection(water)
    if wet.is_empty:raise ValueError('Expected bridge channel crossing missing')
    center_n=(wet.bounds[0]+wet.bounds[2])/2
    roads.append({'id':'bridge_link','points':[[-300,300],[200,300]],'width_m':14,'shoulder_m':3,'material':'road_asphalt','forest_clearance_m':40})
    policy={'kind':'authored_reference_woodland','seed':189,'clearing_cell_m':700,'clearing_radius_m':[75,145],'shore_root_clearance_m':3.,'roads':roads,
        'bridge':{'id':'river_bridge','model':a.bridge_asset,'center_nwu':[center_n,300],'scale':.5,'source_deck':str(a.bridge_deck.resolve())},
        'road_materials':json.loads(a.road_materials.read_text()),'road_material_policy_sha256':sha(a.road_materials),
        'source_map_sha256':sha(a.source),'planner_sha256':sha(__file__),'road_helper_sha256':sha(ROOT/'bvr_game/road_authoring.py'),
        'scope':'Authored world-space roads planned against original terrain/water;one explicit original-source bridge. Forest/corridors are authored,not reconstructed original Smolensk land use or a ground-driving certification.'}
    policy['bridge']['source_deck_sha256']=sha(policy['bridge']['source_deck']);write_json(a.output,policy)
    print('SOURCE_ROAD_POLICY_SAVED',a.output,flush=True)
if __name__=='__main__':main()
