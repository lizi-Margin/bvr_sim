from typing import Optional
import numpy as np
from .simple_opponents import (
    BaseOpponent3D,
    RandomOpponent3D,
    SimpleOpponent3D,
    MadOpponent3D,
)
from .tactical_opponent import TacticalOpponent3D
from .slamraam_policy import SLAMRAAMPolicy

# Opponent factory
OPPONENT_CLASSES_3D = {
    'random': RandomOpponent3D,
    'simple': SimpleOpponent3D,
    'mad': MadOpponent3D,
    'tactical': TacticalOpponent3D,
}


def create_opponent(opponent_type: Optional[str] = None) -> BaseOpponent3D:
    """
    Create a 3D opponent strategy instance

    Args:
        opponent_type: Type of opponent ('random', 'simple', 'tactical')
                      If None, randomly selects one

    Returns:
        BaseOpponent3D: An instance of the selected opponent strategy
    """
    if opponent_type is None:
        # Randomly select opponent type
        opponent_type = np.random.choice(list(OPPONENT_CLASSES_3D.keys()))

    if opponent_type not in OPPONENT_CLASSES_3D:
        raise ValueError(f"Unknown opponent type: {opponent_type}. "
                        f"Available types: {list(OPPONENT_CLASSES_3D.keys())}")

    opponent_class = OPPONENT_CLASSES_3D[opponent_type]
    opponent = opponent_class()
    return opponent


def create_random_opponent(types=None) -> BaseOpponent3D:
    """Create a randomly selected opponent"""
    if types is None:
        return create_opponent(None)
    return create_opponent(np.random.choice(types))


def create_tactical_opponent() -> BaseOpponent3D:
    """Create a tactical opponent (for testing RL agents)"""
    return create_opponent('tactical')
