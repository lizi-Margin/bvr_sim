"""
Sensor systems for BVR air combat simulation.

Provides modular sensor implementations with realistic noise modeling:
- Radar: Active radar detection
- RWS: Radar Warning System (RWR + MWS)
- SADatalink: Situation Awareness datalink (AWACS/GCI)

All sensor detections use the unified DataObj class (from simulator/data_obj.py)
for consistent noise modeling and Tacview rendering support.
"""

from .base import SensorBase
from .radar import Radar
from .rws import RadarWarningSystem, MissileWarningSystem
from .awacs import SADatalink

# DataObj is imported from parent module
from ..data_obj import DataObj

__all__ = [
    # Base class
    'SensorBase',

    # Sensor systems
    'Radar',
    'RadarWarningSystem',
    'MissileWarningSystem',
    'SADatalink',

    # Unified data object
    'DataObj',
]
