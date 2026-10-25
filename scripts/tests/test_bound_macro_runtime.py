"""Explicit source regions need no redundant palette or silent material fallback."""
from types import SimpleNamespace
import numpy as np
import pytest
from bvr_game.scene_runtime import BakedScene


def scene(bound=True):
    result=object.__new__(BakedScene);result.ground_atlas=None;result.arrays={}
    result.document={'instances':[],'resource_versions':{},'surfaces':[],
        'materials':{'source':{'color':[1,1,1,1],'roughness':.9,'tile_m':20000}},
        'terrain':{'bound_macro_only':bound,'base':{'material':'source'},'details':[{'material':'source'}]}}
    return result


def configure(result):
    calls=[]
    renderer=SimpleNamespace(register_scene_models=lambda models:None,configure_scene=lambda *args:calls.append(args))
    bindings=SimpleNamespace(SceneMaterial=SimpleNamespace,TERRAIN_BASE_MATERIAL=True,TERRAIN_TILE_MATERIALS=True)
    result.configure(renderer,bindings,'typed-terrain')
    return calls[0]


def test_source_macro_configures_without_loading_any_legacy_palette():
    args=configure(scene())
    assert args[0]=='typed-terrain'
    assert all(args[index]==[] for index in [1,2,6,7])
    assert args[8]==['source','source']


@pytest.mark.parametrize('material',[None,'missing-declaration'])
def test_source_macro_rejects_incomplete_tile_bindings(material):
    result=scene();result.document['terrain']['details'][0]['material']=material
    with pytest.raises(ValueError,match='declared material'):configure(result)


def test_legacy_palette_maps_keep_their_actual_palette_data():
    result=scene(False)
    result.arrays={'landcover':np.array([[3]]),'outer_landcover':np.array([[2]]),
        'macro_color':np.array([[[.1,.2,.3,1]]]),'outer_macro_color':np.array([[[.4,.5,.6,1]]])}
    args=configure(result)
    assert args[1]==[3] and args[6]==[2]
    assert args[2]==[[.1,.2,.3,1]] and args[7]==[[.4,.5,.6,1]]


def test_saved_ground_detail_binds_its_actual_pbr_files(tmp_path):
    from PIL import Image
    from bvr_game.content import sha
    file=tmp_path/'detail.png';Image.new('RGB',(2,2),(90,100,80)).save(file)
    detail={k:str(file) for k in ['base_color','normal','roughness_map']};detail.update({k+'_sha256':sha(file) for k in ['base_color','normal','roughness_map']})
    detail.update(tile_m=2.,mean_linear_luminance=.2,strength=.45)
    result=scene();result.document['materials']['source']['ground_detail']=detail
    material=configure(result)[3][0]
    assert material.detail_color==str(file) and material.detail_normal==str(file) and material.detail_roughness==str(file)
    assert material.detail_tile_m==2. and material.detail_mean_linear==.2 and material.detail_strength==.45
def test_surface_detail_rejects_an_old_renderer_before_mutating_the_scene():
    from types import SimpleNamespace
    import pytest
    from bvr_game.scene_runtime import BakedScene
    scene=object.__new__(BakedScene)
    scene.document={'materials':{'shoulder':{'ground_detail':{'tile_m':2}}},
                    'surfaces':[{'material':'shoulder'}]}
    with pytest.raises(RuntimeError,match='world-detail UV interface'):
        scene.configure(SimpleNamespace(),SimpleNamespace(),None)
