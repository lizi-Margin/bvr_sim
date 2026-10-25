"""Offline additive woodland edit, preserving the complete original scene.

Accepts a local-policy ground patch and original-source tree additions. Verifies
the existing point pool, all original instance bytes, physical environment and
registered near-geometry parent before saving a separate candidate map.
"""
from pathlib import Path
import argparse,copy,hashlib,json,math,shutil,sys
from collections import Counter
import numpy as np
from scipy.spatial import cKDTree
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.authored_canopy import woodland_mask
from game.tools.author_woodland_materials import geometry

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def instance_digest(items):
    h=hashlib.sha256()
    for item in items:h.update(json.dumps(item,sort_keys=True,separators=(',',':')).encode());h.update(b'\n')
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['source','additions','materials','existing-pool','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();doc=json.loads(a.source.read_text(encoding='utf8'));extra=json.loads(a.additions.read_text(encoding='utf8'));bundle=json.loads(a.materials.read_text(encoding='utf8'))
    before_count=len(doc['instances']);before_hash=instance_digest(doc['instances']);physics=geometry(doc);old_forest=copy.deepcopy(doc['source_woodland_bake']);new_forest=extra['source_woodland_bake']
    if geometry(extra)!=physics or bundle['geometry']!=physics:raise ValueError('Additions/ground patch change physical terrain or environment')
    for key in ['surfaces','mission','roads','rivers','airfields','settlements']:
        if extra[key]!=doc[key]:raise ValueError('Additions changed '+key)
    if extra['terrain']['ground_atlas']['sha256']!=doc['terrain']['ground_atlas']['sha256']:raise ValueError('Ground atlas changed')
    policy=bundle['biome_policy'];prior=old_forest['authored_biome']['policy'];bounds=policy['meadow_fragmentation']['bounds_nw']
    if new_forest['authored_biome']['policy']!=policy or bundle['biome_policy_sha256']!=new_forest['authored_biome']['sha256']:raise ValueError('Local tree/ground policies differ')
    if policy.get('parent_policy_sha256')!=old_forest['authored_biome']['sha256']:raise ValueError('Local policy identifies another parent')
    for key in set(prior)|set(policy):
        if key not in ['scope','parent_policy_sha256','meadow_fragmentation']and prior.get(key)!=policy.get(key):raise ValueError('Unrelated planting rule changed: '+key)
    remap=doc.get('distance_lod_derivation',{}).get('mapping',{})
    added=[copy.deepcopy(i)for i in extra['instances']if 'ground_stems'in i]
    points=np.concatenate([np.asarray(i['ground_stems'])for i in added]);n0,w0,n1,w1=bounds
    if not ((points[:,0]>n0)&(points[:,0]<n1)&(points[:,1]>w0)&(points[:,1]<w1)).all():raise ValueError('New tree leaves local edit bounds')
    if not woodland_mask(*points.T,policy).all()or woodland_mask(*points.T,prior).any():raise ValueError('New trees do not exclusively fill previously open support')
    local=[]
    for item in doc['instances']:
        if 'ground_stems'not in item:continue
        if n0-600<item['position'][0]<n1+600 and w0-600<item['position'][1]<w1+600:local.extend(item['ground_stems'])
    minimum=float(cKDTree(local).query(points,k=1)[0].min())
    if minimum<3:raise ValueError('New stem overlaps an existing stem')
    ids={i['id']for i in doc['instances']}
    for item in added:
        item['id']='confluence_addition_'+item['id'];item['model']=remap.get(item['model'],item['model'])
        if item['id']in ids:raise ValueError('Duplicate added instance ID')
        ids.add(item['id'])
        if item['model']not in doc['resource_versions']:raise ValueError('New tree requires a different registered resource')
    for mat in bundle['materials'].values():
        for layer in [mat]+([mat['ground_detail']]if mat.get('ground_detail')else[]):
            for key in ['base_color','normal','roughness_map']:
                if key in layer and sha(layer[key])!=layer[key+'_sha256']:raise ValueError('Ground image changed')
    large=bundle['large_asset'];registered=ASSETS/'registered'/remap.get(large,large);manifest=json.loads((registered/'manifest.json').read_text(encoding='utf8'))
    if remap.get(large):
        proof=manifest['source_distance_lod']
        if proof['parent_manifest_sha256']!=bundle['large_manifest_sha256']or not proof['high_detail_bytes_unchanged']:raise ValueError('Ground clearance requires another original near tree')
    elif sha(registered/'manifest.json')!=bundle['large_manifest_sha256']:raise ValueError('Ground clearance source changed')
    if sha(a.existing_pool)!=old_forest['points_sha256']:raise ValueError('Existing source point pool changed')
    old_points=np.load(a.existing_pool,mmap_mode='r');new_points=np.load(a.additions.parent/'authored-source-mask-points.npy',mmap_mode='r')
    if len(new_points)!=len(points)or sha(a.additions.parent/'authored-source-mask-points.npy')!=new_forest['points_sha256']:raise ValueError('New source point pool changed')
    a.output.mkdir(parents=True,exist_ok=False);pool=a.output/'authored-source-mask-points.npy'
    merged=np.lib.format.open_memmap(pool,mode='w+',dtype=old_points.dtype,shape=(len(old_points)+len(new_points),2))
    for start in range(0,len(old_points),1000000):
        stop=min(start+1000000,len(old_points));merged[start:stop]=old_points[start:stop]
    merged[len(old_points):]=new_points;merged.flush();del merged
    doc['instances'].extend(added)
    if instance_digest(doc['instances'][:before_count])!=before_hash:raise ValueError('Original instance data changed')
    doc['materials'].update(bundle['materials']);doc['terrain']['file']=str((a.source.parent/doc['terrain']['file']).resolve())
    atlas=doc['terrain']['ground_atlas'];atlas['file']=str((a.source.parent/atlas['file']).resolve())
    for tile in doc['terrain']['details']:tile['material']='source_focus'
    doc['chunks']={};mix=Counter();trees=0
    for item in doc['instances']:
        doc['chunks'].setdefault(item['chunk'],[]).append(item['id'])
        if 'ground_stems'in item:mix[item['model']]+=len(item['ground_stems']);trees+=len(item['ground_stems'])
    doc['counts']={k:sum(i['category']==k for i in doc['instances'])for k in ['vegetation','building','prop']}
    doc['budgets']['vegetation_instances']=max(doc['budgets']['vegetation_instances'],doc['counts']['vegetation'])
    doc['environment']['decorative_instance_ids'].extend(i['id']for i in added)
    doc['source_road_bake'].update({k:extra['source_road_bake'][k]for k in ['policy_file','policy_sha256','woodland_policy_revision']})
    forest=doc['source_woodland_bake'];forest.update(trees=trees,batches=old_forest['batches']+len(added),source_grove_mix=dict(mix),points_sha256=sha(pool),
        helper_sha256=bundle['footprint_helper_sha256'],authored_biome=new_forest['authored_biome'])
    forest['additive_revision']={'parent_bake':old_forest,'addition_bake':new_forest,'old_instances_retained_exactly':True,
        'scope':'Original forest retained without regeneration; new helpers apply to additions and ground-mask validation. Parent helper hashes remain in parent_bake.'}
    doc['authored_canopy_materials']={'bundle':str(a.materials.resolve()),'sha256':sha(a.materials),'source_map_sha256':sha(a.source),'tool_sha256':sha(__file__),'scope':bundle['scope']}
    doc['source_canopy_merge']={'source':str(a.source.resolve()),'source_sha256':sha(a.source),'additions':str(a.additions.resolve()),'additions_sha256':sha(a.additions),
        'retained_instances':before_count,'retained_instance_digest':before_hash,'added_batches':len(added),'added_trees':len(points),
        'total_trees':trees,'minimum_new_to_existing_stem_distance_m':minimum,'physical_geometry':physics,'tool_sha256':sha(__file__)}
    if geometry(doc)!=physics:raise ValueError('Physical geometry changed during merge')
    doc['distance_lod_derivation']['tree_count']=trees
    recipe=json.loads((a.additions.parent/'scene-recipe.json').read_text(encoding='utf8'));recipe['source_canopy_merge']=doc['source_canopy_merge']
    recipe['resource_use']['asset_manifest_sha256']={id:version['manifest_sha256']for id,version in doc['resource_versions'].items()}
    doc['resource_use']=copy.deepcopy(recipe['resource_use'])
    doc['recipe_sha256']=digest(recipe)
    (a.output/'generated-map.json').write_text(json.dumps(doc,ensure_ascii=False,separators=(',',':')),encoding='utf8')
    shutil.copy2(a.additions.parent/'water-footprint.wkb',a.output/'water-footprint.wkb')
    write_json(a.output/'scene-recipe.json',recipe);write_json(a.output/'merge-report.json',doc['source_canopy_merge'])
    print('ADDITIVE_CANOPY_MERGE',trees,'ADDED',len(points),'RETAINED_INSTANCES',before_count,flush=True)

if __name__=='__main__':main()
