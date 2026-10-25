"""Immutable source-geometry forest candidate; preserve the physical environment."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys,uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.ground_atlas import copy_or_build_atlas

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-map',type=Path,required=True)
    p.add_argument('--forest-asset',default='fir_grove_geometry_quality')
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();original=BakedScene(a.source_map)
    document=copy.deepcopy(original.document)
    manifest_path=ASSETS/'registered'/a.forest_asset/'manifest.json'
    manifest=json.loads(manifest_path.read_text(encoding='utf8'))
    if not manifest.get('source_geometry_lods') or manifest.get('impostor'):
        raise ValueError('Reference geometry candidate requires source geometry at both levels')
    for lod in manifest['lods']:
        if sha(manifest_path.parent/lod['file'])!=lod['sha256']:raise ValueError('Source mesh changed')
    if manifest['cluster']['ground_conform']['anchor_encoding']!='source_tree_index_uv1':
        raise ValueError('Independent terrain-grounded source geometry is required')
    recipe=json.loads((a.source_map.parent/'scene-recipe.json').read_text(encoding='utf8'))
    recipe['name']='river_valley_reference_geometry_quality'
    document['name']=recipe['name']
    old_assets=set();changed=trees=0
    for placement in document['instances']:
        if 'ground_stems' not in placement:continue
        if len(placement['ground_stems'])>manifest['cluster']['source_copies']:
            raise ValueError('New source batch cannot hold the recorded tree positions')
        old_assets.add(placement['model']);placement['model']=a.forest_asset
        placement['lod_distance']=1200.;placement['cull_distance']=50000.
        changed+=1;trees+=len(placement['ground_stems'])
    if not changed:raise ValueError('No independent source forest in source map')
    for asset in old_assets:document['resource_versions'].pop(asset)
    document['resource_versions'][a.forest_asset]={'sha256':manifest['glb_sha256'],
        'lods':manifest['lods'],'manifest_sha256':sha(manifest_path)}
    for role,assets in recipe['asset_roles'].items():
        if isinstance(assets,list):recipe['asset_roles'][role]=[a.forest_asset if id in old_assets else id for id in assets]
        else:recipe['asset_roles'][role]=a.forest_asset if assets in old_assets else assets
    recipe['reference_quality']={'builder_version':2,'source_map':str(a.source_map.resolve()),'source_map_sha256':sha(a.source_map),
        'forest_asset':a.forest_asset,'source_manifest_sha256':sha(manifest_path),
        'performance_constraint':'Quality-first user goal; old frame-rate target removed',
        'scope':'First source-geometry forest candidate; land-use/ecology, cloud appearance and final visual match still require work.'}
    document['reference_quality']=recipe['reference_quality']
    document['recipe_sha256']=hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    document['source_geometry_forest']={'source_asset':a.forest_asset,'changed_batches':changed,'trees':trees,
        'near_triangles_per_tree':manifest['source_geometry_lods']['near_triangles_per_tree'],
        'far_triangles_per_tree':manifest['source_geometry_lods']['far_triangles_per_tree'],
        'tree_positions_unchanged':True,'method':manifest['source_geometry_lods'].get('method','Source-derived three dimensional crown approximation; no whole-tree crossed billboards.')}
    for key in ['surfaces','environment','mission','fields','roads','rivers','airfields','settlements']:
        assert document[key]==original.document[key],key
    for before,after in zip(original.document['instances'],document['instances']):
        assert {k:v for k,v in before.items() if k not in ('model','lod_distance','cull_distance')}=={k:v for k,v in after.items() if k not in ('model','lod_distance','cull_distance')}
    version=hashlib.sha256(json.dumps(document,sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    target=a.output.resolve()/'versions'/version
    if target.exists():raise FileExistsError('Immutable candidate already exists: '+str(target))
    stage=a.output.resolve()/('._bake-'+uuid.uuid4().hex);stage.mkdir(parents=True)
    shutil.copy2(original.height_file,stage/'terrain.npz');document['terrain']['file']='terrain.npz'
    document['terrain']['ground_atlas']=copy_or_build_atlas(original,document['terrain'],stage)
    document['terrain']['ground_atlas']['file']=Path(document['terrain']['ground_atlas']['file']).name
    assert sha(stage/'terrain.npz')==original.document['terrain']['sha256']
    write_json(stage/'scene-recipe.json',recipe);write_json(stage/'generated-map.json',document)
    target.parent.mkdir(parents=True,exist_ok=True);stage.rename(target)
    BakedScene(target/'generated-map.json')
    write_json(a.output/'candidate.json',{'map':str(target/'generated-map.json'),'sha256':sha(target/'generated-map.json'),
        'terrain_sha256':document['terrain']['sha256'],'forest':document['source_geometry_forest'],
        'status':'built_requires_actual_visual_review'})
    print(json.dumps({'map':str(target/'generated-map.json'),'batches':changed,'trees':trees}),flush=True)
if __name__=='__main__':main()
