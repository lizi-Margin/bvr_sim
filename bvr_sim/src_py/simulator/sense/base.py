"""
Base classes for sensor systems in BVR air combat simulation.

Provides common functionality for all sensors including standardized interfaces.
Sensor data is now unified in the DataObj class (simulator/data_obj.py).
"""

import numpy as np
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Union, Dict, List

if TYPE_CHECKING:
    from ..aircraft.base import Aircraft
    from ..data_obj import DataObj


class SensorBase(ABC):
    """
    Abstract base class for all sensor systems.

    Sensors are attached to aircraft and update their parent's detection lists.
    Each sensor type manages its own detection logic and data structures.
    """

    def __init__(self, parent: 'Aircraft', **kwargs):
        """
        Initialize sensor system.

        Args:
            parent: The aircraft this sensor is attached to
            **kwargs: Sensor-specific configuration parameters
        """
        self.parent = parent
        self.data_dict: Dict[str, 'DataObj'] = {}

        # from .canvas import PolarCanvas
        # self.canvas = PolarCanvas(
        #     width=64,
        #     height=64,
        #     fov_deg=360,
        # )
    
    def get_data_list(self) -> List['DataObj']:
        dataobj_list = list(self.data_dict.values())
        # sort by distance
        dataobj_list.sort(key=lambda x: np.linalg.norm(x.position - self.parent.position))
        return dataobj_list

    @abstractmethod
    def update(self) -> Dict[str, 'DataObj']:
        return self.get_data()

    def get_data(self) -> Dict[str, 'DataObj']:
        return self.data_dict
    
    # def render(self) -> np.ndarray:
    #     pic = self.canvas.render(
    #         observer=self.parent,
    #         data_dict=self.data_dict,
    #     )
    #     return pic
    
    def log_suffix(self) -> str:
        # see https://www.tacview.net/documentation/acmi/en/
        return ""
        # return "RadarMode=1,RadarRange=10000,RadarHorizontalBeamwidth=7.5,RadarVerticalBeamwidth=7.5\n"
