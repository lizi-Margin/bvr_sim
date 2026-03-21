import math
import numpy as np
from typing import List, Dict, Union, Optional,Tuple


######################################
## Vectors
######################################


class Vector2  : 
    def __init__(self,list2) -> None:
        self.vec = np.array(list2)

    def prod(self,x : float):
    
        self.vec[0] = self.vec[0] *  x
        self.vec[1] =self.vec[1] * x
        return self

    def add(self,v3):
        v3 = v3.vec
        self.vec[0] += v3[0]
        self.vec[1] += v3[1]
        return self


    def __mul__(self, other):
        if isinstance(other, Vector2):
            return Vector2([self.vec[0] * other.vec[0], self.vec[1] * other.vec[1]])
        else:
            return Vector2([self.vec[0] * other, self.vec[1] * other])
    
    def __add__(self, other):
        if isinstance(other, Vector2):
            return Vector2([self.vec[0] + other.vec[0], self.vec[1] + other.vec[1]])
        else:
            return Vector2([self.vec[0] + other, self.vec[1] + other])
    
    def get_np(self):
        return  np.array(self.vec)


########################################################################## 
    def get_list(self):
        return [self.vec[0],self.vec[1]]
    
    def get_prod(self,v3 ):
        v3 = v3.vec
        product = self.vec[0] *  v3[0]
        product +=self.vec[1] * v3[1]
        return product 
    def get_module(self,non_zero =False):
        mo = self.vec[0]* self.vec[0]
        mo += self.vec[1] * self.vec[1]
        if (non_zero == True and mo ==0 ) : mo = 0.0001

        return math.sqrt(mo)

    def get_angle (self,v3):
        ang =  (self.get_prod(v3))*(1/(self.get_module(non_zero=True) * v3.get_module(non_zero = True)))
        if ang >1 :ang =1
        if ang <-1 : ang =-1
        return math.acos(ang) 
    
    def get_Vector3(self,z=0):
        lis = self.vec.tolist()
        return Vector3([lis[0],lis[1],z])




class Vector3 :
    def __init__(self,list3) -> None:
        assert len(list3) == 3, f"Vector3 must have 3 elements, got {len(list3)}: {list3}"
        if hasattr(list3, 'vec') and isinstance(list3.vec, np.ndarray):
            assert len(list3.vec) == 3, f"Vector3 must have 3 elements, got {len(list3.vec)}: {list3.vec}"
            self.vec = np.array(list3.vec)
        elif isinstance(list3, list):
            self.vec = np.array(list3)
        elif isinstance(list3, np.ndarray):
            self.vec = list3.copy()
        # self.vec = np.array(list3, dtype=float)

    def rotate_xyz_self(self,ax,ay,az):
        rotate_matrix =  np.array([[1,0,0],[0,math.cos(ax),-math.sin(ax)], [0,math.sin(ax),math.cos(ax)]])
        rotate_matrix = rotate_matrix @ np.array([[math.cos(ay),0,math.sin(ay)],[0,1,0],[-math.sin(ay),0,math.cos(ay)]])
        rotate_matrix = rotate_matrix @ np.array([[math.cos(az),-math.sin(az),0],[math.sin(az),math.cos(az),0],[0,0,1]])
        self.vec = rotate_matrix @ self.vec
        return self

    def rotate_zyx_self(self,ax,ay,az) :   
        mz = np.array([[math.cos(az),-math.sin(az),0],[math.sin(az),math.cos(az),0],[0,0,1]])
        my =  np.array([[math.cos(ay),0,math.sin(ay)],[0,1,0],[-math.sin(ay),0,math.cos(ay)]])
        mx =  np.array([[1,0,0],[0,math.cos(ax),-math.sin(ax)], [0,math.sin(ax),math.cos(ax)]])
        self.vec = np.dot(mz,np.dot(my,mx)) @ self.vec 
        return self

    def rev_rotate_zyx_self(self,ax,ay,az): 
        mxt =  np.array([[1,    0,                   0],
                                [0,math.cos(ax),math.sin(ax)],
                                [0,-math.sin(ax),math.cos(ax)]])
        myt =  np.array([[math.cos(ay),0,-math.sin(ay)],
                                                [0,            1,           0],
                                                [math.sin(ay),0,math.cos(ay)]])
        mzt = np.array([[math.cos(az),math.sin(az),0],
                                                [-math.sin(az),math.cos(az),0],
                                                [0,          0,            1]])
        self.vec = np.dot(mxt,np.dot(myt,mzt)) @ self.vec
        return self


    def rotate_xyz_fix(self,ax,ay,az):
        rotate_matrix =   np.array([[math.cos(az),-math.sin(az),0],
                                    [math.sin(az),math.cos(az),0],
                                    [0,0,1]])  
        rotate_matrix = rotate_matrix @ np.array([[math.cos(ay),0,math.sin(ay)],
                                                [0,1,0],
                                                [-math.sin(ay),0,math.cos(ay)]])
        rotate_matrix =  rotate_matrix @ np.array([[1,0,0],
                                                [0,math.cos(ax),-math.sin(ax)],
                                                [0,math.sin(ax),math.cos(ax)]])
        self.vec = rotate_matrix @ self.vec
        return self
    def rev_rotate_xyz_fix(self,ax,ay,az):
        rotate_matrix =   np.array([[1,0,0],
                                    [0,math.cos(ax),math.sin(ax)],
                                    [0,-math.sin(ax),math.cos(ax)]])
        rotate_matrix =   rotate_matrix @ np.array([[math.cos(ay),0,-math.sin(ay)],
                                                    [0            ,1,          0],
                                                    [math.sin(ay),0,math.cos(ay)]])
        rotate_matrix =   rotate_matrix @ np.array([[math.cos(az),math.sin(az),0],
                                                    [-math.sin(az),math.cos(az),0],
                                                    [0,           0,           1]])  
        self.vec = rotate_matrix @ self.vec
        return self

    def prod(self,x : float):
    
        self.vec[0] = self.vec[0] *  x
        self.vec[1] =self.vec[1] * x
        self.vec[2] = self.vec[2] *x
        return self
    def add(self,v3 ):
        v3 = v3.vec
        self.vec[0] += v3[0]
        self.vec[1] += v3[1]
        self.vec[2] += v3[2]
        return self

