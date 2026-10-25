"""Select the game core before importing simulator bindings in a fresh process."""
from pathlib import Path
import hashlib,json,os,sys

DEFAULT_CONFIG=Path(__file__).resolve().parents[1]/'game/native-runtime.json'

def configure_native_core(config=DEFAULT_CONFIG,*,environ=None,modules=None):
    environ=os.environ if environ is None else environ
    modules=sys.modules if modules is None else modules
    # Explicit experiment overrides and an already embedded simulator keep ownership.
    if environ.get('BVR_SIM_CPP_PATH') or 'bvr_sim.bvr_env_cpp' in modules:return None
    config=Path(config)
    if not config.is_file():return None
    data=json.loads(config.read_text(encoding='utf8'))
    if data.get('schema_version')!=1:raise ValueError('Unsupported game native runtime configuration')
    file=Path(data['core_module'])
    if not file.is_absolute():file=config.parent/file
    file=file.resolve()
    if hashlib.sha256(file.read_bytes()).hexdigest()!=data['core_sha256']:
        raise ValueError('Game native core hash changed: '+str(file))
    environ['BVR_SIM_CPP_PATH']=str(file)
    return file
