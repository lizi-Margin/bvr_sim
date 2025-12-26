"""
BVR 3D - 3D Beyond Visual Range Air Combat Environment

Clean, modular 3D BVR environment with:
- Full 3D aircraft physics with altitude dynamics
- Realistic missile guidance (AIM-120C parameters)
- Pluggable observation space system
- ACMI Tacview rendering
- Modular reward components
"""

from .env_wrapper import ScenarioConfig, make_env, BVR3DWrapper
from .bvr_env import BVR3DEnv, make_bvr3d_env
from .simulator import Aircraft, Missile, Radar
from .observation_space import (
    ObservationSpace,
    CompactObsSpace,
    ExtendedObsSpace,
    create_observation_space
)
from .reward.reward_components import (
    RewardComponent,
    RewardManager,
    EngageEnemyReward,
    AltitudeAdvantageReward,
    SafeAltitudeReward,
    MissileLaunchReward,
    MissileResultReward,
    MissileEvasionReward,
    SpeedReward,
    SurvivalReward,
    WinLossReward,
    create_default_reward_manager
)
from .reward.reward_visualization import RewardVisualizer
from .baseline_opponents import (
    BaseOpponent3D,
    RandomOpponent3D,
    SimpleOpponent3D,
    TacticalOpponent3D,
    create_opponent,
    create_random_opponent,
    create_tactical_opponent
)

__all__ = [
    # Environment
    'ScenarioConfig',
    'make_env',
    'BVR3DWrapper',
    'BVR3DEnv',
    'make_bvr3d_env',

    # Simulator
    'Aircraft',
    'Missile',
    'Radar',

    # Observation spaces
    'ObservationSpace',
    'CompactObsSpace',
    'ExtendedObsSpace',
    'create_observation_space',

    # Reward components
    'RewardComponent',
    'RewardManager',
    'EngageEnemyReward',
    'AltitudeAdvantageReward',
    'SafeAltitudeReward',
    'MissileLaunchReward',
    'MissileResultReward',
    'MissileEvasionReward',
    'SpeedReward',
    'SurvivalReward',
    'WinLossReward',
    'create_default_reward_manager',

    # Reward visualization
    'RewardVisualizer',

    # Opponents
    'BaseOpponent3D',
    'RandomOpponent3D',
    'SimpleOpponent3D',
    'TacticalOpponent3D',
    'create_opponent',
    'create_random_opponent',
    'create_tactical_opponent'
]