########################################################################## 
    def get_list(self):
        return [self.vec[0],self.vec[1],self.vec[2]]
    
    def get_prod(self,v3 ):
        v3 = v3.vec
        product = self.vec[0] *  v3[0]
        product +=self.vec[1] * v3[1]
        product += self.vec[2] * v3[2]
        return product 
    def get_module(self,non_zero =False):
        # mo = self.vec[0]* self.vec[0]
        # mo += self.vec[1] * self.vec[1]
        # mo += self.vec[2] * self.vec[2]
        # if (non_zero == True and mo ==0 ) : mo = 0.0001
        # return math.sqrt(mo)
        mo = np.linalg.norm(self.vec)
        if (non_zero == True and mo ==0 ) : mo = 1e-4
        return mo
    def get_angle(self, v3, pid_set_zero=-1, pid_sign_dim:int=None):
        if pid_set_zero == -1:
            dot_product = self.get_dot(v3)
            modules_product = self.get_module(non_zero=True) * v3.get_module(non_zero=True)
            ang = dot_product / modules_product
            if ang > 1.0: ang = 1.0
            if ang < -1.0: ang = -1.0
            return math.acos(ang)

        temp = Vector3(v3.get_list())

        if pid_set_zero == 0:
            set_zero_dim = 0
            sign_dim = 1
        elif pid_set_zero == 1:
            set_zero_dim = 1
            sign_dim = 2
        elif pid_set_zero == 2:
            set_zero_dim = 2
            sign_dim = 0
        else:
            raise ValueError("Invalid pid_set_zero value")

        if pid_sign_dim is not None:
            if 0 <= pid_sign_dim < 3:
                sign_dim = pid_sign_dim
            else:
                raise ValueError("Invalid pid_sign_dim value")

        temp.vec[set_zero_dim] = 0

        dot_product = self.get_prod(temp)
        modules_product = self.get_module(non_zero=True) * temp.get_module(non_zero=True)
        ang = dot_product / modules_product
        if ang > 1.0: ang = 1.0
        if ang < -1.0: ang = -1.0

        angle = math.acos(ang)
        if temp.vec[sign_dim] < 0:
            angle = -angle

        return angle

    def get_rotate_angle_fix(self):
        """
        Get the Euler angles (gamma, beta, alpha) needed to rotate this vector
        using fixed-axis rotations (Z-Y-X order). Only valid in NED or NWU, not NEU!!!!)

        Returns:
            list: [gamma, beta, alpha] where:
                - alpha: rotation around Z-axis (yaw)
                - beta: rotation around Y-axis (pitch)
                - gamma: rotation around X-axis (roll, always 0 in this method)
        """
        vx = self.vec[0]
        vy = self.vec[1]
        vz = self.vec[2]

        alpha = math.atan2(vy, vx)
        beta = math.atan2(-vz, math.sqrt(vx*vx + vy*vy))
        gamma = 0.0

        return [gamma, beta, alpha]

    def get_dot(self, v3):
        """Compute dot product with another vector (alias for get_prod)."""
        return self.get_prod(v3)

    def get_Vector2(self):
        lis = self.vec.tolist()
        return Vector2([lis[0],lis[1]])
    
    def __len__(self):
        return len(self.vec)

    def __add__(self, other):
        """Add two vectors."""
        if isinstance(other, Vector3):
            return Vector3((self.vec + other.vec).tolist())
        else:
            raise TypeError("Unsupported operand type for +")

    def __sub__(self, other):
        """Subtract two vectors."""
        if isinstance(other, Vector3):
            return Vector3((self.vec - other.vec).tolist())
        else:
            raise TypeError("Unsupported operand type for -")

    def __eq__(self, other):
        """Check equality with another vector."""
        if not isinstance(other, Vector3):
            return False
        if np.array_equal(self.vec, other.vec):
            return True
        # Use approximate equality with absolute precision
        abs_precision = 1e-9
        return np.allclose(self.vec, other.vec, atol=abs_precision, rtol=0)

    def __getitem__(self, index):
        """Get vector component by index."""
        if 0 <= index < 3:
            return self.vec[index]
        else:
            raise IndexError("Index out of range")

    def __setitem__(self, index, value):
        """Set vector component by index."""
        if 0 <= index < 3:
            self.vec[index] = value
        else:
            raise IndexError("Index out of range")
    
    def __str__(self):
        """Return string representation of vector."""
        return f"Vector3({self.vec.tolist()})"
    
    def __repr__(self):
        """Return string representation of vector."""
        return f"Vector3({self.vec.tolist()})"
    
    def copy(self):
        """Return a copy of the vector."""
        return Vector3(self.vec.tolist())

    def normalize(self):
        """Normalize the vector to unit length."""
        module = self.get_module(non_zero=False)
        if module == 0:
            raise ValueError("Cannot normalize zero vector")
        self.vec = self.vec / module
        return self


