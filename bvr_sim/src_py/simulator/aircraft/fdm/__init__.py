"""Flight Dynamics Models for BVR 3D simulator.

This package provides pluggable flight dynamics models for aircraft
simulation in the BVR 3D environment. The architecture allows swapping
between different fidelity levels without changing the rest of the
simulation.

Available FDMs:
- SimpleFDM: Fast, simplified physics (compatible with original F16)
- JSBSimFDM: High-fidelity physics using JSBSim (placeholder)
"""

from .base import BaseFDM
from .simple_fdm import SimpleFDM
from .jsbsim_fdm import JSBSimFDM

__all__ = ['BaseFDM', 'SimpleFDM', 'JSBSimFDM']