"""Offline retained-mask planting on an already baked typed source map."""
from pathlib import Path
import argparse,copy,json,math,shutil,sys
import numpy as np
from shapely import from_wkb,union_all,contains_xy
from shapely.geometry import Polygon,Point
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json,registered_version
from bvr_game.scene_runtime import BakedScene
from bvr_game.source_woodland import source_plant_layers,planting_density,protected_footprints
from bvr_game.source_tree_layout import spatial_batches
from bvr_game.heightfield import sample_grid
from bvr_game.ground_atlas import write_atlas
from bvr_game.grove_grounding import conform_grove
from bvr_game.authored_canopy import woodland_mask,validate_policy


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--landclasses',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--half-m',type=int,default=40000);p.add_argument('--seed',type=int,default=176)
    p.add_argument('--positions-from',type=Path,help='Reuse a saved authored candidate point pool;recheck source masks,bounds,water and full airport footprints')
    p.add_argument('--large-asset',help='Optional registered source grove for mature-tree mixture')
    p.add_argument('--medium-asset',default='WT-OakMediumGrove64-v91',help='Registered medium grove; use source-native-normal derivative for that resource family')
    p.add_argument('--large-fraction',type=float,default=.65)
    p.add_argument('--authored-biome',type=Path,help='Optional explicit authored woodland openings instead of original source density masks')
    p.add_argument('--grid-spacing-m',type=float,default=8.)
    p.add_argument('--jitter-m',type=float,default=2.5)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    scene=BakedScene(a.source);doc=copy.deepcopy(scene.document);report=json.loads(a.landclasses.read_text(encoding='utf8'))
    policy=json.loads(a.authored_biome.read_text(encoding='utf8')) if a.authored_biome else None
    if policy:validate_policy(policy)
    if policy and policy.get('roads') and doc.get('source_road_bake',{}).get('policy_sha256')!=sha(a.authored_biome):raise ValueError('Canopy biome requires the matching saved road plan')
    layers=[] if policy else source_plant_layers(report)
    if any('ground_stems' in item for item in doc['instances']):raise ValueError('Population source must not already contain source-tree batches')
    asset=a.medium_asset;ids=[asset]+([a.large_asset] if a.large_asset else [])
    manifests={id:json.loads((ASSETS/'registered'/id/'manifest.json').read_text(encoding='utf8')) for id in ids}
    if not 0<=a.large_fraction<=1 or len({len(m['cluster']['poses_before_recentering']) for m in manifests.values()})!=1:raise ValueError('Invalid source grove mixture')
    manifest=manifests[asset]
    radius=max(math.hypot(x,y) for m in manifests.values() for b in m['cluster']['ground_conform']['tree_bounds_relative_blender'] for x in [b['min'][0],b['max'][0]] for y in [b['min'][1],b['max'][1]])*1.35
    forbidden=protected_footprints(doc,from_wkb((a.source.parent/'water-footprint.wkb').read_bytes()),radius,shore_root_clearance_m=(policy or {}).get('shore_root_clearance_m'),road_root_clearance_m=(policy or {}).get('road_root_clearance_m'))
    class Heights:
        def many(self,n,w):
            n,w=np.broadcast_arrays(n,w);t=doc['terrain'];result=sample_grid(scene.arrays['base'],t['base'],n,w)
            for meta in t['details']:
                inside=(n>=meta['origin_north'])&(n<=meta['origin_north']+(meta['columns']-1)*meta['spacing'])&(w>=meta['origin_west'])&(w<=meta['origin_west']+(meta['rows']-1)*meta['spacing'])
                result=np.where(inside,sample_grid(scene.arrays[meta.get('array_key','focus')],meta,n,w),result)
            return result
        def one(self,n,w):return float(self.many(n,w))
    heights=Heights();rng=np.random.default_rng(a.seed);spacing=a.grid_spacing_m;jitter=a.jitter_m;half=a.half_m
    if not 3<=spacing<=40 or not 0<=jitter or spacing-2*jitter<3:raise ValueError('Invalid authored stem spacing/jitter')
    if not 1000<=half<=40000 or half%5:raise ValueError('Source planting half-extent must align to5m and fit the native atlas')
    axis=(np.arange(math.floor(-half/spacing),math.ceil(half/spacing))+.5)*spacing;accepted=[];saturated=0
    for first in ([] if a.positions_from else range(0,len(axis),64)):
        n,w=np.meshgrid(axis,axis[first:first+64]);points=np.column_stack([n.ravel(),w.ravel()]);points+=rng.uniform(-jitter,jitter,points.shape)
        n,w=points.T;density=woodland_mask(n,w,policy).astype(float) if policy else planting_density(layers,n,w)*spacing*spacing/100;saturated+=int((density>1).sum())
        points=points[rng.random(len(points))<np.minimum(density,1)]
        if len(points):points=points[~contains_xy(forbidden,points[:,0],points[:,1])]
        if len(points):points=points[heights.many(points[:,0],points[:,1])>1]
        accepted.append(points)
        if first%512==0:print('SOURCE_PLANT_ROWS',first,'/',len(axis),'accepted',sum(len(x) for x in accepted),flush=True)
    if a.positions_from:
        points=np.load(a.positions_from,allow_pickle=False)
        if points.ndim!=2 or points.shape[1]!=2 or not np.isfinite(points).all() or np.max(abs(points))>=half:raise ValueError('Invalid authored source point pool')
        support=woodland_mask(points[:,0],points[:,1],policy) if policy else planting_density(layers,points[:,0],points[:,1])>0
        if not support.all():raise ValueError('Point pool leaves declared planting support')
        points=points[~contains_xy(forbidden,points[:,0],points[:,1])];points=points[heights.many(points[:,0],points[:,1])>1]
        saturated=None
    else:points=np.concatenate(accepted)
    count=len(manifest['cluster']['poses_before_recentering']);discarded=len(points)%count
    if discarded:points=points[:-discarded]
    np.save(out/'authored-source-mask-points.npy',points,allow_pickle=False);print('SOURCE_PLANT_POINTS',len(points),flush=True)
    additions=[];landclass_sha=sha(a.landclasses)
    for index,positions in enumerate(spatial_batches(points,count,max_extent_m=500)):
        model=a.large_asset if a.large_asset and rng.random()<a.large_fraction else asset
        positions=positions[rng.permutation(len(positions))];n,w=positions.mean(axis=0);scale=float(rng.uniform(.8,1.1) if model==a.large_asset else rng.uniform(1,1.35));yaw=float(rng.uniform(-math.pi,math.pi));extent=float(np.linalg.norm(positions-[n,w],axis=1).max())+radius
        fit=conform_grove(manifests[model],float(n),float(w),yaw,scale,heights.one,sample_heights=heights.many,ground_stems=positions)
        additions.append({'id':f'source_canopy_{index:06d}','model':model,'category':'vegetation','zone':'source_mask_canopy','position':[float(n),float(w),fit['height']],
            'yaw':yaw,'scale':scale,'chunk':f'{math.floor(n/doc["chunk_m"])}:{math.floor(w/doc["chunk_m"])}','lod_distance':1400.,'cull_distance':100000.,'radius_m':extent,
            'collision_type':'decorative vegetation','up_normal':[0,1,0],'ground_stems':positions.tolist(),'grove_ground_conform':fit,'stem_clearance_radius_m':radius,
            'independent_source_layout':{'source_trees':len(positions),'source_slots':count,'minimum_stem_m':spacing-2*jitter,'maximum_axis_extent_m':500.,
                'source_landclass_report_sha256':landclass_sha,'placement_seed':a.seed,'scope':'Authored continuous woodland/openings and cell RNG;original highest source-tree geometry.' if policy else 'Original global/local masks and summed plant density;authored jitter/geometry substitution,not exact original RNG or species reconstruction.'}})
        if index%8192==0:print('SOURCE_PLANT_GROUPS',index,flush=True)
    doc['instances'].extend(additions);doc['chunks']={}
    for item in doc['instances']:doc['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    doc['counts']={k:sum(i['category']==k for i in doc['instances']) for k in ['vegetation','building','prop']}
    doc['budgets']['vegetation_instances']=max(doc['budgets']['vegetation_instances'],len(additions))
    doc['environment']['decorative_instance_ids']=[i['id'] for i in doc['instances'] if i['category']!='building']
    for id,m in manifests.items():
        version=registered_version(id,m);version['manifest_sha256']=sha(ASSETS/'registered'/id/'manifest.json');doc['resource_versions'][id]=version
    shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    grid={'origin_north':-half,'origin_west':-half,'spacing':5,'columns':2*half//5+1,'rows':2*half//5+1}
    print('SOURCE_PLANT_ATLAS',grid,flush=True);doc['terrain']['ground_atlas']=write_atlas(out,scene.arrays,doc['terrain'],grid)
    for key in ['surfaces','mission','roads','rivers','airfields','settlements']:assert doc[key]==scene.document[key],key
    for key in ['contact_surfaces','obstacles','water_regions']:assert doc['environment'][key]==scene.document['environment'][key],key
    doc['source_woodland_bake']={'source_map_sha256':sha(a.source),'source_landclass_report_sha256':sha(a.landclasses),'tool_sha256':sha(__file__),
        'helper_sha256':sha(ROOT/'bvr_game/source_woodland.py'),'points_sha256':sha(out/'authored-source-mask-points.npy'),'trees':len(points),'batches':len(additions),
        'half_m':half,'spacing_m':spacing,'jitter_m':jitter,'seed':a.seed,'density_saturated_candidate_cells':saturated,'discarded_incomplete_batch_points':discarded,
        'authored_input_pool':{'file':str(a.positions_from.resolve()),'sha256':sha(a.positions_from)} if a.positions_from else None,
        'source_grove_mix':{id:sum(len(i['ground_stems']) for i in additions if i['model']==id) for id in ids},
        'large_fraction_requested':a.large_fraction if a.large_asset else None,
        'source_layers':[{k:v for k,v in x.items() if k not in ('coverage','density')} for x in layers],
        'authored_biome':{'policy':policy,'file':str(a.authored_biome.resolve()),'sha256':sha(a.authored_biome),'helper_sha256':sha(ROOT/'bvr_game/authored_canopy.py')} if policy else None,
        'scope':'Authored continuous woodland with small irregular clearings,source oak geometry and unchanged source terrain/water;not original Smolensk land use,placement or finished art.' if policy else 'Retained source landclass coverage/local density and summed plant-group densities. Source shrub/tree groups substitute registered medium/mature oak geometry;authored cell RNG,mix and scales. Not exact original species/instance reconstruction or finished art.'}
    write_json(out/'generated-map.json',doc);shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb')
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text(encoding='utf8'));recipe['source_woodland_bake']=doc['source_woodland_bake']
    for id in manifests:recipe['resource_use']['asset_manifest_sha256'][id]=sha(ASSETS/'registered'/id/'manifest.json')
    write_json(out/'scene-recipe.json',recipe);BakedScene(out/'generated-map.json')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'woodland':doc['source_woodland_bake'],'status':'requires_actual_visual_and_grounding_review'})
    print('SOURCE_WOODLAND_BUILT',out/'generated-map.json',flush=True)
if __name__=='__main__':main()
