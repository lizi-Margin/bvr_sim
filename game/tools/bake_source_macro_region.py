"""Derive a saved map with a higher resolution retained-source ground region."""
from pathlib import Path
import argparse,copy,json,shutil,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.source_macro import SourceMacro,to_srgb


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','class-report','macro-report','texture-report','output']:p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--resolution',type=int,default=8192)
    p.add_argument('--repeat-detail',action='store_true',help='Apply the existing explicitly configured generic ground detail;not the original landclass shader')
    a=p.parse_args()
    if not 512<=a.resolution<=16384:raise ValueError('Region resolution must be512..16384')
    scene=BakedScene(a.source);original=scene.document;doc=copy.deepcopy(original)
    if not doc['terrain'].get('bound_macro_only'):raise ValueError('Requires explicit source macro terrain')
    focus=doc['terrain']['details'][0];origin_n=focus['origin_north'];origin_w=focus['origin_west']
    size_n=(focus['columns']-1)*focus['spacing'];size_w=(focus['rows']-1)*focus['spacing']
    if size_n!=size_w:raise ValueError('World-aligned source region must be square')
    for tile in doc['terrain']['details']:
        if tile['origin_north']<origin_n or tile['origin_west']<origin_w or tile['origin_north']+(tile['columns']-1)*tile['spacing']>origin_n+size_n or tile['origin_west']+(tile['rows']-1)*tile['spacing']>origin_w+size_w:
            raise ValueError('A detail tile leaves the focus color region')
    sampler=SourceMacro(a.class_report,a.macro_report,a.texture_report)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    color=np.empty((a.resolution,a.resolution,3),dtype=np.uint8)
    north=origin_n+(np.arange(a.resolution)+.5)*size_n/a.resolution
    for first in range(0,a.resolution,32):
        west=origin_w+(np.arange(first,min(first+32,a.resolution))+.5)*size_w/a.resolution
        n,w=np.meshgrid(north,west);color[first:first+len(west)]=to_srgb(sampler.sample_linear(n,w))
        if first%512==0:print('SOURCE_REGION_ROWS',first,'/',a.resolution,flush=True)
    path=out/'source-focus-albedo-nwu.png';Image.fromarray(color).save(path)
    material=copy.deepcopy(doc['materials']['source_macro'])
    material.update(id='retained-source-focus',base_color=str(path),base_color_sha256=sha(path),tile_m=size_n,
        uv_origin_north=origin_n,uv_origin_west=origin_w,repeat_detail=a.repeat_detail)
    doc['materials']['source_focus']=material
    for tile in doc['terrain']['details']:tile['material']='source_focus'
    # All geometry, physical environment, gameplay and exact height bytes stay
    # unchanged. A color-region binding is presentation data only.
    for key in ['instances','surfaces','mission','environment','roads','rivers','airfields','settlements']:
        assert doc[key]==original[key],key
    shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    doc['source_region_bake']={'source_map':str(a.source.resolve()),'source_map_sha256':sha(a.source),
        'tool_sha256':sha(__file__),'helper_sha256':sha(ROOT/'bvr_game/source_macro.py'),
        'origin_nwu':[origin_n,origin_w],'extent_m':size_n,'resolution':a.resolution,'metres_per_texel':size_n/a.resolution,
        'color_sha256':sha(path),'source':sampler.provenance,'generic_repeat_detail':a.repeat_detail,
        'scope':'Original class colors/UV/retained quantized weights sampled at regional resolution in linear light. Flat normal/roughness retained;optional generic detail is an authored approximation. Not the full original shader or new source geometry.'}
    write_json(out/'generated-map.json',doc)
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text());recipe['source_region_bake']=doc['source_region_bake']
    write_json(out/'scene-recipe.json',recipe)
    if (a.source.parent/'water-footprint.wkb').exists():shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb')
    BakedScene(out/'generated-map.json')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),
        'region':doc['source_region_bake'],'status':'requires_actual_visual_review'})
    print('SOURCE_REGION_COMPLETE',out/'generated-map.json',flush=True)
if __name__=='__main__':main()
