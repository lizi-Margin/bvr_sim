"""Independent source-tree locations, spatially batched for shared source meshes."""
import math
import numpy as np
from shapely import contains_xy,distance,points as shape_points
from shapely.geometry import Point,box
from shapely.ops import unary_union


def spatial_batches(points,count,max_extent_m=None):
    """Equal-count KD partitions: every source copy is used exactly once."""
    points=np.asarray(points,dtype=float)
    if points.ndim!=2 or points.shape[1]!=2 or len(points)%count:raise ValueError('Source points must fill complete source batches')
    def partition(values):
        groups=len(values)//count
        if len(values)<=count:
            extent=np.ptp(values,axis=0)
            if max_extent_m is not None and extent.max()>max_extent_m and len(values)>1:
                axis=int(np.argmax(extent));order=np.argsort(values[:,axis]);split=int(np.argmax(np.diff(values[order,axis])))+1
                yield from partition(values[order[:split]]);yield from partition(values[order[split:]])
            else:yield values
            return
        axis=int(np.argmax(np.ptp(values,axis=0)));split=(groups//2)*count
        order=np.argpartition(values[:,axis],split);yield from partition(values[order[:split]]);yield from partition(values[order[split:]])
    yield from partition(points)


def forbidden_geometry(baker):
    def circle(center,radius):
        # A circumscribed polygon cannot admit points inside the declared
        # analytic settlement/footprint circle between tessellation vertices.
        return Point(center).buffer(radius/math.cos(math.pi/256),quad_segs=64)
    blocked=[baker.water,baker.road_exclusion,baker.industry.buffer(100)]
    blocked.extend(p for e,p in baker.exclusions if 'no_vegetation' in e['rules'] or 'no_tall_objects' in e['rules'])
    blocked.extend(circle(s['center'],s['radius_m']) for s in baker.r['settlements'])
    blocked.extend(circle((n,w),radius) for values in baker.occupied.values() for n,w,radius in values)
    return unary_union(blocked)


def edge_density_probability(forest,locations,config,seed):
    """Authored density transition inside unchanged forest/exclusion polygons."""
    from .regional_cover import smooth_noise
    width=float(config['width_m']);variation=float(config['variation_m']);scale=float(config['patch_scale_m'])
    if not all(math.isfinite(v) for v in [width,variation,scale]) or not 0<width<=500 or not 0<=variation<=width or not 20<=scale<=1000:
        raise ValueError('Invalid source-tree edge density dimensions')
    locations=np.asarray(locations);n,w=locations.T
    depth=distance(forest.boundary,shape_points(locations))
    local_width=width*(.5+smooth_noise(n,w,scale,seed+191))
    setback=variation*smooth_noise(n,w,scale*.63,seed+197)
    u=np.clip((depth-setback)/local_width,0,1);smooth=u*u*(3-2*u)
    # Sparse outliers retain a soft fringe rather than moving a hard wall inward.
    return .005+.995*smooth**1.5


def build_rule(baker,rule):
    models=baker.r['asset_roles'][rule['roles']]
    manifests=[baker.metadata[x] for x in models]
    sizes={len(m['cluster']['poses_before_recentering']) for m in manifests}
    if len(sizes)!=1:raise ValueError('Independent source batches must share a source count')
    count=sizes.pop();target=rule['count']*count
    if not hasattr(baker,'source_tree_pending'):
        baker.source_tree_pending=[];baker.source_tree_blocked=forbidden_geometry(baker);baker.source_tree_flushed=False
    if baker.source_tree_flushed:raise ValueError('Independent source forest rules must precede ordinary scatter rules')
    if not hasattr(baker,'grove_stems'):baker.grove_stems={};baker.overlapping_grove_roots=set();baker.maximum_stem_spacing=0.
    minimum=max(float(m['conversion_recipe']['policy']['cluster']['inter_grove_stem_spacing_m']) for m in manifests)
    if not 0<minimum<=10:raise ValueError('Independent source-tree minimum spacing must be0..10m')
    radius=max(math.hypot(x,y) for m in manifests for b in m['cluster']['ground_conform']['tree_bounds_relative_blender'] for x in [b['min'][0],b['max'][0]] for y in [b['min'][1],b['max'][1]])*max(rule['scale_range'])
    forest=unary_union([baker.forests[z] for z in rule['zones']])
    allowed=forest.intersection(box(-9800,-9800,9800,9800)).difference(baker.source_tree_blocked.buffer(radius+.15))
    if allowed.is_empty:raise ValueError('No source-tree area remains after source crown clearance')
    n0,w0,n1,w1=allowed.bounds;seed=baker.rng.getrandbits(64);rng=np.random.default_rng(seed);accepted=[];attempted=0
    search=math.ceil(max(minimum,baker.maximum_stem_spacing)/4);squared=minimum*minimum
    while len(accepted)<target and attempted<target*100:
        batch=min(131072,max(4096,(target-len(accepted))*4));candidates=np.round(rng.uniform([n0,w0],[n1,w1],(batch,2)),4);attempted+=batch
        mask=contains_xy(allowed,candidates[:,0],candidates[:,1]);candidates=candidates[mask]
        if len(candidates) and rule.get('edge_density'):
            probability=edge_density_probability(forest,candidates,rule['edge_density'],baker.r['seed'])
            candidates=candidates[rng.random(len(candidates))<probability]
        if len(candidates):
            n,w=candidates.T;t=baker.terrain
            slope=np.hypot(t.height_many(n+25,w)-t.height_many(n-25,w),t.height_many(n,w+25)-t.height_many(n,w-25))/50
            candidates=candidates[slope<=.65]
        for n,w in candidates:
            i,j=math.floor(n/4),math.floor(w/4);blocked=False
            for a in range(i-search,i+search+1):
                for b in range(j-search,j+search+1):
                    if any((n-x)**2+(w-y)**2<max(squared,spacing*spacing) for x,y,spacing in baker.grove_stems.get((a,b),())):blocked=True;break
                if blocked:break
            if blocked:continue
            n,w=float(n),float(w);accepted.append((n,w));baker.grove_stems.setdefault((i,j),[]).append((n,w,minimum))
            if len(accepted)==target:break
        if attempted//131072!=(attempted-batch)//131072:print('SOURCE_TREE_SAMPLES',rule['id'],len(accepted),target,flush=True)
    if len(accepted)!=target:raise RuntimeError(f'Independent source-tree density not met: {rule["id"]} {len(accepted)}/{target}')
    baker.maximum_stem_spacing=max(minimum,baker.maximum_stem_spacing)
    maximum_radius=0.
    batches=0;inactive=0
    for points in spatial_batches(accepted,count,max_extent_m=float(rule.get('spatial_batch_extent_m',250))):
        points=points[rng.permutation(len(points))];n,w=np.round(points.mean(axis=0),4);model=baker.rng.choice(models);scale=round(baker.rng.uniform(*rule['scale_range']),5);yaw=round(baker.rng.uniform(-math.pi,math.pi),6)
        batches+=1;inactive+=count-len(points)
        h=baker.terrain.height(float(n),float(w));baker.serial+=1
        extent=float(np.max(np.linalg.norm(points-[n,w],axis=1)))+radius;maximum_radius=max(maximum_radius,extent)
        baker.instances.append({'id':f'{rule["id"]}_{baker.serial:05d}','model':model,'position':[float(n),float(w),h],
            'yaw':yaw,'scale':scale,'category':'vegetation','zone':rule['id'],'chunk':f'{math.floor(n/baker.r["chunk_m"])}:{math.floor(w/baker.r["chunk_m"])}',
            'lod_distance':rule['lod_distance_m'],'cull_distance':rule['cull_distance_m'],'collision_type':'decorative vegetation',
            'radius_m':extent,'up_normal':[0,1,0],'ground_stems':points.tolist(),'stem_clearance_radius_m':radius,
            'independent_source_layout':{'source_trees':len(points),'source_slots':count,'minimum_stem_m':minimum,'placement_seed':seed,'forest_zones':rule['zones'],
                'maximum_axis_extent_m':float(rule.get('spatial_batch_extent_m',250)),
                **({'edge_density':rule['edge_density']} if rule.get('edge_density') else {}),
                'spatial_batch':'Equal-count KD partition, split sparse tails at largest gaps; unused source slots collapse to zero-area triangles. Authored positions, not GIS.'}})
    baker.source_tree_pending.extend((n,w,radius) for n,w in accepted)
    baker.rejections['independent_source_candidates_'+rule['id']]=attempted-target
    print('SOURCE_TREE_RULE_COMPLETE',rule['id'],'groups',batches,'trees',target,'inactive_slots',inactive,'max_batch_radius_m',maximum_radius,flush=True)


def flush_occupancy(baker):
    if not getattr(baker,'source_tree_pending',None):return
    from scipy.spatial import cKDTree
    values=np.asarray(baker.source_tree_pending,dtype=float)
    baker.source_tree_index=cKDTree(values[:,:2]);baker.source_tree_clearance=values[:,2];baker.source_tree_max_clearance=float(values[:,2].max())
    baker.source_tree_pending=[];baker.source_tree_flushed=True


def rebuild_forests(recipe,source_scene,document):
    """Resample trees through the same Baker without rebaking unchanged land.

    Registered assets, source materials, terrain arrays, road/contact triangles,
    mission and ordinary placements are frozen from the source version.
    """
    from .worldgen import Baker
    from .heightfield import sample_grid
    from .grove_grounding import conform_grove
    from .content import sha,registered_version
    class HeightView:
        def height_many(self,n,w):
            n,w=np.broadcast_arrays(n,w);meta=document['terrain'];arrays=source_scene.arrays
            values=sample_grid(arrays['base'],meta['base'],n,w)
            for tile in sorted(meta['details'],key=lambda x:x['spacing'],reverse=True):
                inside=(n>=tile['origin_north'])&(n<=tile['origin_north']+(tile['columns']-1)*tile['spacing'])&(w>=tile['origin_west'])&(w<=tile['origin_west']+(tile['rows']-1)*tile['spacing'])
                values=np.where(inside,sample_grid(arrays[tile.get('array_key','focus')],tile,n,w),values)
            return values
        def height(self,n,w):return float(self.height_many(n,w))
    baker=Baker(recipe);baker.terrain=HeightView()
    source_zones={r['id'] for r in recipe['scatter_rules'] if r['roles']=='canopy'}
    ordinary=[i for i in document['instances'] if not (i['category']=='vegetation' and i['zone'] in source_zones)]
    baker.instances=list(ordinary);baker.serial=max([int(i['id'].rsplit('_',1)[-1]) for i in document['instances'] if i['id'].rsplit('_',1)[-1].isdigit()]+[0])
    for item in ordinary:
        n,w=item['position'][:2];baker.occupied.setdefault((math.floor(n/50),math.floor(w/50)),[]).append((n,w,item['radius_m']))
    for rule in recipe['scatter_rules']:
        if rule['roles']=='canopy':build_rule(baker,rule)
    source_items=baker.instances[len(ordinary):];fits=[]
    for item in source_items:
        fit=conform_grove(baker.metadata[item['model']],*item['position'][:2],item['yaw'],item['scale'],baker.terrain.height,sample_heights=baker.terrain.height_many,ground_stems=item['ground_stems'])
        item['grove_ground_conform']=fit;fits.append(fit)
    document['instances']=baker.instances;document['chunks']={}
    for item in baker.instances:document['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    document['counts']={k:sum(i['category']==k for i in baker.instances) for k in ['vegetation','building','prop']}
    for category,key in [('vegetation','vegetation_instances'),('building','building_instances'),('prop','prop_instances')]:
        if document['counts'][category]>recipe['budgets'][key]:raise ValueError('Source forest rebuild exceeds '+key)
    for id in set(i['model'] for i in source_items):
        m=baker.metadata[id];document['resource_versions'][id]=registered_version(id,m)
    if document.get('environment') is not None:document['environment']['decorative_instance_ids']=[i['id'] for i in baker.instances if i['category']!='building']
    document['forest_representation']={'independently_grounded_groves':len(source_items),'independently_grounded_source_trees':sum(len(i['ground_stems']) for i in source_items),
        'unused_shared_mesh_slots':sum(i['independent_source_layout']['source_slots']-len(i['ground_stems']) for i in source_items),'maximum_batch_axis_extent_m':max(float(np.ptp(i['ground_stems'],axis=0).max()) for i in source_items),
        'maximum_batch_radius_m':max(i['radius_m'] for i in source_items),'maximum_per_grove_height_span_m':max(f['source_height_span_m'] for f in fits),
        'ground_conform_approximation':'Independent authored source tree locations, bounded shared64-tree batches and indexed shared terrain; unused slots collapse in all raster passes. No terrain grading; not measured GIS.'}
    document['source_tree_layout_rebuild']={'source_map':str(source_scene.path.resolve()),'source_map_sha256':sha(source_scene.path),
        'helper_sha256':sha(__file__),'ordinary_instances_preserved':len(ordinary),'operation':'Existing Baker source-tree placement only; shared terrain/materials/contact/mission and ordinary placements preserved'}
    return document
