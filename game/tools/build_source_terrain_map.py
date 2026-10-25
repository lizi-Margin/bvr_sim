"""Bake a playable typed terrain from retained original WT landmesh samples."""
from pathlib import Path
import argparse,copy,json,math,shutil,sys
import numpy as np
from PIL import Image
from shapely import union_all,constrained_delaunay_triangles
from shapely.geometry import box,Point
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.worldgen import deterministic_npz
from bvr_game.scene_runtime import BakedScene
from bvr_game.heightfield import sample_grid
from bvr_game.source_water import wet_footprint,without_holes
from bvr_game.river_valley import building_foundation,smooth


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--template',type=Path,required=True);p.add_argument('--height-report',type=Path,required=True)
    p.add_argument('--macro-report',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    original=BakedScene(a.template);src=json.loads(a.height_report.read_text());macro=json.loads(a.macro_report.read_text())
    if sha(src['file'])!=src['sha256'] or sha(macro['macro'])!=macro['macro_sha256']:raise ValueError('Retained original terrain/macro source changed')
    source=np.load(src['file'],allow_pickle=False)['base'];source_meta={k:src[k] for k in ['origin_north','origin_west','spacing','columns','rows']}
    doc=copy.deepcopy({k:v for k,v in original.document.items() if k not in ('instances','chunks','environment','surfaces')})
    # Original source height is the basis everywhere. Only runway/taxi/apron
    # pads receive explicitly authored grading; no invented sinusoidal hills.
    airport_levels=[]
    for airport in doc['airfields']:
        n,w=airport['center'];level=max(10.,float(sample_grid(source,source_meta,n,w)))
        airport_levels.append({'id':airport['id'],'height_m':level})
    def height_rule(n,w):
        h=sample_grid(source,source_meta,n,w)
        for airport,grade in zip(doc['airfields'],airport_levels):
            cn,cw=airport['center'];half=airport['runway_length_m']/2
            pads=[(cn,cw,half+35,airport['runway_width_m']/2+12),(cn,cw+airport['taxi_offset_m'],half-80,18),(*airport['apron'],airport['apron_size_m'][0]/2,airport['apron_size_m'][1]/2)]
            for pn,pw,hn,hw in pads:
                weight=smooth(np.maximum(np.abs(n-pn)-hn,np.abs(w-pw)-hw)/200.)
                h=h*weight+grade['height_m']*(1-weight)
        return np.asarray(h,dtype=np.float32)
    arrays={};tiles=[]
    for key,half,step in [('base',64000,40),('focus',10000,20),('sample',1000,5)]:
        meta={'origin_north':-half,'origin_west':-half,'spacing':step,'columns':2*half//step+1,'rows':2*half//step+1,'material':'source_macro'}
        if key!='base':meta['array_key']=key
        value=np.empty((meta['rows'],meta['columns']),dtype=np.float32);north=-half+np.arange(meta['columns'])*step
        for first in range(0,meta['rows'],128):
            n,w=np.meshgrid(north,-half+np.arange(first,min(first+128,meta['rows']))*step);value[first:first+len(w)]=height_rule(n,w)
        if tiles:
            parent_key,parent=tiles[-1];n,w=np.meshgrid(north,-half+np.arange(meta['rows'])*step)
            edge=np.minimum(half-abs(n),half-abs(w));blend=smooth(edge/300)
            value=(value*blend+sample_grid(arrays[parent_key],parent,n,w)*(1-blend)).astype(np.float32)
        arrays[key]=value;tiles.append((key,meta));print('SOURCE_HEIGHT_TILE',key,value.shape,flush=True)
    doc['terrain']={'version':3,'file':'terrain.npz','base':tiles[0][1],'details':[x[1] for x in tiles[1:]],'bound_macro_only':True,
                    'cell_diagonal':'Same indexed triangle planes as core Terrain,water clipping,and native mesh'}
    def height(n,w):
        for key,meta in reversed(tiles):
            if meta['origin_north']<=n<=meta['origin_north']+(meta['columns']-1)*meta['spacing'] and meta['origin_west']<=w<=meta['origin_west']+(meta['rows']-1)*meta['spacing']:return float(sample_grid(arrays[key],meta,n,w))
        raise ValueError('Height query outside imported source map')
    water_parts=[]
    for index,(key,meta) in enumerate(tiles):
        cut=None
        if index+1<len(tiles):
            t=tiles[index+1][1];cut=[t['origin_north'],t['origin_west'],t['origin_north']+(t['columns']-1)*t['spacing'],t['origin_west']+(t['rows']-1)*t['spacing']]
        water_parts.append(wet_footprint(arrays[key],meta,0.,cut));print('SOURCE_WATER_TILE',key,flush=True)
    water=union_all(water_parts);core_polygons=without_holes(water)
    from shapely import to_wkb
    (out/'water-footprint.wkb').write_bytes(to_wkb(water))
    doc['surfaces']=[]
    if not water.is_empty:
        lo_n,lo_w,hi_n,hi_w=water.bounds
        for n in range(math.floor(lo_n/2000),math.ceil(hi_n/2000)):
            for w in range(math.floor(lo_w/2000),math.ceil(hi_w/2000)):
                part=water.intersection(box(n*2000,w*2000,(n+1)*2000,(w+1)*2000))
                if part.is_empty or part.area<1e-6:continue
                vertices=[];indices=[]
                for tri in constrained_delaunay_triangles(part).geoms:
                    points=list(tri.exterior.coords)[:3]
                    p0,p1,p2=points
                    if (p1[0]-p0[0])*(p2[1]-p0[1])-(p1[1]-p0[1])*(p2[0]-p0[0])<0:points.reverse()
                    indices.extend(range(len(vertices),len(vertices)+3));vertices.extend([[x,y,.025] for x,y in points])
                if indices:doc['surfaces'].append({'id':f'source_water_{n}_{w}','material':'water','vertices':vertices,'indices':indices,'drivable':False,'authored_water_level_m':0.,'visual_bias_m':.025})
    print('SOURCE_WATER_BUILT',len(core_polygons),'core polygons',len(doc['surfaces']),'render tiles',flush=True)
    # Airport mesh and core contact use the same regraded vertices. Legacy
    # invented river ribbons/roads are excluded from this source-map candidate.
    for surface in original.document['surfaces']:
        if not surface['id'].startswith(('runway','taxi','apron','threshold')) or surface['material']=='water':continue
        item=copy.deepcopy(surface)
        offset=.08 if item['material']=='marking' else .06 if item['material']=='pavement' else .02
        for v in item['vertices']:v[2]=height(v[0],v[1])+offset
        doc['surfaces'].append(item)
    doc['instances']=[];obstacles=[];rejected=0
    for old in original.document['instances']:
        if old['category']=='vegetation':continue
        item=copy.deepcopy(old);n,w=item['position'][:2]
        if water.distance(Point(n,w))<item['radius_m']+1:rejected+=1;continue
        manifest=json.loads((ASSETS/'registered'/item['model']/'manifest.json').read_text())
        item['position'][2]=height(n,w)-manifest['bounds_blender']['min'][2]*item['scale']
        if item['category']=='building':
            foundation,obstacle=building_foundation(item,manifest,height);doc['surfaces'].append(foundation);obstacles.append(obstacle)
        doc['instances'].append(item)
    doc['chunks']={}
    for item in doc['instances']:doc['chunks'].setdefault(item['chunk'],[]).append(item['id'])
    doc['counts']={k:sum(i['category']==k for i in doc['instances']) for k in ['vegetation','building','prop']}
    doc['environment']={'version':2,'contact_surfaces':[{'id':s['id'],'material':s['material'],'vertices':s['vertices'],'indices':s['indices'],'drivable':True} for s in doc['surfaces'] if s['material']=='pavement'],
        'obstacles':obstacles,'water_regions':[{'id':f'source_water_{i}','polygon':list(map(list,p.exterior.coords))} for i,p in enumerate(core_polygons)],
        'decorative_instance_ids':[i['id'] for i in doc['instances'] if i['category']!='building']}
    doc['rivers']=[];doc['roads']=[];doc['fields']=[];doc['focus_area_km']=[20,20]
    doc['mission']['target'][2]=height(*doc['mission']['target'][:2])
    # Ground routes must be authored for this shoreline before offering convoy
    # play. This flight-art candidate does not reuse routes through new water.
    doc['mission']['ground_units']=[]
    used={i['model'] for i in doc['instances']};doc['resource_versions']={k:v for k,v in doc['resource_versions'].items() if k in used}
    for key,meta in tiles:
        label='outer_landcover' if key=='base' else 'landcover' if key=='focus' else None
        if label:
            arrays[label]=np.zeros((meta['rows']-1,meta['columns']-1),dtype=np.uint8)
            arrays['outer_macro_color' if key=='base' else 'macro_color']=np.ones((meta['rows']-1,meta['columns']-1,4),dtype=np.float32)
    deterministic_npz(out/'terrain.npz',arrays);doc['terrain']['sha256']=sha(out/'terrain.npz')
    Image.new('RGB',(2,2),(128,128,255)).save(out/'flat-normal.png');Image.new('L',(2,2),235).save(out/'roughness.png')
    material={'provider':'retained original source macro','id':'smolensk-original-macro-v103','color':[1,1,1,1],'roughness':.92,'tile_m':131072,
        'base_color':macro['macro'],'base_color_sha256':macro['macro_sha256'],'normal':str(out/'flat-normal.png'),'normal_sha256':sha(out/'flat-normal.png'),
        'roughness_map':str(out/'roughness.png'),'roughness_map_sha256':sha(out/'roughness.png'),'world_uv':True,'uv_origin_north':-65536,'uv_origin_west':-65536,
        'license':'Local original WT source;not redistributable','distribution_allowed':False,'source_url':'local:original Smolensk class macro;not the full source shader'}
    doc['materials']['source_macro']=material
    for key in ['forest_representation','reference_quality','source_tree_layout_rebuild','source_card_resource_swap','offline_ground_policy']:
        doc.pop(key,None)
    doc['name']='source_smolensk_typed_terrain_candidate'
    doc['source_terrain_bake']={'template_sha256':sha(a.template),'height_report_sha256':sha(a.height_report),'source_height_sha256':src['sha256'],
        'macro_report_sha256':sha(a.macro_report),'macro_sha256':macro['macro_sha256'],'generator_sha256':sha(__file__),
        'water_helper_sha256':sha(ROOT/'bvr_game/source_water.py'),'authored_water_level_m':0.,'water_level_provenance':'Design level chosen for this candidate;not verified original game water level',
        'airport_grading':airport_levels,'water_area_m2':water.area,'core_water_polygons':len(core_polygons),'water_rejected_props':rejected,
        'scope':'Original sampled relief resampled to40/20/5m,explicit airport grading,and indexed level-water clipping. Typed core/render geometry share this archive. No original full shader,exact-source sea level,forest,ground-route or finished-art claim.'}
    write_json(out/'generated-map.json',doc)
    recipe={'schema_version':1,'kind':'source_terrain_adapter','source_terrain_bake':doc['source_terrain_bake'],'resource_use':{'mode':'local_private','asset_manifest_sha256':{k:sha(ASSETS/'registered'/k/'manifest.json') for k in used}}}
    write_json(out/'scene-recipe.json',recipe);BakedScene(out/'generated-map.json')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'status':'source_geometry_built_requires_actual_visual_review','source_terrain_bake':doc['source_terrain_bake']})
    print('SOURCE_MAP_BUILT',out/'generated-map.json',flush=True)
if __name__=='__main__':main()
