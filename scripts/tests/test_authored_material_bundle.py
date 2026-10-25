"""Authored material composition must preserve physics and reject stale biomes."""
from argparse import Namespace
import copy,json
import numpy as np
from PIL import Image
import pytest
from bvr_game.content import sha,write_json
from game.tools.author_woodland_materials import compose,geometry


def inputs(tmp_path):
    source=tmp_path/'source';source.mkdir()
    np.savez(source/'terrain.npz',base=np.zeros((2,2)),focus=np.zeros((2,2)))
    (source/'water-footprint.wkb').write_bytes(b'retained-exact-bytes')
    Image.new('RGB',(2,2),(75,100,65)).save(tmp_path/'ground.png')
    material={'color':[1,1,1,1],'tile_m':100,'roughness':.9,'base_color':str(tmp_path/'ground.png'),'base_color_sha256':sha(tmp_path/'ground.png')}
    doc={'name':'fixture','materials':{'source_macro':material},'terrain':{'file':'terrain.npz','sha256':sha(source/'terrain.npz'),
        'base':{'material':'source_macro'},'details':[{'material':'source_macro'}]},
        'instances':[{'id':'retained'}],'surfaces':[],'mission':{'target':[0,0,0]},'roads':[],'rivers':[],'airfields':[],'settlements':[],
        'environment':{'water_regions':[{'id':'water','polygon':[[0,0],[1,0],[0,1]]}],'obstacles':[],'contact_surfaces':[]},
        'resource_versions':{'oak':{'manifest_sha256':'source-grove-hash'}},
        'source_woodland_bake':{'authored_biome':{'sha256':'policy-hash','helper_sha256':'biome-code-hash','policy':{'kind':'authored_reference_woodland'}},'helper_sha256':'footprint-code-hash','half_m':40000}}
    bundle={'geometry':geometry(doc),'materials':{'source_macro':material,'source_focus':material},
        'biome_policy_sha256':'policy-hash','biome_policy':{'kind':'authored_reference_woodland'},'half_m':40000,
        'biome_helper_sha256':'biome-code-hash','footprint_helper_sha256':'footprint-code-hash',
        'large_asset':'oak','large_manifest_sha256':'source-grove-hash','scope':'fixture'}
    write_json(source/'generated-map.json',doc);write_json(source/'scene-recipe.json',{})
    write_json(tmp_path/'materials.json',bundle)
    return Namespace(source=source/'generated-map.json',materials=tmp_path/'materials.json',output=tmp_path/'result'),doc,bundle


def test_composition_preserves_physical_geometry_gameplay_and_source_files(tmp_path):
    args,doc,bundle=inputs(tmp_path);before=sha(args.source)
    compose(args);result=json.loads((args.output/'generated-map.json').read_text())
    for key in ['instances','surfaces','mission','environment','roads','rivers']:assert result[key]==doc[key]
    assert sha(args.output/'terrain.npz')==doc['terrain']['sha256']
    assert (args.output/'water-footprint.wkb').read_bytes()==b'retained-exact-bytes'
    assert result['terrain']['details'][0]['material']=='source_focus'
    assert sha(args.source)==before


@pytest.mark.parametrize('changed',['physics','biome','asset','biome_helper','footprint_helper'])
def test_stale_material_bundle_is_rejected_before_creating_output(tmp_path,changed):
    args,doc,bundle=inputs(tmp_path)
    if changed=='physics':bundle['geometry']['physical_environment_sha256']='different-water'
    if changed=='biome':bundle['biome_policy_sha256']='different-policy'
    if changed=='asset':bundle['large_manifest_sha256']='different-tree-size'
    if changed=='biome_helper':bundle['biome_helper_sha256']='different-code'
    if changed=='footprint_helper':bundle['footprint_helper_sha256']='different-code'
    write_json(args.materials,bundle)
    with pytest.raises(ValueError,match='source height|biomes differ|different source grove|helper versions differ'):compose(args)
    assert not args.output.exists()
