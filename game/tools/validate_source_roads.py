"""Core-only shared road/deck and hydrology checks against saved source geometry."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from shapely import from_wkb,contains_xy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json
from bvr_game.scene_runtime import BakedScene


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    from bvr_sim.bvr_env_cpp import bvr_sim_cpp as n
    scene=BakedScene(a.map);doc=scene.document;terrain=scene.terrain(n);rng=np.random.default_rng(227);samples=[];checks=[]
    road_ids={r['id']+'_surface' for r in doc['roads']}|{'original_bridge_deck'}
    for surface in doc['environment']['contact_surfaces']:
        if surface['id'] not in road_ids:continue
        vertices=np.asarray(surface['vertices']);triangles=vertices[np.asarray(surface['indices']).reshape(-1,3)]
        selected=triangles[rng.choice(len(triangles),min(400,len(triangles)),replace=False)];weights=rng.uniform(.1,1,(len(selected),3));weights/=weights.sum(axis=1,keepdims=True)
        points=(selected*weights[...,None]).sum(axis=1);error=[];wet=0
        for point in points:
            contact=terrain.contact(float(point[0]),float(point[1]),0.,float(point[2]),.005)
            error.append(abs(contact.height-point[2]));wet+=contact.water
        assert max(error)<1e-6,(surface['id'],max(error))
        assert wet==0,(surface['id'],wet)
        checks.append({'surface':surface['id'],'samples':len(points),'maximum_core_plane_error_m':max(error),'water_contacts':wet});samples.extend(points.tolist())
    bridge=next(x for x in doc['environment']['contact_surfaces'] if x['id']=='original_bridge_deck');v=np.asarray(bridge['vertices'])[np.asarray(bridge['indices']).reshape(-1,3)];p=v.mean(axis=1)
    water=from_wkb((a.map.parent/'water-footprint.wkb').read_bytes());over_water=contains_xy(water,p[:,0],p[:,1]);under=[]
    for point in p[over_water]:
        contact=terrain.contact(float(point[0]),float(point[1]),0.,0.)
        assert contact.water,'Bridge must not erase hydrology below its deck';under.append([*point,contact.height])
    assert len(under)>0
    a.output.mkdir(parents=True,exist_ok=False);np.savez_compressed(a.output/'shared-road-samples.npz',points=np.asarray(samples),bridge_under_water=np.asarray(under))
    core=n.SimCore(.02,str(a.output/'core.log'),'',False)
    try:
        core.reset_world(227);core.set_environment(terrain)
        spec=n.AircraftSpawnSpec();spec.uid='own';spec.model='F16';spec.team='blue';spec.position=[-4000,-3000,2200];spec.velocity=[220,0,0];spec.loadout={};core.spawn_aircraft(spec)
        for _ in range(20):core.step()
        assert next(x for x in core.objects() if x.uid=='own').alive
    finally:core.close()
    write_json(a.output/'report.json',{'status':'passed','map_sha256':sha(a.map),'core_sha256':sha(n.__file__),'checks':checks,'bridge_under_water_samples':len(under),
        'game_session_constructed':False,'renderer_constructed':False,'direct_core_flight_ticks':20,'scope':'Saved road/bridge planes versus typed core contact at bounded barycentric samples. Preserves water below bridge. No rail/pier volume collider,full vehicle-driving or full collision certification.'})
    print('CORE_SOURCE_ROADS_PASSED',sum(x['samples'] for x in checks),len(under),flush=True)
if __name__=='__main__':main()
