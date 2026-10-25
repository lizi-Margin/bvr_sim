from types import SimpleNamespace
import pytest
from bvr_game.map_library import scene_profile,shadow_cascades
from bvr_game.app import FlightGame


def test_saved_shadow_distances_apply_and_restore_without_core_changes():
    calls=[];game=object.__new__(FlightGame)
    game._base_visual_profile={'ambient':[.1,.2,.3]};game.map_environment=True;game._environment_applied=False
    game.r=SimpleNamespace(BAKED_ENVIRONMENT=True)
    game.renderer=SimpleNamespace(apply_environment=lambda profile:calls.append(('environment',profile)),set_shadow_cascades=lambda values:calls.append(('shadows',values)))
    scene=SimpleNamespace(document={'baked_environment':{'schema_version':1,'profile':{'sun_shadow_cascades_m':[500,4500,10000,24000]}}})
    # Only cloud resolution needs an asset root; use a harmless path here.
    from pathlib import Path
    scene.path=Path('saved-map.json')
    game._apply_scene_environment(scene)
    assert calls[-1]==('shadows',[500,4500,10000,24000])
    game._apply_scene_environment(None)
    assert calls[-1]==('shadows',[8,80,800])
    before=list(calls);scene.document['baked_environment']['profile']['sun_shadow_cascades_m']=[500,100]
    with pytest.raises(ValueError,match='must increase'):game._apply_scene_environment(scene)
    assert calls==before


@pytest.mark.parametrize('values',[[500,500],[0],[50001],[float('nan')],[True],[1,2,3,4,5],'500'])
def test_invalid_cascade_profiles_fail_before_use(values):
    with pytest.raises(ValueError):scene_profile({}, {'baked_environment':{'schema_version':1,'profile':{'sun_shadow_cascades_m':values}}})


@pytest.mark.parametrize('resolution',[0,4097,8192,True,4096.5])
def test_invalid_shadow_atlas_dimensions_are_rejected(resolution):
    with pytest.raises(ValueError):shadow_cascades({'sun_shadow_cascades_m':[500,4500,10000,24000],'sun_shadow_resolution':resolution})
