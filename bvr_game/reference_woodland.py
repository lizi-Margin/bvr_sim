"""Authored continuous temperate woodland and source-derived aerial appearance."""
from pathlib import Path
import copy,json,struct,io
import numpy as np
from shapely.geometry import box,Polygon,Point,LineString
from shapely.ops import unary_union
from .content import ASSETS,sha
from .regional_cover import smooth_noise


def crown_mean(asset_id,material_name=None):
    manifest_path=ASSETS/'registered'/asset_id/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    file=manifest_path.parent/manifest['lods'][0]['file']
    if sha(file)!=manifest['lods'][0]['sha256']:raise ValueError('Source crown changed')
    data=file.read_bytes();length=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+length]);primitive=doc['meshes'][0]['primitives'][0]
    if 'COLOR_0' not in primitive['attributes']:
        from PIL import Image
        name=material_name or manifest.get('conversion_recipe',{}).get('policy',{}).get('crown_albedo_material')
        if not name:raise ValueError('Textured crown mean requires an explicit source foliage material')
        material=next(m for m in doc['materials'] if m['name']==name)
        pbr=material['pbrMetallicRoughness'];texture=doc['textures'][pbr['baseColorTexture']['index']]
        entry=doc['images'][texture['source']];view=doc['bufferViews'][entry['bufferView']]
        offset=28+length+view.get('byteOffset',0)
        rgba=np.asarray(Image.open(io.BytesIO(data[offset:offset+view['byteLength']])).convert('RGBA'),dtype=np.float32)/255
        factor=np.asarray(pbr.get('baseColorFactor',[1,1,1,1]),dtype=np.float32)
        rgb=np.where(rgba[...,:3]<=.04045,rgba[...,:3]/12.92,((rgba[...,:3]+.055)/1.055)**2.4)*factor[:3]
        alpha=rgba[...,3]*factor[3];alpha=np.where(alpha>=material.get('alphaCutoff',.5),alpha,0)
        return ((rgb*alpha[...,None]).sum(axis=(0,1),dtype=np.float64)/max(float(alpha.sum()),1)).tolist(),file
    accessor=doc['accessors'][primitive['attributes']['COLOR_0']];view=doc['bufferViews'][accessor['bufferView']]
    if accessor['componentType']!=5126 or accessor['type']!='VEC4':raise ValueError('Expected linear floating-point source colors')
    colors=np.frombuffer(data,dtype='<f4',count=accessor['count']*4,offset=28+length+view.get('byteOffset',0)+accessor.get('byteOffset',0)).reshape(-1,4)
    return colors[:,:3].mean(axis=0,dtype=np.float64).tolist(),file


