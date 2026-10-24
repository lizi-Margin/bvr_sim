"""Offline checks over baked data, source provenance and spatial constraints."""
from pathlib import Path
import json,math,hashlib
import numpy as np
from shapely import points as geometry_points,distance as geometry_distance,contains_xy
from shapely.geometry import Point,LineString,Polygon,box
from shapely.ops import unary_union
from .scene_runtime import BakedScene
from .content import ASSETS,sha

def validate(path):
    scene=BakedScene(path);d=scene.document;failures=[];items=d['instances'];counts={}
    water=unary_union([LineString(r['points']).buffer(r['width_m']/2,cap_style=2) for r in d['rivers']])
    roads=unary_union([LineString(r['points']).buffer(r['width_m']/2+10) for r in d['roads']])
    versions=d['resource_versions'];inventory=[];metadata={}
    for id,version in versions.items():
        p=ASSETS/'registered'/id/'manifest.json';m=json.loads(p.read_text(encoding='utf8'))
        metadata[id]=m
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
    from .grove_grounding import stem_spacing_report
    stem_report=stem_spacing_report(items,metadata);failures.extend(stem_report['failures'])
    overlapping_crowns={item['id'] for item in items if metadata[item['model']].get('cluster') and metadata[item['model']].get('conversion_recipe',{}).get('policy',{}).get('cluster',{}).get('inter_grove_stem_spacing_m',0)}
    seen=set();grid={};pairs=0;independent_points=[];independent_radii=[];independent_owners=[];ordinary=[];forest_masks={};recipe_rules=None
    for item in items:
        id=item['id'];n,w,h=item['position'];radius=item['radius_m'];point=Point(n,w);category=item['category']
        if id in seen:failures.append({'instance':id,'error':'duplicate id'})
        seen.add(id);counts[category]=counts.get(category,0)+1
        chunk=f'{math.floor(n/d["chunk_m"])}:{math.floor(w/d["chunk_m"])}'
        if chunk!=item['chunk'] or id not in d['chunks'].get(chunk,[]):failures.append({'instance':id,'error':'chunk membership'})
        if 'ground_stems' in item:
            model=metadata[item['model']];encoding=model['cluster'].get('ground_conform') or {};stems=np.asarray(item['ground_stems'],dtype=float)
            if encoding.get('anchor_encoding')!='source_tree_index_uv1' or stems.ndim!=2 or stems.shape[1]!=2 or not 1<=len(stems)<=len(model['cluster']['poses_before_recentering']) or not np.isfinite(stems).all():
                failures.append({'instance':id,'error':'independent source tree encoding/count'});continue
            source_radius=max(math.hypot(x,y) for b in encoding['tree_bounds_relative_blender'] for x in [b['min'][0],b['max'][0]] for y in [b['min'][1],b['max'][1]])*item['scale']
            clearance=item['stem_clearance_radius_m']
            declared_zones=item['independent_source_layout'].get('forest_zones')
            if declared_zones is None:
                if recipe_rules is None:recipe_rules={r['id']:r for r in json.loads((Path(path).parent/'scene-recipe.json').read_text(encoding='utf8'))['scatter_rules']}
                declared_zones=recipe_rules[item['zone']]['zones']
            zones=tuple(declared_zones)
            if zones not in forest_masks:forest_masks[zones]=unary_union([Polygon(z['polygon']) for z in d['zones'] if z['id'] in zones and z['type']=='forest'])
            if not contains_xy(forest_masks[zones],stems[:,0],stems[:,1]).all():failures.append({'instance':id,'error':'independent source tree outside declared forest'})
            if np.ptp(stems,axis=0).max()>item['independent_source_layout']['maximum_axis_extent_m']+.001:failures.append({'instance':id,'error':'independent spatial batch extent exceeded'})
            if clearance<source_radius-.001:failures.append({'instance':id,'error':'independent source crown clearance understated'})
            if radius<np.max(np.linalg.norm(stems-[n,w],axis=1))+source_radius-.01:failures.append({'instance':id,'error':'independent source batch bounds understated'})
            independent_points.append(stems);independent_radii.extend([clearance]*len(stems));independent_owners.extend([id]*len(stems));continue
        ordinary.append(item)
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
                    if id in overlapping_crowns and other['id'] in overlapping_crowns:continue
                    if math.hypot(n-other['position'][0],w-other['position'][1])<radius+other['radius_m']-.015:failures.append({'instance':id,'other':other['id'],'error':'footprint overlap'})
        grid.setdefault(key,[]).append(item)
    for category,key in [('vegetation','vegetation_instances'),('building','building_instances'),('prop','prop_instances')]:
        if counts.get(category,0)>d['budgets'][key]:failures.append({'budget':key,'actual':counts.get(category,0)})
    source_points_checked=0;source_neighbor_pairs=0
    if independent_points:
        from scipy.spatial import cKDTree
        source=np.concatenate(independent_points);radii=np.asarray(independent_radii);geometry=geometry_points(source);source_points_checked=len(source)
        blocked=[('water',water),('road',roads)]
        blocked.extend((z['id'],Polygon(z['polygon']).buffer(100)) for z in d['zones'] if z['type']=='industrial')
        blocked.extend((rule['id'],poly) for rule,poly in exclusions if 'no_tall_objects' in rule['rules'] or 'no_vegetation' in rule['rules'])
        for name,polygon in blocked:
            invalid=np.flatnonzero(geometry_distance(polygon,geometry)<radii-.01)
            for index in invalid[:20]:failures.append({'instance':independent_owners[index],'source_tree':int(index),'error':'independent source '+name+' exclusion'})
        for settlement in d['settlements']:
            invalid=np.flatnonzero(np.linalg.norm(source-settlement['center'],axis=1)<settlement['radius_m']+radii-.01)
            for index in invalid[:20]:failures.append({'instance':independent_owners[index],'error':'independent source settlement exclusion'})
        tree=cKDTree(source);maximum_radius=float(radii.max())
        for item in ordinary:
            center=item['position'][:2];near=tree.query_ball_point(center,item['radius_m']+maximum_radius)
            if not near:continue
            source_neighbor_pairs+=len(near);near=np.asarray(near);bad=near[np.linalg.norm(source[near]-center,axis=1)<radii[near]+item['radius_m']-.015]
            for index in bad[:5]:failures.append({'instance':independent_owners[index],'other':item['id'],'error':'independent source/object footprint overlap'})
    fine=scene.arrays['focus'];cover=scene.arrays['landcover'];unique=np.unique(cover).tolist()
    surface_names=['grass','farmland','forest','soil','rock','pavement','water','marking']
    represented={surface_names[i] for i in unique if 0<=i<len(surface_names)}
    represented.update(s['material'] for s in d['surfaces'] if s.get('indices'))
    required=set(surface_names[:7]);missing=required-represented
    if missing:failures.append({'error':'missing land-use classes','missing':sorted(missing),'raster_classes':unique})
    if np.ptp(fine)<150:failures.append({'error':'insufficient genuine relief'})
    return {'status':'passed' if not failures else 'failed','map_sha256':sha(path),'terrain_sha256':d['terrain']['sha256'],'instances':len(items),'counts':counts,'chunks':len(d['chunks']),'fine_sample_m':d['terrain']['details'][0]['spacing'],'height_range_m':[float(fine.min()),float(fine.max())],'landcover_classes':unique,'represented_land_use':sorted(represented),'checked_neighbor_pairs':pairs,'grove_stem_spacing':stem_report,'independent_source_points_checked':source_points_checked,'independent_source_object_neighbor_pairs':source_neighbor_pairs,'failures':failures,'resource_inventory':inventory}

def main():
    import argparse
    from .content import write_json
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path)
    a=p.parse_args();report=validate(a.map)
    if a.output:write_json(a.output,report)
    print(json.dumps({k:v for k,v in report.items() if k!='resource_inventory'},indent=2))
    if report['status']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