######################################
## Coordinate Transformations
######################################

def get_NED_from_NEU(x,mid=np.array([0,0,5000])):
    import warnings
    warnings.warn("This legacy func for hdb2023 is deprecated.", DeprecationWarning)
    if mid != np.array([0,0,5000]) : raise NotImplementedError
    h = x[2]
    z = -(h- mid[2])
    x[2] = z
    return x

# def NEU_to_self(neu:list,roll,pitch,yaw):
#     intent_heading = neu
#     intent_heading[2] = -intent_heading[2]  #-------------

#     intent_heading = Vector3(intent_heading)
#     intent_heading.rev_rotate_zyx_self(roll,pitch,yaw)
#     intent_heading = intent_heading.get_list()

#     intent_heading[2] = -1* intent_heading[2]   # ----------------------
#     return intent_heading

def NEU_to_self(neu: Union[List[float], np.ndarray], roll: float, pitch: float, yaw: float) -> List[float]:
    vec = Vector3(neu)
    vec.vec[2] = -vec.vec[2]

    # vec.rev_rotate_zyx_self(roll, -pitch, yaw)
    vec.rev_rotate_zyx_self(roll, pitch, yaw)

    vec = vec.get_list()
    vec[2] = -vec[2]
    return vec


def self_to_NEU(body: List[float], roll: float, pitch: float, yaw: float) -> List[float]:
    vec = Vector3(body)
    vec.vec[2] = -vec.vec[2]

    # vec.rotate_zyx_self(roll, -pitch, yaw)
    vec.rotate_zyx_self(roll, pitch, yaw)

    vec = vec.get_list()
    vec[2] = -vec[2]
    return vec

