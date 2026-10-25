import json
import numpy as np
import pytest
from PIL import Image
from bvr_game.content import sha
from bvr_game.open_ground import OpenGround


def test_real_ground_prefilters_in_linear_light_and_is_world_deterministic(tmp_path):
    policy={'kind':'source_grass_dry_mix','seed':212}
    for role in ['green','dry']:
        image=np.zeros((2,2,3),dtype=np.uint8)
        if role=='dry':image[0]=255
        file=tmp_path/(role+'.png');Image.fromarray(image).save(file)
        policy[role]={k:str(file) for k in ['base_color','normal','roughness_map']}
        policy[role].update({k+'_sha256':sha(file) for k in ['base_color','normal','roughness_map']})
    file=tmp_path/'policy.json';file.write_text(json.dumps(policy));ground=OpenGround(file)
    np.testing.assert_allclose(ground.means['dry'],[.5,.5,.5],atol=1e-12)
    p=np.random.default_rng(212).uniform(-40000,40000,(600,2));whole=ground.color_linear(*p.T)
    np.testing.assert_array_equal(whole,np.concatenate([ground.color_linear(*s.T) for s in np.array_split(p,7)]))
    assert np.isfinite(whole).all() and 0<whole.min()<whole.max()<1
    (tmp_path/'dry.png').write_bytes(b'changed-source')
    with pytest.raises(ValueError,match='source changed'):OpenGround(file)

def test_soil_mosaic_has_world_consistent_variation_and_pinned_inputs(tmp_path):
    policy={'kind':'source_grass_dry_mix','seed':267,'variation':{'dry_range':[.12,.92],
        'dry_scale_m':120,'soil_max':.35,'soil_scale_m':70,'brightness_range':[.65,1.35],
        'brightness_scale_m':240,'mottle_strength':.18,'mottle_scale_m':35}}
    for role,color in [('green',(80,120,40)),('dry',(180,130,80)),('soil',(130,70,30))]:
        image=tmp_path/(role+'.png');Image.new('RGB',(3,3),color).save(image)
        policy[role]={slot:str(image) for slot in ['base_color','normal','roughness_map']}
        policy[role].update({slot+'_sha256':sha(image) for slot in ['base_color','normal','roughness_map']})
    file=tmp_path/'policy.json';file.write_text(json.dumps(policy));ground=OpenGround(file)
    points=np.random.default_rng(267).uniform(-40000,40000,(2000,2));whole=ground.color_linear(*points.T)
    np.testing.assert_array_equal(whole,np.concatenate([ground.color_linear(*part.T) for part in np.array_split(points,9)]))
    assert whole.std()>0.01 and 0<whole.min()<whole.max()<1
    (tmp_path/'soil.png').write_bytes(b'changed-soil')
    with pytest.raises(ValueError,match='source changed'):OpenGround(file)
