"""Extend saved source groves beyond the central planting rectangle, offline."""
from pathlib import Path
import argparse,copy,json,math,shutil,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.worldgen import Baker
from bvr_game.heightfield import sample_grid
from bvr_game.ground_atlas import write_atlas
from bvr_game.grove_grounding import conform_grove
from bvr_game.source_tree_layout import spatial_batches,forbidden_geometry
from bvr_game.woodland_extension import extension_points


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--outer-half-m',type=float,default=40000)
    p.add_argument('--seed',type=int,default=155)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    source=BakedScene(a.source);doc=copy.deepcopy(source.document)
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text());baker=Baker(recipe)
    asset='WT-OakMediumGrove64-v91';manifest=baker.metadata[asset]
    assert doc['resource_versions'][asset]['manifest_sha256']==sha(ASSETS/'registered'/asset/'manifest.json')
    inner=9800.;spacing=12.;jitter=3.8;minimum=spacing-2*jitter;batch_extent=500.
    if minimum<float(manifest['conversion_recipe']['policy']['cluster']['inter_grove_stem_spacing_m']):raise ValueError('Authored cell jitter violates source stem spacing')
    assert all(np.max(np.abs(i['ground_stems']))<=inner for i in doc['instances'] if 'ground_stems' in i),'Source forest exceeds the preserved inner domain'
    half=a.outer_half_m
    doc['zones'].append({'id':'far_woodland_domain','type':'forest','polygon':[[-half,-half],[half,-half],[half,half],[-half,half]],
                         'holes':[[[-inner,-inner],[-inner,inner],[inner,inner],[inner,-inner]]]})
    radius=max(math.hypot(x,y) for b in manifest['cluster']['ground_conform']['tree_bounds_relative_blender'] for x in [b['min'][0],b['max'][0]] for y in [b['min'][1],b['max'][1]])*1.35
    # Existing decorative trees remain verbatim. Only solid/ordinary source
    # occupancy contributes forbidden footprints; old groves lie inside inner.
    for item in doc['instances']:
        if 'ground_stems' in item:continue
        n,w=item['position'][:2];baker.occupied.setdefault((math.floor(n/50),math.floor(w/50)),[]).append((n,w,item['radius_m']))
    blocked=forbidden_geometry(baker).buffer(radius+.15)
    points=extension_points(blocked,inner_half_m=inner,outer_half_m=a.outer_half_m,spacing_m=spacing,jitter_m=jitter,seed=a.seed)
    count=len(manifest['cluster']['poses_before_recentering']);discarded=len(points)%count
    points=points[:len(points)-discarded] if discarded else points
    np.save(out/'authored-far-tree-points.npy',points,allow_pickle=False)
    print('EXTENSION_POINTS',len(points),flush=True)
    class SharedHeight:
        def height_many(self,n,w):
            n,w=np.broadcast_arrays(n,w);t=doc['terrain'];h=sample_grid(source.arrays['base'],t['base'],n,w)
            for meta in sorted(t['details'],key=lambda x:x['spacing'],reverse=True):
                inside=(n>=meta['origin_north'])&(n<=meta['origin_north']+(meta['columns']-1)*meta['spacing'])&(w>=meta['origin_west'])&(w<=meta['origin_west']+(meta['rows']-1)*meta['spacing'])
                h=np.where(inside,sample_grid(source.arrays[meta.get('array_key','focus')],meta,n,w),h)
            return h
        def height(self,n,w):return float(self.height_many(n,w))
    heights=SharedHeight();rng=np.random.default_rng(a.seed+1);added=[]
    for index,positions in enumerate(spatial_batches(points,count,max_extent_m=batch_extent)):
        positions=positions[rng.permutation(len(positions))];n,w=positions.mean(axis=0);scale=float(rng.uniform(1,1.35));yaw=float(rng.uniform(-math.pi,math.pi))
        fit=conform_grove(manifest,float(n),float(w),yaw,scale,heights.height,sample_heights=heights.height_many,ground_stems=positions)
        extent=float(np.linalg.norm(positions-[n,w],axis=1).max())+radius
        added.append({'id':f'far_woodland_{index:06d}','model':asset,'position':[float(n),float(w),heights.height(n,w)],'yaw':yaw,'scale':scale,
            'category':'vegetation','zone':'far_woodland','chunk':f'{math.floor(n/recipe["chunk_m"])}:{math.floor(w/recipe["chunk_m"])}',
            'lod_distance':1400.,'cull_distance':100000.,'collision_type':'decorative vegetation','radius_m':extent,'up_normal':[0,1,0],
            'ground_stems':positions.tolist(),'stem_clearance_radius_m':radius,'grove_ground_conform':fit,
            'independent_source_layout':{'source_trees':len(positions),'source_slots':count,'minimum_stem_m':minimum,'placement_seed':a.seed,
                'maximum_axis_extent_m':batch_extent,'forest_zones':['far_woodland_domain'],'spatial_batch':'Jittered world-cell points,spatially partitioned; fixed offline density,not runtime LOD.'}})
        if index%4096==0:print('EXTENSION_GROUPS',index,flush=True)
    doc['instances'].extend(added);doc['chunks']={}
    for item in doc['instances']:doc['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    doc['counts']={k:sum(i['category']==k for i in doc['instances']) for k in ['vegetation','building','prop']}
    doc['budgets']['vegetation_instances']=max(doc['budgets']['vegetation_instances'],doc['counts']['vegetation'])
    doc['environment']['decorative_instance_ids']=[i['id'] for i in doc['instances'] if i['category']!='building']
    shutil.copy2(source.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    step=min(t['spacing'] for t in doc['terrain']['details']);half=math.ceil(a.outer_half_m/step)*step
    grid={'origin_north':-half,'origin_west':-half,'spacing':step,'columns':round(2*half/step)+1,'rows':round(2*half/step)+1}
    print('EXTENSION_ATLAS',grid,flush=True)
    atlas=write_atlas(out,source.arrays,doc['terrain'],grid)
    # The enlarged atlas must preserve every previously rendered source node.
    data=np.memmap(atlas['file'],dtype='<f4',mode='r',shape=(grid['rows'],grid['columns']))
    old=doc['terrain']['ground_atlas'];x=round((old['origin_north']+half)/step);y=round((old['origin_west']+half)/step)
    assert np.array_equal(data[y:y+old['rows'],x:x+old['columns']],source.ground_atlas)
    doc['terrain']['ground_atlas']=atlas
    for key in ['surfaces','mission','roads','rivers','airfields','settlements']:assert doc[key]==source.document[key],key
    for key in ['contact_surfaces','obstacles','water_regions']:assert doc['environment'][key]==source.document['environment'][key],key
    assert doc['instances'][:len(source.document['instances'])]==source.document['instances']
    doc['reference_quality'].update(stage='extended_source_woodland_candidate',source_tree_count=sum(len(i.get('ground_stems',[])) for i in doc['instances']),
        forest_area_scope='Central dense polygon only;far authored scattering is recorded separately in woodland_extension')
    doc['forest_representation'].update(independently_grounded_groves=sum('ground_stems' in i for i in doc['instances']),
        independently_grounded_source_trees=doc['reference_quality']['source_tree_count'],
        maximum_batch_axis_extent_m=max(float(np.ptp(i['ground_stems'],axis=0).max()) for i in doc['instances'] if 'ground_stems' in i),
        maximum_batch_radius_m=max(i['radius_m'] for i in doc['instances'] if 'ground_stems' in i))
    doc['woodland_extension']={'policy_version':2,'source_map':str(a.source.resolve()),'source_sha256':sha(a.source),'tool_sha256':sha(__file__),
        'helper_sha256':sha(ROOT/'bvr_game/woodland_extension.py'),'seed':a.seed,'inner_half_m':inner,'outer_half_m':half,
        'spacing_m':spacing,'jitter_m':jitter,'minimum_stem_m':minimum,'batch_extent_m':batch_extent,'added_source_trees':len(points),'added_groups':len(added),
        'discarded_unfilled_slots':discarded,'previous_atlas_nodes_byte_equal':True,'source_height_sha256':doc['terrain']['sha256'],
        'scope':'Authored fixed scenery on shared terrain. No camera-distance disappearance,terrain grading,physics or mission edit; requires actual render review.'}
    write_json(out/'generated-map.json',doc);write_json(out/'scene-recipe.json',recipe)
    BakedScene(out/'generated-map.json')
    from bvr_game.mapcheck import validate
    print('EXTENSION_VALIDATE_SPATIAL',flush=True)
    validation=validate(out/'generated-map.json');write_json(out/'spatial-validation.json',validation)
    if validation['status']!='passed':raise ValueError('Extended woodland failed spatial validation; candidate retained for inspection')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'extension':doc['woodland_extension'],'status':'requires_actual_render_review'})
    print('EXTENSION_BUILT',out/'generated-map.json',flush=True)
if __name__=='__main__':main()