def NWU_to_self(nwu: Union[List[float], np.ndarray], roll: float, pitch: float, yaw: float) -> List[float]:
    vec = Vector3(nwu)
    vec.rev_rotate_zyx_self(roll, pitch, yaw)
    vec = vec.get_list()
    return vec


def self_to_NWU(body: List[float], roll: float, pitch: float, yaw: float) -> List[float]:
    vec = Vector3(body)
    vec.rotate_zyx_self(roll, pitch, yaw)
    vec = vec.get_list()
    return vec

def NEU_to_LLA_deg_lowacc(north: float, east: float, up: float, lon_ref: float, lat_ref: float, alt_ref: float) -> Tuple[float, float, float]:
    # Earth radius
    R = 6371000.0  # meters
    # Convert north/east to lat/lon offsets
    lat = lat_ref + (north / R) * (180.0 / np.pi)
    lon = lon_ref + (east / R) * (180.0 / np.pi) / np.cos(lat_ref * np.pi / 180.0)
    alt = alt_ref + up
    return lon, lat, alt

def NWU_to_LLA_deg_lowacc(north: float, west: float, up: float, lon_ref: float, lat_ref: float, alt_ref: float) -> Tuple[float, float, float]:
    return NEU_to_LLA_deg_lowacc(north, -west, up, lon_ref, lat_ref, alt_ref)

def LLA_to_NWU_deg_lowacc(lon: float, lat: float, alt: float,
    lon_ref: float, lat_ref: float, alt_ref: float) -> Tuple[float, float, float]:
    R = 6371000.0  # meters

    # Convert degree differences to radians
    dlat = (lat - lat_ref) * np.pi / 180.0
    dlon = (lon - lon_ref) * np.pi / 180.0

    # North displacement (positive north)
    north = dlat * R

    # West displacement (positive west, opposite of east)
    west = -dlon * R * np.cos(lat_ref * np.pi / 180.0)

    # Up displacement
    up = alt - alt_ref

    return north, west, up

###############################################################

# --------------------------
#  ELLIPSOID CONSTANTS
# --------------------------
a = 6378137.0                          # WGS84 semi-major axis
f = 1.0 / 298.257223565                # flattening
e2 = f * (2 - f)                       # eccentricity^2


# --------------------------
#  LLA → ECEF
# --------------------------
def LLA_to_ECEF(lon: float, lat: float, alt: float) -> np.ndarray:
    N = a / np.sqrt(1 - e2 * np.sin(lat)**2)

    x = (N + alt) * np.cos(lat) * np.cos(lon)
    y = (N + alt) * np.cos(lat) * np.sin(lon)
    z = (N * (1 - e2) + alt) * np.sin(lat)

    return np.array([x, y, z])


# --------------------------
#  ECEF → LLA  (ITERATIVE)
# --------------------------
def ECEF_to_LLA(x: float, y: float, z: float) -> Tuple[float, float, float]:
    lon = np.arctan2(y, x)
    p = np.sqrt(x*x + y*y)

    # initial latitude
    lat = np.arctan2(z, p * (1 - e2))

    # iterative solve
    for _ in range(10):
        N = a / np.sqrt(1 - e2 * np.sin(lat)**2)
        lat = np.arctan2(z + e2 * N * np.sin(lat), p)

    N = a / np.sqrt(1 - e2 * np.sin(lat)**2)
    alt = p / np.cos(lat) - N

    return lon, lat, alt


# --------------------------
#  NWU → LLA_ 
# --------------------------
def NWU_to_LLA_(north: float, west: float, up: float,
                lon_ref: float, lat_ref: float, alt_ref: float
                ) -> Tuple[float, float, float]:

    # NWU → ENU
    east = -west
    north_ = north
    up_ = up

    ENU = np.array([east, north_, up_])

    # reference ECEF
    ECEF_ref = LLA_to_ECEF(lon_ref, lat_ref, alt_ref)

    # ENU → ECEF rotation matrix
    sin_lon = np.sin(lon_ref);  cos_lon = np.cos(lon_ref)
    sin_lat = np.sin(lat_ref);  cos_lat = np.cos(lat_ref)

    M = np.array([
        [-sin_lon,                 -sin_lat * cos_lon,    cos_lat * cos_lon],
        [ cos_lon,                 -sin_lat * sin_lon,    cos_lat * sin_lon],
        [ 0.0,                      cos_lat,              sin_lat          ]
    ])

    dECEF = M @ ENU

    ECEF_target = ECEF_ref + dECEF

    return ECEF_to_LLA(*ECEF_target)


