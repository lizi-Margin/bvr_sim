"""Offline, hash-pinned ground-material iteration on an existing baked map."""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.scene_runtime import BakedScene
from bvr_game.worldgen import Baker,BakedTerrain,canonical
from bvr_game.regional_cover import bake_outer_cover
from bvr_game.detail_bake import _bake_material


def reuse_materials(source,material_source,output,*,mix_source_ground=False):
    """Compose reviewed geometry and a bake with identical material masks."""
    geometry=BakedScene(source);appearance=BakedScene(material_source)
    doc=copy.deepcopy(geometry.document);other=appearance.document
    if doc['terrain']['sha256']!=other['terrain']['sha256']:raise ValueError('Material bake belongs to different shared terrain')
    for key in ('fields','roads','rivers','airfields','settlements','zones','landscape'):
        if doc[key]!=other[key]:raise ValueError('Material bake masks differ: '+key)
    for key in ('contact_surfaces','obstacles','water_regions'):
        if doc['environment'][key]!=other['environment'][key]:raise ValueError('Material bake physical environment differs: '+key)
    output.mkdir(parents=True,exist_ok=False)
    doc['materials']=copy.deepcopy(other['materials'])
    mixtures={}
    if mix_source_ground:
        from bvr_game.ground_color_mix import mix_ground_images
        used={doc['terrain']['base']['material'],*[t['material'] for t in doc['terrain']['details']]}
        for id in sorted(used):
            old=geometry.document['materials'][id];new=doc['materials'][id]
            if old.get('base_color_sha256')==new.get('base_color_sha256'):continue
            target=output/(id+'-mixed-albedo.png')
            mixtures[id]=mix_ground_images(Path(old['base_color']),Path(new['base_color']),target,doc,id)
            new['base_color']=str(target.resolve());new['base_color_sha256']=sha(target)
    recipe=json.loads((source.parent/'scene-recipe.json').read_text())
    material_recipe=json.loads((material_source.parent/'scene-recipe.json').read_text())
    recipe['materials']=copy.deepcopy(material_recipe['materials'])
    doc['offline_material_composition']={'geometry_map':str(source.resolve()),'geometry_sha256':sha(source),
        'material_map':str(material_source.resolve()),'material_sha256':sha(material_source),'tool_sha256':sha(__file__),
        'scope':'Identical terrain/land-use masks required. Geometry,all tree positions,contacts and mission retained;material images reused without rebaking.'}
    if mixtures:doc['offline_material_composition']['ground_albedo_mix']=mixtures
    recipe['offline_material_composition']=doc['offline_material_composition']
    doc['recipe_sha256']=hashlib.sha256(canonical(recipe)).hexdigest()
    shutil.copy2(geometry.height_file,output/geometry.height_file.name);doc['terrain']['file']=geometry.height_file.name
    if doc['terrain'].get('ground_atlas'):doc['terrain']['ground_atlas']['file']=str((source.parent/doc['terrain']['ground_atlas']['file']).resolve())
    for key in ('instances','surfaces','environment','mission','fields','roads','rivers','airfields','settlements','zones','chunks'):
        if doc[key]!=geometry.document[key]:raise ValueError('Material composition changed '+key)
    # Legacy source metadata can predate an extension. Report the saved
    # source slots actually present, without touching any instance geometry.
    groves=[i for i in doc['instances'] if 'ground_stems' in i]
    if groves and 'forest_representation' in doc:
        doc['forest_representation']['unused_shared_mesh_slots']=sum(i['independent_source_layout']['source_slots']-len(i['ground_stems']) for i in groves)
    write_json(output/'scene-recipe.json',recipe);write_json(output/'generated-map.json',doc)
    BakedScene(output/'generated-map.json')
    write_json(output/'variant-report.json',{'map_sha256':sha(output/'generated-map.json'),'source_map_sha256':sha(source),
        'material_map_sha256':sha(material_source),'height_sha256':doc['terrain']['sha256'],
        'full_geometry_environment_mission_unchanged':True,'status':'requires_actual_native_visual_review'})
    print('MATERIAL_COMPOSITION_COMPLETE',output/'generated-map.json',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True)
    choice=p.add_mutually_exclusive_group(required=True)
    choice.add_argument('--policy',type=Path);choice.add_argument('--reuse-materials',type=Path,help='Reuse an existing bake only when shared terrain and every land-use mask match')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resolution',type=int,default=8192)
    p.add_argument('--mix-source-ground',action='store_true',help='With --reuse-materials,spatially mix source/reused ground albedos in linear light')
    a=p.parse_args()
    if a.reuse_materials:return reuse_materials(a.source,a.reuse_materials,a.output,mix_source_ground=a.mix_source_ground)
    if a.mix_source_ground:p.error('--mix-source-ground requires --reuse-materials')
    scene=BakedScene(a.source);doc=copy.deepcopy(scene.document)
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text());policy=json.loads(a.policy.read_text())
    if not 512<=a.resolution<=8192:raise ValueError('Resolution must be512..8192')
    for role,material in policy['materials'].items():
        if role not in ('grass','farmland','forest','soil','rock'):raise ValueError('Ground material role required')
        if material.get('provider')!='local_texture':raise ValueError('Explicit local_texture declarations required')
        for slot in ('base_color','normal','roughness_map'):
            if sha(material[slot])!=material[slot+'_sha256']:raise ValueError('Source material hash changed: '+slot)
        doc['materials'][role]=copy.deepcopy(material);recipe['materials'][role]=copy.deepcopy(material)
    recipe['name']=doc['name']=policy['name']
    repairs=[]
    for role,ids in list(recipe['asset_roles'].items()):
        if isinstance(ids,list) and ids and all(isinstance(v,str) and len(v)==1 for v in ids):
            joined=''.join(ids)
            if joined not in doc['resource_versions']:raise ValueError('Split source role cannot be resolved against frozen map: '+role)
            repairs.append({'role':role,'source':ids,'restored':joined});recipe['asset_roles'][role]=joined
    if repairs:recipe['authoring_role_repairs']=repairs
    # Derived geometry candidates can replace a source role while retaining an
    # older authoring recipe. Carry only already-frozen map manifest hashes
    # into this new recipe; never approve an arbitrary changed local asset.
    pins=recipe.setdefault('resource_use',{}).setdefault('asset_manifest_sha256',{})
    for ids in recipe['asset_roles'].values():
        for id in ids if isinstance(ids,list) else [ids]:
            expected=doc['resource_versions'].get(id,{}).get('manifest_sha256')
            if expected:
                if sha(ASSETS/'registered'/id/'manifest.json')!=expected:raise ValueError('Frozen source manifest changed: '+id)
                pins[id]=expected
    recipe['offline_ground_policy']={'file':str(a.policy.resolve()),'sha256':sha(a.policy),'source_sha256':sha(a.source),'tool_sha256':sha(__file__)}
    a.output.mkdir(parents=True,exist_ok=False);baker=Baker(recipe);arrays=scene.arrays
    baker.terrain=BakedTerrain(arrays['base'],arrays['focus'],doc['terrain']['base'],doc['terrain']['details'][0]);baker.fields=doc['fields']
    print('GROUND_BAKE_OUTER',flush=True);bake_outer_cover(baker,doc,arrays,a.output)
    spec={**recipe['detail_sample'],'size_m':[x*1000 for x in recipe['focus_area_km']],
        'texture_resolution':a.resolution,'seam_blend_m':recipe['landscape']['outer_surface']['focus_blend_m'],
        'material_detail_strength':policy.get('macro_detail_strength',.65),'macro_source_tile_m':160}
    print('GROUND_BAKE_REGIONAL',flush=True)
    _bake_material(doc,arrays,doc['terrain']['details'][0],spec,a.output,baker,material_id='regional_1',prefix='regional')
    meta=doc['terrain']['details'][0]
    doc['materials']['regional_1'].update(world_uv=True,uv_origin_north=meta['origin_north'],uv_origin_west=meta['origin_west'],repeat_detail=True)
    doc['materials']['outer_1']['repeat_detail']=True
    for tile in doc['terrain']['details']:tile['material']='regional_1'
    shutil.copy2(scene.height_file,a.output/scene.height_file.name);doc['terrain']['file']=scene.height_file.name
    if doc['terrain'].get('ground_atlas'):doc['terrain']['ground_atlas']['file']=str((a.source.parent/doc['terrain']['ground_atlas']['file']).resolve())
    for key in ('instances','surfaces','environment','mission','fields','roads','rivers','airfields','settlements','zones','chunks'):
        if doc[key]!=scene.document[key]:raise ValueError('Material iteration changed '+key)
    if sha(a.output/scene.height_file.name)!=scene.document['terrain']['sha256']:raise ValueError('Physical terrain changed')
    doc['recipe_sha256']=hashlib.sha256(canonical(recipe)).hexdigest();doc['offline_ground_policy']=recipe['offline_ground_policy']
    write_json(a.output/'scene-recipe.json',recipe);write_json(a.output/'ground-policy.json',policy);write_json(a.output/'generated-map.json',doc)
    write_json(a.output/'variant-report.json',{'map_sha256':sha(a.output/'generated-map.json'),'source_map_sha256':sha(a.source),
        'height_sha256':doc['terrain']['sha256'],'full_geometry_environment_mission_unchanged':True,
        'status':'requires_actual_native_visual_review','scope':'Offline material iteration only. No reference-match or playable acceptance claim.'})
    print('GROUND_BAKE_COMPLETE',a.output/'generated-map.json',flush=True)

if __name__=='__main__':main()
