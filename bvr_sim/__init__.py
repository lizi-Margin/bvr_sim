"""
BVR Sim - 3D Beyond Visual Range Air Combat Environment

Clean, modular 3D BVR environment with:
- Full 3D aircraft physics with altitude dynamics
- Realistic missile guidance (AIM-120C parameters)
- Pluggable observation space system
- ACMI Tacview rendering
- Modular reward components
"""

__version__ = "0.4.6"

from .resource_paths import configure_runtime_environment

configure_runtime_environment()

from .bvr_env import BVR3DEnv, make_bvr3d_env
from .bvr_env_cpp import BVR3DEnvCpp  ## C++ version for faster training and more features

all_envs = [BVR3DEnv, BVR3DEnvCpp]


"""
Wrappers for RL frameworks
"""
# for MARLBenchmark (on-policy, off-policy):
# compatible fork: https://github.com/lizi-Margin/off-policy
# original: https://github.com/marlbenchmark
# from .env_marlbenchmark import BVRSimEnvMarlBenchmark, MultiAgentEnvWrapper

# for HARL
# compatible fork: https://github.com/lizi-Margin/HARL4BVRSim
# original: https://github.com/PKU-MARL/HARL
# from .env_harl import BVRSimEnv, HARLLogger

# for UHRL: https://github.com/lizi-Margin/UHRL
# from .env_wrapper import BVR3DWrapper, make_env, ScenarioConfig