# --------------------------
#  NWU → LLA 
# --------------------------
def NWU_to_LLA_deg(north: float, west: float, up: float,
                lon_ref: float, lat_ref: float, alt_ref: float
                ) -> Tuple[float, float, float]:
    lon_ref = np.deg2rad(lon_ref)
    lat_ref = np.deg2rad(lat_ref)
    
    lon, lat, alt = NWU_to_LLA_(
        north, west, up,
        lon_ref, lat_ref, alt_ref
    )
    lon = np.rad2deg(lon)
    lat = np.rad2deg(lat)
    return lon, lat, alt

# ===============  LLA → NWU  ===============
def LLA_to_NWU_(lon: float, lat: float, alt: float,
                lon_ref: float, lat_ref: float, alt_ref: float
                ) -> Tuple[float, float, float]:
    # 1. LLA → ECEF
    ECEF_target = LLA_to_ECEF(lon, lat, alt)
    ECEF_ref    = LLA_to_ECEF(lon_ref, lat_ref, alt_ref)

    dECEF = ECEF_target - ECEF_ref

    # 2. ECEF → ENU 
    sin_lon = np.sin(lon_ref);  cos_lon = np.cos(lon_ref)
    sin_lat = np.sin(lat_ref);  cos_lat = np.cos(lat_ref)

    M = np.array([
        [-sin_lon,                 cos_lon,                 0.0       ],
        [-sin_lat * cos_lon,      -sin_lat * sin_lon,       cos_lat   ],
        [ cos_lat * cos_lon,       cos_lat * sin_lon,       sin_lat   ]
    ])

    ENU = M @ dECEF     # (east, north, up)

    # 3. ENU → NWU
    east, north, up_ = ENU

    north_nwu = north
    west_nwu  = -east
    up_nwu    = up_

    return north_nwu, west_nwu, up_nwu

def LLA_to_NWU_deg(lon: float, lat: float, alt: float,
                lon_ref: float, lat_ref: float, alt_ref: float
                ) -> Tuple[float, float, float]:
    lon = np.deg2rad(lon)
    lat = np.deg2rad(lat)
    lon_ref = np.deg2rad(lon_ref)
    lat_ref = np.deg2rad(lat_ref)

    n, w, u = LLA_to_NWU_(lon, lat, alt, lon_ref, lat_ref, alt_ref)
    return n, w, u
###############################################################

# def _check_LLA_to_NWU():
#     # original NWU
#     nwu0 = np.array([100.0, 50.0, 20.0])
#     ref  = np.array([120.0, 30.0, 100.0])  # lon, lat, alt

#     lla = NWU_to_LLA(nwu0, ref)
#     nwu1 = LLA_to_NWU(lla, ref)

#     print(nwu0, nwu1)   # should match (within floating precision)

# def velocity_to_euler_NEU(velocity: np.ndarray) -> Tuple[float, float, float]:
#     """
#     Convert velocity vector to Euler angles (roll, pitch, yaw)

#     For visualization purposes, we assume:
#     - Roll = 0 (no bank angle, simplified)
#     - Pitch = angle from horizontal
#     - Yaw = heading angle

#     Args:
#         velocity: [vx, vy, vz] velocity vector in m/s (NEU frame)

#     Returns:
#         (roll, pitch, yaw) in degrees
#     """
#     vx, vy, vz = velocity

#     # Yaw (heading): 0 = north, clockwise positive
#     yaw = np.arctan2(vy, vx) * 180.0 / np.pi

#     # Pitch: angle from horizontal
#     v_horizontal = np.sqrt(vx**2 + vy**2)
#     pitch = np.arctan2(vz, v_horizontal) * 180.0 / np.pi

#     # Roll: assume zero for simplicity
#     roll = 0.0

#     return roll, pitch, yaw

def velocity_to_euler_NEU(velocity: np.ndarray) -> Tuple[float, float, float]:
    if isinstance(velocity, np.ndarray):
        vel_vec = Vector3(velocity)
    g, b, a = vel_vec.get_rotate_angle_fix()
    return g, -b, a  # NEU!!!!!!!

