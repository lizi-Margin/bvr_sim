import hashlib,json
import pytest
from bvr_game.native_runtime import configure_native_core

def setup_config(tmp_path):
    binary=tmp_path/'core.pyd';binary.write_bytes(b'fixed game core')
    config=tmp_path/'runtime.json'
    config.write_text(json.dumps({'schema_version':1,'core_module':'core.pyd',
        'core_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()}),encoding='utf8')
    return config,binary

def test_game_core_is_pinned_before_simulator_import(tmp_path):
    config,binary=setup_config(tmp_path);env={}
    assert configure_native_core(config,environ=env,modules={})==binary
    assert env['BVR_SIM_CPP_PATH']==str(binary)
    binary.write_bytes(b'changed core')
    with pytest.raises(ValueError,match='hash changed'):
        configure_native_core(config,environ={},modules={})

def test_explicit_override_and_embedded_simulator_are_preserved(tmp_path):
    config,_=setup_config(tmp_path);config.write_text('invalid JSON',encoding='utf8')
    env={'BVR_SIM_CPP_PATH':'experiment.pyd'}
    assert configure_native_core(config,environ=env,modules={}) is None
    assert env=={'BVR_SIM_CPP_PATH':'experiment.pyd'}
    env={}
    assert configure_native_core(config,environ=env,modules={'bvr_sim.bvr_env_cpp':object()}) is None
    assert env=={}

def test_absent_configuration_keeps_portable_fallback(tmp_path):
    env={}
    assert configure_native_core(tmp_path/'absent.json',environ=env,modules={}) is None
    assert env=={}
