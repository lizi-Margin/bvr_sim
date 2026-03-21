from .simulator import SimulatedObject, TeamColors, NWU2LLA, velocity_to_euler
from .aircraft.base import Aircraft
from .missile.base import Missile
from .ground.base import GroundUnit
from .ground.ground_static_target import GroundStaticTarget
from .ground.aa import AA
from .ground.slamraam import SLAMRAAM

from .data_obj import DataObj

# Sensor systems
from .sense.base import SensorBase
from .sense.radar import Radar
from .sense.simple_radar import SimpleRadar
from .sense.rws import RadarWarningSystem, MissileWarningSystem
from .sense.awacs import SADatalink

# Concrete implementations
from .aircraft.f16 import F16
from .aircraft.fdm import JSBSimFDM, SimpleFDM
from .missile.aim120c import AIM120C
from .missile.aim120c_lossless import AIM120CLossless, AIM120CLoss
from .missile.aim120c_maddog import AIM120CMadDog
from .missile.jsow import JSOW


create_aircraft_dict = {
    'F16': {
        'class': F16,
        'kwargs_override': {
            # 'FDM': SimpleFDM,
            'FDM': JSBSimFDM,
        },
        'sensors': {
            # 'radar': SimpleRadar,
            'radar': Radar,
            'rws': RadarWarningSystem,
            'mws': MissileWarningSystem,
            'sa_datalink': SADatalink,
        },
    },
}

def create_aircraft(aircraft_type: str, **kwargs):
    """Create an aircraft instance with specified type"""
    if aircraft_type not in create_aircraft_dict:
        raise ValueError(f"Unknown aircraft type: {aircraft_type}")
    
    aircraft_config = create_aircraft_dict[aircraft_type]
    aircraft_class = aircraft_config['class']
    sensors: dict[str, SensorBase] = aircraft_config['sensors']

    # Override default kwargs with config
    kwargs_override = aircraft_config['kwargs_override']
    kwargs.update(kwargs_override)
    
    aircraft_instance: Aircraft = aircraft_class(**kwargs)
    
    # Create sensors
    for name, sensor_class in sensors.items():
        aircraft_instance.add_sensor(
            name,
            sensor_class(parent=aircraft_instance, aircraft_model=aircraft_instance.aircraft_model)
        )

    
    return aircraft_instance

create_missile = {
    'AIM120C': AIM120C,
    'AIM120CLossless': AIM120CLossless,
    'AIM120CLoss': AIM120CLoss,
    'AIM120CMadDog': AIM120CMadDog,
    'JSOW': JSOW,
}
