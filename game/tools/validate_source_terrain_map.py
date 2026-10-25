"""Headless shared terrain/water/flight verification for source-map candidates."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from shapely import from_wkb,contains_xy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.heightfield import sample_grid


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    from bvr_sim.bvr_env_cpp import bvr_sim_cpp as n
    scene=BakedScene(a.map);terrain=scene.terrain(n);t=scene.document['terrain'];base=t['base']
    points=np.random.default_rng(178).uniform([-63000,-63000],[63000,63000],(12000,2));north,west=points.T
    expected=sample_grid(scene.arrays['base'],base,north,west)
    for meta in t['details']:
        inside=(north>=meta['origin_north'])&(north<=meta['origin_north']+(meta['columns']-1)*meta['spacing'])&(west>=meta['origin_west'])&(west<=meta['origin_west']+(meta['rows']-1)*meta['spacing'])
        expected=np.where(inside,sample_grid(scene.arrays[meta.get('array_key','focus')],meta,north,west),expected)
    actual=np.array([terrain.height(float(x),float(y)) for x,y in points]);error=abs(actual-expected)
    water=from_wkb((a.map.parent/'water-footprint.wkb').read_bytes());wet=contains_xy(water,north,west)
    contacts=[terrain.contact(float(x),float(y),0.) for x,y in points];core_wet=np.array([c.water for c in contacts])
    assert (wet==core_wet).all(),'Core water differs from saved indexed footprint'
    away=abs(actual)>.01;assert (wet[away]==(actual[away]<0)).all(),'Water does not follow shared indexed shore'
    assert np.isfinite(actual).all() and error.max()<1e-6
    np.savez_compressed(a.output/'terrain-water-samples.npz',points=points,core=actual,archive=expected,core_water=core_wet,indexed_water=wet)
    core=n.SimCore(.02,str(a.output/'core.log'),'',False);traces=[]
    try:
        for _ in range(2):
            core.reset_world(178);core.set_environment(terrain)
            spec=n.AircraftSpawnSpec();spec.uid='own';spec.model='F16';spec.team='blue';spec.position=[-4000,-3000,2200];spec.velocity=[220,0,0];spec.loadout={}
            core.spawn_aircraft(spec);trace=[]
            for index in range(20):
                core.step();state=next(o for o in core.objects() if o.uid=='own');trace.append([*state.position,*state.velocity])
                assert state.alive
            traces.append(trace)
        assert traces[0]==traces[1]
    finally:core.close()
    write_json(a.output/'report.json',{'status':'passed','map_sha256':sha(a.map),'core_sha256':sha(n.__file__),'renderer_constructed':False,'game_session_constructed':False,
        'base_shape':[base['rows'],base['columns']],'height_samples':len(points),'maximum_archive_core_error_m':float(error.max()),
        'core_water_mask_mismatches':int((wet!=core_wet).sum()),'wet_samples':int(wet.sum()),'signed_height_range_m':[float(actual.min()),float(actual.max())],
        'deterministic_flight_ticks_per_repeat':20,'deterministic_flight_repeats':2,'trace':traces[0],
        'scope':'Typed core heights/contacts and exact indexed wet footprint;bounded samples and short core-only flight,not full-map collision or art certification.'})
    print('SOURCE_TERRAIN_HEADLESS_PASSED',len(points),float(error.max()),flush=True)
if __name__=='__main__':main()
