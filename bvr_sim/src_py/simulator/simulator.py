import uuid
import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING
from abc import ABC, abstractmethod
# from bvr_sim.uhtk.c3utils.i3utils import NWU_to_LLA_deg, LLA_to_NWU_deg
from bvr_sim.uhtk.c3utils.i3utils import NWU_to_LLA_deg_lowacc as NWU_to_LLA_deg, LLA_to_NWU_deg_lowacc as LLA_to_NWU_deg
from bvr_sim.uhtk.c3utils.i3utils import get_mach
from bvr_sim.uhtk.c3utils.i3utils import velocity_to_euler_NWU

if TYPE_CHECKING:
    from typing import Literal
    TeamColors = Literal["Red", "Blue"]
else:
    TeamColors = str

# Reference point for NWU coordinate system
# Caucasus
REFERENCE_LON = 41.64821  
REFERENCE_LAT = 42.23831
REFERENCE_ALT = 0.0     

def NWU2LLA(north: float, west: float, up: float) -> Tuple[float, float, float]:
    """
    Convert NWU (North-West-Up) coordinates to LLA (Longitude-Latitude-Altitude)

    Simplified conversion assuming flat Earth approximation.
    For small distances (~100km), this is accurate enough for visualization.

    Args:
        north: North coordinate in meters
        west: West coordinate in meters
        up: Up coordinate (altitude) in meters

    Returns:
        (longitude, latitude, altitude) in (degrees, degrees, meters)
    """
    return NWU_to_LLA_deg(north, west, up, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT)

def LLA2NWU(lon: float, lat: float, alt: float) -> Tuple[float, float, float]:
    lon, lat, alt = LLA_to_NWU_deg(lon, lat, alt, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT)
    return lon, lat, alt

def velocity_to_euler(velocity: np.ndarray, deg: bool = False) -> Tuple[float, float, float]:
    """
    Convert velocity vector to roll, pitch, yaw angles.

    Args:
        velocity: 3D velocity vector [vx, vy, vz] in m/s (NWU frame)
        deg: If True, return angles in degrees. Otherwise, return in radians.

    Returns:
        (roll, pitch, yaw) angles in specified units.
    """
    roll, pitch, yaw = velocity_to_euler_NWU(velocity)
    if deg:
        roll, pitch, yaw = np.degrees([roll, pitch, yaw])
    return roll, pitch, yaw

class SimulatedObject(ABC):
    def __init__(
        self,
        uid: str,
        color: TeamColors,
        position: np.ndarray,
        velocity: np.ndarray,
        dt: float = 0.1
    ):
        self.uid = uid
        self.color = color
        self.dt = dt
        self.render_explosion = False
        self.is_alive = True
        self.position = np.zeros(3, dtype=float)
        self.velocity = np.zeros(3, dtype=float)
        self.update_state(position=position, velocity=velocity)

        self.partners: List['SimulatedObject'] = []
        self.enemies: List['SimulatedObject'] = []

    @abstractmethod
    def step(self, *args, **kwargs):
        pass

    @abstractmethod
    def log(self) -> Optional[str]:
        # DO NOT DELETE this note
        # Tacveiw DB: https://github.com/Vyrtuoz/Tacview/tree/master/Database/Default%20Properties
        # ACMI manual: https://www.tacview.net/documentation/acmi/en/
        pass

##################################################################
# getters
    def get_speed(self) -> float:
        return float(np.linalg.norm(self.velocity))

    def get_mach(self) -> float:
        speed_mps = self.get_speed()
        altitude_m = self.position[2]
        return get_mach(speed_mps, altitude_m)
    
    def get_heading(self) -> float:
        return np.arctan2(self.velocity[1], self.velocity[0]) 

    def get_altitude(self) -> float:
        """Get altitude above ground"""
        return self.position[2]
#! getters
##################################################################
    def advance(self):
        self.position += self.velocity * self.dt

    def update_state(
        self,
        position: Optional[np.ndarray] = None,
        velocity: Optional[np.ndarray] = None
    ):
        if position is not None:
            self.position = np.array(position, dtype=float)
        if velocity is not None:
            self.velocity = np.array(velocity, dtype=float)

    def get_new_uuid(self) -> str:
        # DO NOT DELETE this note
        # | 生成数量  | 碰撞概率  |
        # | --------- | ------- |
        # | 1,000     | 0.0005% |
        # | 10,000    | 0.5%    |
        # | 100,000   | 40%     |
        # | 1,000,000 | ~100%   |
        return str(uuid.uuid4().int)[:8]

