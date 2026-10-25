"""Offline material-only map iteration using hash-checked local War Thunder textures.

Keep the complete source terrain, trees, contacts, water geometry and missions.
This does not remove distant geometry or generate content during gameplay.
"""
from pathlib import Path
import argparse,copy,hashlib,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from PIL import Image
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.scene_runtime import BakedScene
from bvr_game.worldgen import Baker,BakedTerrain,canonical
from bvr_game.detail_bake import _bake_material
from bvr_game.regional_cover import bake_outer_cover

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--textures',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--resolution',type=int,default=8192)
    p.add_argument('--grass-texture',default='air_smolensk_meadows_a',
        choices=['air_smolensk_meadows_a','air_smolensk_meadows_b','air_smolensk_meadows_b2'])
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    scene=BakedScene(a.source);doc=copy.deepcopy(scene.document)
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text(encoding='utf8'))
    imported=json.loads(a.textures.read_text(encoding='utf8'))
    def texture(pack,name):
        row=next(r for r in imported['textures'] if r['status']=='decoded' and Path(r['source']).parent.name==pack and Path(r['source']).stem==name)
        file=Path(row['png']);assert sha(file)==row['png_sha256'],'Imported source image changed'
        return row,file
    normal=a.output/'flat-normal.png';rough=a.output/'flat-roughness.png'
    Image.new('RGB',(2,2),(128,128,255)).save(normal);Image.new('L',(2,2),230).save(rough)
    choices={'forest':('landclass_color_and_detail','forest_land_tex_d',512),
             'grass':('air_smolensk',a.grass_texture,1024),
             'farmland':('air_smolensk','air_smolensk_fields_a',1024)}
    sources={}
    for role,(pack,name,tile) in choices.items():
        row,file=texture(pack,name);material=copy.deepcopy(doc['materials'][role])
        material.update(provider='local_texture',id='wt-'+name,base_color=str(file),base_color_sha256=sha(file),
            normal=str(normal.resolve()),normal_sha256=sha(normal),roughness_map=str(rough.resolve()),roughness_map_sha256=sha(rough),
            tile_m=tile,macro_tile_m=tile,color=[1,1,1,1],roughness=.9,
            license='user-owned-local-War-Thunder-resource',distribution_allowed=False,
            source_url='local://WarThunder/content/base/res/'+pack+'.dxp.bin',
            source_texture=row,approximation='Unmodified decoded source albedo. Authored world tiling; flat normal and roughness0.9, not a reconstruction of the Dagor material shader.')
        if role=='forest':material['aerial_canopy_albedo']=True
        material.pop('canopy_proxy',None);doc['materials'][role]=material;recipe['materials'][role]=copy.deepcopy(material)
        sources[role]={'file':str(file),'sha256':sha(file),'world_tile_m':tile}
    for field in doc['fields']:field['color']=[1,1,1,1]
    recipe['name']=doc['name']=doc['name']+'_wt_materials'
    recipe['resource_use']['mode']='local_private'
    recipe['offline_material_variant']={'tool':'game/tools/build_wt_material_variant.py','source_map':str(a.source.resolve()),
        'tool_sha256':sha(Path(__file__)),'texture_resolution':a.resolution,'grass_texture':a.grass_texture,
        'source_map_sha256':sha(a.source),'texture_import_report':str(a.textures.resolve()),'texture_import_report_sha256':sha(a.textures),
        'sources':sources,'field_tints':'Neutral. Source photos provide their own color variation.',
        'scope':'Material-only iteration; all source geometry and core environment preserved.'}
    baker=Baker(recipe);arrays=scene.arrays
    baker.terrain=BakedTerrain(arrays['base'],arrays['focus'],doc['terrain']['base'],doc['terrain']['details'][0]);baker.fields=doc['fields']
    print('WT_MATERIAL_STAGE outer',flush=True);bake_outer_cover(baker,doc,arrays,a.output)
    spec={**recipe['detail_sample'],'size_m':[x*1000 for x in recipe['focus_area_km']],
        'texture_resolution':a.resolution,'seam_blend_m':recipe['landscape']['outer_surface']['focus_blend_m'],
        'material_detail_strength':1.,'macro_source_tile_m':160}
    print('WT_MATERIAL_STAGE regional',flush=True)
    _bake_material(doc,arrays,doc['terrain']['details'][0],spec,a.output,baker,material_id='regional_1',prefix='regional')
    doc['regional_surface']['material_bake'].update(material_world_tiles_m={role:row['world_tile_m'] for role,row in sources.items()},
        macro_source_note='Area-filtered decoded local source albedos at explicitly recorded role tile sizes; no additional runtime microtexture.',
        normal_roughness_note='Selected WT albedos use flat normal and roughness0.9 approximations; unmodified legacy soil/pavement retain their registered maps.')
    meta=doc['terrain']['details'][0]
    doc['materials']['regional_1'].update(world_uv=True,uv_origin_north=meta['origin_north'],uv_origin_west=meta['origin_west'],repeat_detail=False)
    doc['materials']['outer_1']['repeat_detail']=False
    # Use the exact same regional image/UV phase for every nested height tile.
    for tile in doc['terrain']['details']:tile['material']='regional_1'
    shutil.copy2(scene.height_file,a.output/scene.height_file.name);doc['terrain']['file']=scene.height_file.name
    if doc['terrain'].get('ground_atlas'):
        doc['terrain']['ground_atlas']['file']=str((a.source.parent/doc['terrain']['ground_atlas']['file']).resolve())
    for id,version in doc['resource_versions'].items():version['manifest_sha256']=sha(ASSETS/'registered'/id/'manifest.json')
    doc['recipe_sha256']=hashlib.sha256(canonical(recipe)).hexdigest();doc['material_variant']=recipe['offline_material_variant']
    for key in ('instances','surfaces','environment','mission','roads','rivers','airfields','settlements','zones','chunks'):
        assert doc[key]==scene.document[key],key+' changed during material-only bake'
    assert sha(a.output/scene.height_file.name)==scene.document['terrain']['sha256']
    write_json(a.output/'scene-recipe.json',recipe);write_json(a.output/'generated-map.json',doc)
    write_json(a.output/'variant-report.json',{'status':'baked_pending_actual_render_review','source_map_sha256':sha(a.source),
        'map_sha256':sha(a.output/'generated-map.json'),'terrain_sha256':doc['terrain']['sha256'],
        'complete_source_geometry_environment_mission_equal':True,'instances':len(doc['instances']),'sources':sources,
        'scope':'No visual reference-match claim until actual whole-map native rendering is inspected.'})
    print('WT_MATERIAL_VARIANT_COMPLETE',a.output/'generated-map.json',flush=True)

if __name__=='__main__':main()
