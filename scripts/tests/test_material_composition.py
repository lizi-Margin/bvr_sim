"""Material-bake reuse must reject genuinely different saved terrain or masks."""
import copy,json
import numpy as np
import pytest
from bvr_game.content import sha,write_json
from game.tools.rebake_map_materials import reuse_materials


def saved_map(folder,*,height=0.,color=(.2,.4,.1),field='same'):
    folder.mkdir()
    np.savez(folder/'terrain.npz',base=np.full((2,2),height,dtype=np.float32),focus=np.full((2,2),height,dtype=np.float32))
    doc={'name':folder.name,'terrain':{'file':'terrain.npz','sha256':sha(folder/'terrain.npz')},
         'materials':{'grass':{'color':list(color)}},'mission':{'target':[0,0,0]},
         'instances':[{'id':'retained','category':'prop'}],'surfaces':[],'chunks':{'0:0':['retained']},
         'fields':[field],'roads':[],'rivers':[],'airfields':[],'settlements':[],'zones':[],'landscape':{},
         'environment':{'contact_surfaces':[],'obstacles':[],'water_regions':[],'decorative_instance_ids':['retained']}}
    write_json(folder/'generated-map.json',doc)
    write_json(folder/'scene-recipe.json',{'materials':copy.deepcopy(doc['materials'])})
    return folder/'generated-map.json',doc


def test_saved_material_reuse_preserves_geometry_and_source_files(tmp_path):
    source,geometry=saved_map(tmp_path/'geometry')
    material,appearance=saved_map(tmp_path/'appearance',color=(.6,.5,.3))
    before=(sha(source),sha(material));output=tmp_path/'composed'
    reuse_materials(source,material,output)
    result=json.loads((output/'generated-map.json').read_text())
    assert result['materials']==appearance['materials']
    for key in ['instances','surfaces','chunks','environment','mission']:assert result[key]==geometry[key]
    assert sha(output/'terrain.npz')==geometry['terrain']['sha256']
    assert (sha(source),sha(material))==before


@pytest.mark.parametrize('difference',['height','field'])
def test_saved_material_reuse_rejects_different_inputs_before_writing(tmp_path,difference):
    source,_=saved_map(tmp_path/'geometry')
    material,_=saved_map(tmp_path/'appearance',height=10. if difference=='height' else 0.,field='different' if difference=='field' else 'same')
    output=tmp_path/'rejected'
    with pytest.raises(ValueError,match='terrain|masks'):reuse_materials(source,material,output)
    assert not output.exists()
