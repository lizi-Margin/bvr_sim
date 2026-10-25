"""Offline correction of distant water/terrain intersections; core terrain is unchanged."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import native
from bvr_game.scene_runtime import BakedScene
from bvr_game.content import sha,write_json
from bvr_game.water_surface import conform_outer_water
from bvr_game.worldgen import canonical

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--clearance-m',type=float,default=.25);a=parser.parse_args()
    source=BakedScene(a.source);terrain=source.terrain(native);doc=copy.deepcopy(source.document)
    meta=doc['terrain'];focus=meta['details'][0]
    bounds=(focus['origin_north'],focus['origin_west'],focus['origin_north']+(focus['columns']-1)*focus['spacing'],
        focus['origin_west']+(focus['rows']-1)*focus['spacing'])
    rows=[];surfaces=[]
    for surface in doc['surfaces']:
        if surface['material']!='water':surfaces.append(surface);continue
        result=conform_outer_water(surface,meta['base'],terrain.height,bounds,a.clearance_m);surfaces.append(result)
        if not result.get('outer_core_plane_conform'):continue
        vertices=np.asarray(result['vertices']);triangles=vertices[np.asarray(result['indices']).reshape(-1,3)]
        gaps=[]
        for weights in ([1/3]*3,[.1,.2,.7],[.2,.7,.1],[.7,.1,.2]):
            points=np.einsum('j,ijk->ik',weights,triangles)
            gaps.extend(p[2]-terrain.height(float(p[0]),float(p[1])) for p in points)
        if min(gaps)<=.024:raise ValueError('Corrected distant water still intersects the shared terrain')
        rows.append({'id':result['id'],'triangles':len(triangles),'minimum_interior_gap_m':float(min(gaps)),
            'maximum_interior_gap_m':float(max(gaps)),'footprint_area_m2':result['source_footprint_area_m2']})
    if not rows:raise ValueError('No distant water tiles need conformance')
    a.output.mkdir(parents=True,exist_ok=False);doc['surfaces']=surfaces;doc['name']+='_outer_water_planes'
    shutil.copy2(source.height_file,a.output/source.height_file.name);meta['file']=source.height_file.name
    if meta.get('ground_atlas'):meta['ground_atlas']['file']=str((a.source.parent/meta['ground_atlas']['file']).resolve())
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text(encoding='utf8'));recipe['name']=doc['name']
    recipe['landscape'].update(outer_water_core_plane_conform=True,outer_water_clearance_m=a.clearance_m)
    provenance={'tool':'game/tools/repair_outer_water.py','tool_sha256':sha(__file__),
        'source_map':str(a.source.resolve()),'source_map_sha256':sha(a.source),'clearance_m':a.clearance_m,
        'method':'Clip distant water to each actual indexed base terrain triangle. Retain the existing ground-following outer river approximation.',
        'scope':'Water rendering geometry only. Regional level water, water footprint, all terrain, obstacles, vegetation and missions unchanged.'}
    recipe['offline_water_surface_variant']=provenance;doc['offline_water_surface_variant']=provenance
    doc['recipe_sha256']=hashlib.sha256(canonical(recipe)).hexdigest()
    for key in ('instances','environment','mission','roads','rivers','airfields','settlements','zones','chunks','resource_versions'):
        assert doc[key]==source.document[key],key
    assert sha(a.output/source.height_file.name)==meta['sha256']
    write_json(a.output/'scene-recipe.json',recipe);write_json(a.output/'generated-map.json',doc)
    write_json(a.output/'water-repair-report.json',{'map_sha256':sha(a.output/'generated-map.json'),
        'terrain_sha256':meta['sha256'],'core_sha256':sha(native.__file__),
        'core_environment_mission_instances_equal':True,'corrected_far_tiles':len(rows),'tiles':rows,
        'scope':'Typed terrain/triangle-interior verification only; pending actual render review.'})
    print('WATER_REPAIR_COMPLETE',len(rows),a.output/'generated-map.json',flush=True)

if __name__=='__main__':main()
