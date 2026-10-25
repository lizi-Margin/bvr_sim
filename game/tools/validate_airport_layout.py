"""Compare declared airport render triangles with direct core terrain/contact."""
from pathlib import Path
import argparse,json,sys
import numpy as np
from shapely.geometry import Polygon,Point
from shapely.ops import unary_union
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.scene_runtime import BakedScene
from bvr_game.content import sha,write_json
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    source=BakedScene(a.source);candidate=BakedScene(a.map);d=candidate.document;old=source.document
    for key in source.arrays:np.testing.assert_array_equal(source.arrays[key],candidate.arrays[key],err_msg=key)
    assert np.array_equal(source.ground_atlas,candidate.ground_atlas)
    protected=['mission','fields','roads','rivers','settlements','counts','forest_representation','resource_versions']
    for key in protected:assert old[key]==d[key],key
    assert old['terrain']['sha256']==d['terrain']['sha256'],'Height archive bytes changed'
    for key,value in old['materials'].items():assert value==d['materials'][key],key
    allowed={'airport_hangars','apron_equipment'}
    unaffected=lambda doc:[i for i in doc['instances'] if i.get('zone') not in allowed]
    assert unaffected(old)==unaffected(d),'Non-airport placement changed'
    hangar_ids={i['id'] for i in d['instances'] if i.get('zone')=='airport_hangars'}
    replaced={'runway','taxiway','taxi_link_0','taxi_link_1','taxi_link_2','apron','apron_link','airport_courts','airport_courts_shoulder','airport_courts_guides'}|{'foundation_'+id for id in hangar_ids}
    kept_surfaces=lambda doc:[s for s in doc['surfaces'] if s['id'] not in replaced]
    assert kept_surfaces(old)==kept_surfaces(d),'Non-airport surface changed'
    kept_solids=lambda doc:[o for o in doc['environment']['obstacles'] if o['id'] not in hangar_ids]
    assert kept_solids(old)==kept_solids(d),'Non-airport obstacle changed'
    for key in ['water_regions','decorative_instance_ids']:assert old['environment'][key]==d['environment'][key],key
    changed=[i['id'] for i,j in zip(old['instances'],d['instances']) if i!=j]
    assert len(changed)==18
    surfaces={s['id']:s for s in d['surfaces']};contacts=d['environment']['contact_surfaces']
    for c in contacts:
        s=surfaces[c['id']];assert c['vertices']==s['vertices'] and c['indices']==s['indices'],c['id']
    airport=surfaces['airport_courts'];vertices=np.asarray(airport['vertices']);tris=vertices[np.asarray(airport['indices']).reshape(-1,3)]
    xy=tris[:,:,:2];delta1=xy[:,1]-xy[:,0];delta2=xy[:,2]-xy[:,0]
    areas=(delta1[:,0]*delta2[:,1]-delta1[:,1]*delta2[:,0])/2
    assert np.min(areas)>0,'Invalid airport triangle winding'
    assert abs(float(areas.sum())-airport['plan_area_m2'])<1e-4,'Pavement tessellation lost plan area'
    terrain=candidate.terrain(native);terrain_only=source.terrain(native)
    rows=[];max_error=0.;buried=0;solid_excluded=0
    for triangle in tris[::max(1,len(tris)//6000)]:
        q=triangle.mean(axis=0);n,w,z=map(float,q);ground=terrain.height(n,w)
        assert abs(z-ground-airport['collision_height_offset'])<1e-5,'Airport triangle bridges a core terrain crease'
        collision=terrain.collision_height(n,w)
        if collision>z+.1:solid_excluded+=1;continue
        hit=terrain.contact(n,w);error=max(abs(hit.height-z),abs(collision-z));max_error=max(max_error,error)
        if z<ground-1e-6:buried+=1
        rows.append({'north':n,'west':w,'render_mesh_height':z,'core_contact':hit.height,'core_collision':collision,'terrain':ground,'error_m':error})
    assert len(rows)>1000 and buried==0 and max_error<=.1,(len(rows),buried,max_error)
    # Removed rectangular pavement must disappear from physics as well. Pick
    # actual grass gaps using the emitted triangles, not a separate layout mask.
    plan=unary_union([Polygon(t) for t in xy]);assert plan.geom_type=='Polygon','Airport network disconnected'
    grass=[];airfield=d['airfields'][0];n0,w0=airfield['apron'];hn,hw=np.asarray(airfield['apron_size_m'])/2
    for n in np.arange(n0-hn+7,n0+hn,29):
        for w in np.arange(w0-hw+7,w0+hw,23):
            if plan.distance(Point(n,w))<1.:continue
            ground=terrain.height(n,w)
            if terrain.collision_height(n,w)>ground+.1:continue
            hit=terrain.contact(n,w)
            if hit.supported:continue # preserved building foundations
            assert abs(terrain.collision_height(n,w)-ground)<1e-6,'Invisible former apron contact'
            grass.append([float(n),float(w),ground,terrain_only.collision_height(n,w)])
    assert len(grass)>100,len(grass)
    # The same oriented boxes move with each rendered source warehouse.
    boxes={o['id']:o for o in d['environment']['obstacles']}
    for item in d['instances']:
        if item.get('zone')!='airport_hangars':continue
        solid=boxes[item['id']];assert solid['yaw']==item['yaw']
        assert abs(terrain.collision_height(*solid['center'][:2])-solid['center'][2]-solid['half_size'][2])<1e-5
    write_json(a.output,{'status':'passed','source_map':str(a.source),'source_map_sha256':sha(a.source),'map':str(a.map),'map_sha256':sha(a.map),
        'core_sha256':sha(Path(native.__file__)),'complete_height_arrays_and_atlas_exact':True,'protected_document_keys':protected,
        'non_airport_instances_surfaces_solids_materials_water_exact':True,'non_airport_instances_exact':True,'changed_instances':changed,'all_contact_triangles_equal_render_triangles':True,
        'airport_paved_plan_area_m2':airport['plan_area_m2'],'airport_vertices':len(vertices),'airport_triangles':len(tris),
        'connected_pavement_network':True,'maximum_core_render_contact_error_m':max_error,'samples_excluding_building_solids':rows,
        'building_solid_samples_excluded':solid_excluded,'buried_samples':buried,'former_apron_grass_samples':grass,
        'scope':'Direct typed Terrain without GameSession/rendering. Render mesh data compared with core contacts; actual GPU image/flight validation is separate.'})
    print('AIRPORT_CORE_CONTACT_PASSED',len(rows),'grass',len(grass),'maximum_error_m',max_error,flush=True)


if __name__=='__main__':main()
