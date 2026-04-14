import os
from pathlib import Path


ENV_RESOURCE_DIR = "BVR_SIM_RESOURCE_DIR"
ENV_JSBSIM_DIR = "JSBSIM_DIR"


def _package_root() -> Path:
    return Path(__file__).resolve().parent


def _default_resource_dir() -> Path:
    return _package_root() / "resources"


def get_resource_dir() -> Path:
    env_value = os.environ.get(ENV_RESOURCE_DIR)
    if env_value:
        return Path(env_value).expanduser().resolve()

    default_dir = _default_resource_dir()
    if default_dir.is_dir():
        return default_dir

    raise FileNotFoundError(
        f"Could not locate BVR Sim resources. Checked '{default_dir}' and env var {ENV_RESOURCE_DIR}."
    )


def get_resource_path(*parts: str) -> Path:
    return get_resource_dir().joinpath(*parts)


def get_jsbsim_dir() -> Path:
    env_value = os.environ.get(ENV_JSBSIM_DIR)
    if env_value:
        return Path(env_value).expanduser().resolve()

    resource_jsbsim_dir = get_resource_dir() / "jsbsim"
    if resource_jsbsim_dir.is_dir():
        return resource_jsbsim_dir

    raise FileNotFoundError(
        f"Could not locate JSBSim assets. Checked '{resource_jsbsim_dir}' and env var {ENV_JSBSIM_DIR}."
    )


def configure_runtime_environment() -> Path:
    resource_dir = get_resource_dir()
    os.environ.setdefault(ENV_RESOURCE_DIR, str(resource_dir))
    os.environ.setdefault(ENV_JSBSIM_DIR, str(get_jsbsim_dir()))
    os.environ.setdefault("JSBSIM_DEBUG", "0")
    return resource_dir