def configure(recipe,asset_id,*,batches=24000,resolution=8192,clearing_policy=None):
    result=copy.deepcopy(recipe);seed=result['seed'];step=200
    axis=np.arange(-9800,9800,step);n,w=np.meshgrid(axis+step/2,axis+step/2)
    broad=smooth_noise(n,w,1250,seed+701);fine=smooth_noise(n,w,360,seed+709)
    road_distance=np.full(n.shape,np.inf)
    from .detail_bake import _distance_line
    for road in result['roads']:road_distance=np.minimum(road_distance,_distance_line(n,w,LineString(road['points'])))
    clear=(.8*broad+.2*fine>.62)|((road_distance<650)&(.75*broad+.25*fine>.53))
    clear_cells=[box(a-step/2,b-step/2,a+step/2,b+step/2) for a,b in zip(n[clear],w[clear])]
    clearings=unary_union(clear_cells).buffer(150).buffer(-60).simplify(45,preserve_topology=True)
    if clearing_policy is not None:
        count=int(clearing_policy.get('count',320));low,high=clearing_policy.get('radius_range_m',[35,125])
        if not 0<=count<=3000 or not 20<=low<=high<=500:raise ValueError('Invalid authored woodland clearing dimensions')
        rng=np.random.default_rng(seed+int(clearing_policy.get('seed_offset',149)));openings=[]
        angles=np.linspace(0,2*np.pi,20,endpoint=False)
        for _ in range(count):
            center=rng.uniform(-9500,9500,2);radius=rng.uniform(low,high);stretch=rng.uniform(.8,1.6);turn=rng.uniform(0,2*np.pi)
            radial=radius*(1+.17*np.sin(3*angles+rng.uniform(0,2*np.pi))+.11*np.cos(5*angles+rng.uniform(0,2*np.pi)))
            x=radial*np.cos(angles)*stretch;y=radial*np.sin(angles)/stretch
            vertices=np.column_stack([center[0]+x*np.cos(turn)-y*np.sin(turn),center[1]+x*np.sin(turn)+y*np.cos(turn)])
            openings.append(Polygon(vertices).buffer(12).buffer(-8).simplify(4,preserve_topology=True))
        clearings=unary_union(openings)
    for settlement in result['settlements']:
        clearings=clearings.union(Point(settlement['center']).buffer(settlement['radius_m']+140))
    for airport in result['airfields']:
        cn,cw=airport['center'];clearings=clearings.union(box(cn-airport['runway_length_m']/2-250,cw-600,cn+airport['runway_length_m']/2+250,cw+600))
    forest=box(-9800,-9800,9800,9800).difference(clearings).buffer(0)
    parts=list(forest.geoms) if hasattr(forest,'geoms') else [forest]
    parts=[p for p in parts if p.area>100000]
    zones=[z for z in result['zones'] if z['type']!='forest' or z['id']=='sample_woodland']
    ids=[]
    for index,poly in enumerate(parts):
        id='reference_woodland_'+str(index);ids.append(id)
        zones.append({'id':id,'type':'forest','polygon':list(map(list,poly.exterior.coords)),
                      'holes':[list(map(list,ring.coords)) for ring in poly.interiors]})
    result['zones']=zones;result['asset_roles']['canopy']=[asset_id]
    result['budgets']['vegetation_instances']=50000
    for rule in result['scatter_rules']:
        if rule['roles']!='canopy':continue
        if rule['id']=='forest_canopy':rule.update(zones=ids,count=batches,scale_range=[1.,1.35])
        rule.update(lod_distance_m=1400,cull_distance_m=50000,spatial_batch_extent_m=250)
        rule['edge_density']=({'width_m':30.,'variation_m':12.,'patch_scale_m':90.} if clearing_policy is not None
                              else {'width_m':90.,'variation_m':35.,'patch_scale_m':180.})
    mean,file=crown_mean(asset_id)
    result['landscape']['reference_woodland']={
        'version':1,'crown_color_source_file':str(file),'crown_color_source_sha256':sha(file),
        'crown_mean_linear':mean,'aerial_crown_color_fraction':.72,
        'forest_area_km2':sum(p.area for p in parts)/1e6,'forest_zone_ids':ids,
        'design':'Seeded continuous woodland with irregular clearings, road corridors and settlement/airport openings; authored, not GIS.',
        'approximation':'Aerial canopy/understory source-color mixture, not projected per-instance shadows or altered terrain.'}
    result['landscape']['macro_resolution']=resolution
    if clearing_policy is not None:
        result['landscape']['reference_woodland'].update(version=2,clearing_policy=copy.deepcopy(clearing_policy),
            design='Continuous woodland with many small authored irregular clearings, plus required airport/settlement openings; not GIS.')
    result['landscape'].setdefault('outer_surface',{}).update(resolution=8192,forest_scale_m=3000)
    result['materials']['grass']['color']=[.72,.82,.78,1]
    result['materials']['forest']['color']=[1.,1.,1.,1]
    result['materials']['soil']['color']=[.87,.84,.76,1]
    result['name']='reference_woodland_river_valley'
    return result,unary_union(parts)


def clearing_fields(fields,woodland,settlements):
    """A few cultivated clearings near settlements; no global checkerboard."""
    result=[]
    for index,field in enumerate(fields):
        poly=Polygon(field['polygon'],field.get('holes',[]))
        if index%3 or min(Point(s['center']).distance(poly) for s in settlements)>1000:continue
        remaining=poly.difference(woodland)
        parts=list(remaining.geoms) if hasattr(remaining,'geoms') else [remaining]
        for j,part in enumerate(parts):
            if not isinstance(part,Polygon) or part.area<3000:continue
            value=copy.deepcopy(field);value.update(polygon=list(map(list,part.exterior.coords)),holes=[list(map(list,r.coords)) for r in part.interiors])
            value['id']=str(field.get('id',index))+'_clearing_'+str(j)
            value['color']=[.9,.93,.9,1.];result.append(value)
    return result
