"""Build continuous reference woodland through the existing source-tree/material Baker."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys,uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.reference_woodland import configure,clearing_fields
from bvr_game.source_tree_layout import rebuild_forests
from bvr_game.worldgen import Baker,BakedTerrain
from bvr_game.detail_bake import _bake_material
from bvr_game.regional_cover import bake_outer_cover
from bvr_game.ground_atlas import copy_or_build_atlas

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--forest-asset',default='fir_grove_crown_volume_b')
    p.add_argument('--batches',type=int,default=24000);p.add_argument('--resolution',type=int,default=8192)
    p.add_argument('--clearing-policy',type=Path,help='Authored small-clearing layout instead of large noise-generated open areas')
    a=p.parse_args()
    if a.output.exists():raise FileExistsError('Use a new candidate directory')
    a.output.mkdir(parents=True);stage=a.output.resolve()/('._bake-'+uuid.uuid4().hex);stage.mkdir()
    original=BakedScene(a.source_map);doc=copy.deepcopy(original.document)
    source_recipe=json.loads((a.source_map.parent/'scene-recipe.json').read_text(encoding='utf8'))
    policy=json.loads(a.clearing_policy.read_text()) if a.clearing_policy else None
    recipe,woods=configure(source_recipe,a.forest_asset,batches=a.batches,resolution=a.resolution,clearing_policy=policy)
    write_json(stage/'scene-recipe.json',recipe)
    print('WOODLAND_AREA_KM2',woods.area/1e6,'zones',len(recipe['landscape']['reference_woodland']['forest_zone_ids']),flush=True)
    old_models={i['model'] for i in doc['instances'] if 'ground_stems' in i}
    doc=rebuild_forests(recipe,original,doc)
    for item in doc['instances']:
        if 'ground_stems' in item:item['lod_distance']=1400.;item['cull_distance']=50000.
    for id in old_models-{a.forest_asset}:doc['resource_versions'].pop(id,None)
    doc['resource_versions'][a.forest_asset]['manifest_sha256']=sha(ASSETS/'registered'/a.forest_asset/'manifest.json')
    doc['name']=recipe['name'];doc['zones']=recipe['zones']
    doc['fields']=clearing_fields(original.document['fields'],woods,recipe['settlements'])
    doc['budgets']=recipe['budgets'];doc['landscape']=recipe['landscape']
    for name in ['grass','forest','soil']:doc['materials'][name]['color']=recipe['materials'][name]['color']
    doc['recipe_sha256']=hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    shutil.copy2(original.height_file,stage/'terrain.npz');doc['terrain']['file']='terrain.npz'
    doc['terrain']['ground_atlas']=copy_or_build_atlas(original,doc['terrain'],stage)
    baker=Baker(recipe);baker.terrain=BakedTerrain(original.arrays['base'],original.arrays['focus'],doc['terrain']['base'],doc['terrain']['details'][0])
    print('BAKE_OUTER',flush=True);bake_outer_cover(baker,doc,original.arrays,stage)
    regional={**recipe['detail_sample'],'size_m':[x*1000 for x in recipe['focus_area_km']],
              'texture_resolution':a.resolution,'seam_blend_m':2200,
              'material_detail_strength':.65,'macro_source_tile_m':160}
    print('BAKE_REGIONAL',a.resolution,'clearings',len(doc['fields']),flush=True)
    _bake_material(doc,original.arrays,doc['terrain']['details'][0],regional,stage,baker,material_id='regional_1',prefix='regional')
    meta=doc['terrain']['details'][0]
    doc['materials']['regional_1'].update(world_uv=True,uv_origin_north=meta['origin_north'],uv_origin_west=meta['origin_west'])
    for tile in doc['terrain']['details']:tile['material']='regional_1'
    doc['reference_quality']={'stage':'continuous_woodland_candidate','source_map':str(a.source_map.resolve()),'source_map_sha256':sha(a.source_map),
        'generator_sha256':sha(Path(__file__)),'source_tree_count':sum(len(i.get('ground_stems',[])) for i in doc['instances']),
        'forest_area_km2':woods.area/1e6,'clearings':len(doc['fields']),
        'terrain_unchanged':True,'performance_gate':'removed by user','scope':'Authored reference ecology and source-derived appearance, not measured GIS. Requires actual multi-view review.'}
    for key in ['surfaces','mission','roads','rivers','airfields','settlements']:assert doc[key]==original.document[key],key
    for key in ['contact_surfaces','obstacles','water_regions']:assert doc['environment'][key]==original.document['environment'][key],key
    assert sha(stage/'terrain.npz')==original.document['terrain']['sha256']
    def relocate(value,where):
        if isinstance(value,str):return value.replace(str(stage),where)
        if isinstance(value,list):return [relocate(v,where) for v in value]
        if isinstance(value,dict):return {relocate(k,where):relocate(v,where) for k,v in value.items()}
        return value
    version=hashlib.sha256(json.dumps(relocate(doc,'<MAP>'),sort_keys=True,separators=(',',':')).encode()).hexdigest()[:24]
    target=a.output.resolve()/'versions'/version;target.mkdir(parents=True)
    for file in stage.iterdir():
        if file.is_file():shutil.copy2(file,target/file.name)
    doc=relocate(doc,str(target));write_json(target/'generated-map.json',doc)
    BakedScene(target/'generated-map.json')
    from bvr_game.mapcheck import validate
    print('VALIDATE_SPATIAL',flush=True);report=validate(target/'generated-map.json');write_json(target/'spatial-validation.json',report)
    if report['status']!='passed':raise ValueError('Spatial validation failed; candidate retained unpublished')
    write_json(a.output/'candidate.json',{'map':str(target/'generated-map.json'),'sha256':sha(target/'generated-map.json'),
               'terrain_sha256':doc['terrain']['sha256'],'quality':doc['reference_quality'],'status':'built_requires_actual_visual_review'})
    print('WOODLAND_BUILT',target,flush=True)
if __name__=='__main__':main()
