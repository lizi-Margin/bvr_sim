"""Offline checks over baked data, source provenance and spatial constraints."""
from pathlib import Path
import json,math,hashlib
import numpy as np
from shapely.geometry import Point,LineString,box
from shapely.ops import unary_union
from .scene_runtime import BakedScene
from .content import ASSETS,sha

def validate(path):
    scene=BakedScene(path);d=scene.document;failures=[];items=d['instances'];counts={}
    water=unary_union([LineString(r['points']).buffer(r['width_m']/2,cap_style=2) for r in d['rivers']])
    roads=unary_union([LineString(r['points']).buffer(r['width_m']/2+10) for r in d['roads']])
    versions=d['resource_versions'];inventory=[]
    for id,version in versions.items():
        p=ASSETS/'registered'/id/'manifest.json';m=json.loads(p.read_text(encoding='utf8'))
        for key in ['source_url','license','source_sha256','blender','conversion_recipe','units','bounds_blender','vertices','faces','materials','textures','lods','recommended_use','recommended_density_per_km2','collision_type','instancing_allowed','distribution_allowed']:
            if key not in m:failures.append({'asset':id,'missing_field':key})
        if m['license']!='CC0-1.0' or not m['distribution_allowed']:failures.append({'asset':id,'license':m['license']})
        if version['sha256']!=sha(p.parent/m['file']):failures.append({'asset':id,'error':'map resource version changed'})
        for lod in m['lods']:
            if sha(p.parent/lod['file'])!=lod['sha256']:failures.append({'asset':id,'error':'LOD hash mismatch'})
        span=m['bounds_blender']['span']
        if min(span)<=0 or max(span)>200:failures.append({'asset':id,'error':'implausible size','span':span})
        if len(m['lods'])<2:failures.append({'asset':id,'error':'two LODs required'})
        inventory.append(m)
    exclusions=[(e,box(e['center'][0]-e['size_m'][0]/2,e['center'][1]-e['size_m'][1]/2,e['center'][0]+e['size_m'][0]/2,e['center'][1]+e['size_m'][1]/2)) for e in d['exclusion_zones']]
    seen=set();grid={};pairs=0
    for item in items:
        id=item['id'];n,w,h=item['position'];radius=item['radius_m'];point=Point(n,w);category=item['category']
        if id in seen:failures.append({'instance':id,'error':'duplicate id'})
        seen.add(id);counts[category]=counts.get(category,0)+1
        if point.distance(water)<radius-.01:failures.append({'instance':id,'error':'water overlap'})
        if category=='vegetation' and point.distance(roads)<radius-.01:failures.append({'instance':id,'error':'road exclusion'})
        for rule,polygon in exclusions:
            blocked=('no_tall_objects' in rule['rules'] or ('no_vegetation' in rule['rules'] and category=='vegetation') or ('no_building' in rule['rules'] and category=='building'))
            if blocked and point.distance(polygon)<radius-.01:failures.append({'instance':id,'error':'exclusion '+rule['id']})
        chunk=f'{math.floor(n/d["chunk_m"])}:{math.floor(w/d["chunk_m"])}'
        if chunk!=item['chunk'] or id not in d['chunks'].get(chunk,[]):failures.append({'instance':id,'error':'chunk membership'})
        key=(math.floor(n/100),math.floor(w/100))
        for a in range(key[0]-2,key[0]+3):
            for b in range(key[1]-2,key[1]+3):
                for other in grid.get((a,b),[]):
                    pairs+=1
                    if math.hypot(n-other['position'][0],w-other['position'][1])<radius+other['radius_m']-.015:failures.append({'instance':id,'other':other['id'],'error':'footprint overlap'})
        grid.setdefault(key,[]).append(item)
    for category,key in [('vegetation','vegetation_instances'),('building','building_instances'),('prop','prop_instances')]:
        if counts.get(category,0)>d['budgets'][key]:failures.append({'budget':key,'actual':counts.get(category,0)})
    fine=scene.arrays['focus'];cover=scene.arrays['landcover'];unique=np.unique(cover).tolist()
    surface_names=['grass','farmland','forest','soil','rock','pavement','water','marking']
    represented={surface_names[i] for i in unique if 0<=i<len(surface_names)}
    represented.update(s['material'] for s in d['surfaces'] if s.get('indices'))
    required=set(surface_names[:7]);missing=required-represented
    if missing:failures.append({'error':'missing land-use classes','missing':sorted(missing),'raster_classes':unique})
    if np.ptp(fine)<150:failures.append({'error':'insufficient genuine relief'})
    return {'status':'passed' if not failures else 'failed','map_sha256':sha(path),'terrain_sha256':d['terrain']['sha256'],'instances':len(items),'counts':counts,'chunks':len(d['chunks']),'fine_sample_m':d['terrain']['details'][0]['spacing'],'height_range_m':[float(fine.min()),float(fine.max())],'landcover_classes':unique,'represented_land_use':sorted(represented),'checked_neighbor_pairs':pairs,'failures':failures,'resource_inventory':inventory}