def velocity_to_euler_NWU(velocity: np.ndarray) -> Tuple[float, float, float]:
    if isinstance(velocity, np.ndarray):
        vel_vec = Vector3(velocity)
    g, b, a = vel_vec.get_rotate_angle_fix()
    return g, b, a 

######################################
## misc
######################################

def dict_obj(d):
    top = type('new', (object,), d)
    seqs = tuple, list, set, frozenset
    for key, value in d.items():
        if isinstance(value, dict):
            setattr(top, key, dict_obj(value))
        elif isinstance(value, seqs):
            setattr(top, key, type(value)(dict_obj(x) if isinstance(x, dict) else x for x in value))
        else:
            setattr(top, key, value)
    return top 

def float2(list):
    for i in range(len(list)):
        list[i] = round(list[i],2)
    return list

def has(list,x):
    for i in range(len(list)):
        if list[i] == x:
            return True
    return False

def has_index(dict :dict, index):
    for ind,inf in dict.items():
        if ind == index:
            return True
    return False

def abs_max(num,m):
    if num>m :
        num = m
    if num<-m:
        num = -m
    return num

def no_neg(num):
    if num <0 :
        num = 0
    return num

# def abs (x):
#     if x < 0:
#         return -x
#     return x

def pwr(x) :
    return x*x  

def norm(x: float, lower_side: float=-1.0, upper_side: float=1.0):
    if (x > upper_side): x = upper_side
    if (x < lower_side): x = lower_side
    return x

def norm_pi(angle: float) -> float:
    """
    Normalize angle to [-π, π] range.

    Args:
        angle: Angle in radians

    Returns:
        Normalized angle in [-π, π]
    """
    while angle > math.pi:
        angle -= 2 * math.pi
    while angle < -math.pi:
        angle += 2 * math.pi
    return angle
    # return (angle + np.pi) % (2.0 * np.pi) - np.pi

def meters_to_feet(meters):
    return meters * 3.28084
def feet_to_meters(feet):
    return feet / 3.28084

def nm_to_meters(nm):
    """Convert nautical miles to meters."""
    return nm * 1852

def meters_to_nm(meters):
    """Convert meters to nautical miles."""
    return meters / 1852

#################################
## temperature
#################################

K_C0 = 273.15
R = 287.05
GAMMA = 1.4
T0 = 288.15
P0 = 101325.0
L = 0.0065
TROPOPAUSE_ALT = 11000.0
STRAT_ALT = 20000.0
T_TROPOPAUSE = 216.65

def K_to_C(K: float) -> float:
    return K - K_C0

def C_to_K(C: float) -> float:
    return C + K_C0

def estimate_temperature_C(altitude: float) -> float:
    if altitude <= TROPOPAUSE_ALT:
        ret = T0 - L * altitude
    elif altitude <= STRAT_ALT:
        ret = T_TROPOPAUSE
    else:
        ret = T_TROPOPAUSE
    return K_to_C(ret)

def mach_to_mps(mach: float, temperature_C: float) -> float:
    temperature_K = C_to_K(temperature_C)
    local_ss = math.sqrt(GAMMA * R * temperature_K)
    return mach * local_ss

def get_mps(mach: float, altitude: float) -> float:
    return mach_to_mps(mach, estimate_temperature_C(altitude))

def get_mach(mps: float, altitude: float) -> float:
    temperature_C = estimate_temperature_C(altitude)
    temperature_K = C_to_K(temperature_C)
    local_ss = math.sqrt(GAMMA * R * temperature_K)
    return mps / local_ss

def calculate_atmospheric_properties(altitude_m: float) -> dict:
    temperature_K = C_to_K(estimate_temperature_C(altitude_m))
    if altitude_m < TROPOPAUSE_ALT:
        pressure = P0 * (temperature_K / T0) ** 5.256
    else:
        pressure = 22632 * math.exp(-0.0001577 * (altitude_m - TROPOPAUSE_ALT))
    density = pressure / (R * temperature_K)
    sound_speed = math.sqrt(GAMMA * R * temperature_K)
    return {
        'temperature': temperature_K,
        'pressure': pressure,
        'density': density,
        'sound_speed': sound_speed
    }
