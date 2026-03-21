from typing import Dict, Any, Union, List, TYPE_CHECKING
import os
import numpy as np
import math
from .base import BaseFDM
from uhtk.c3utils.i3utils import norm_pi, NWU_to_LLA_deg, LLA_to_NWU_deg, feet_to_meters, meters_to_feet, get_mps, get_mach, Vector3
from ...simulator import NWU2LLA, LLA2NWU
from ..fc.fc_old import StdFlightController
from uhtk.print_pack import print_green, print_red, print_blue, print_dict
from .catalog import Catalog, JsbsimCatalog, ExtraCatalog, Property

if TYPE_CHECKING:
    import jsbsim

def get_root_dir() -> str:
    return os.path.dirname(os.path.realpath(__file__))

class SimpleScalarFilter:
    def __init__(self, alpha: float, initial_value: float = 0.0):
        self.alpha = alpha
        self.init_value = initial_value
        self.value = initial_value
    
    def reset(self) -> None:
        self.value = self.init_value

    def update(self, x: float) -> float:
        self.value = self.alpha * x + (1 - self.alpha) * self.value
        return self.value

class obj:
    def __init__(self):
        pass

class JSBSimFDM(BaseFDM):

    def __init__(self, dt: float = 0.1, **kwargs):
        super().__init__(dt, **kwargs)
        self.JSBSim_dir: str = os.path.join(get_root_dir(), "..", "..", "..", 'src', 'simulator', 'aircraft', 'fdm', 'jsbsim')
        self.aircraft_model: str = kwargs.get('aircraft_model', "F16").lower()

        self._jsbsim_exec: Union['jsbsim.FGFDMExec', None] = None
        self.jsbsim_exec: Union['jsbsim.FGFDMExec', None] = None
        self._initialized: bool = False

        self._jsbsim_dt_max: float = 0.025  # 不抖
        # self._jsbsim_dt_max: float = 0.05  # 抖
        self._jsbsim_inner_dt: float = self.dt
        self._jsbsim_inner_steps: int = 1
        if self.dt > self._jsbsim_dt_max:
            self._jsbsim_inner_steps = int(self.dt / self._jsbsim_dt_max) + 1
            self._jsbsim_inner_dt = self.dt / self._jsbsim_inner_steps
        
        self.fc: StdFlightController = StdFlightController(dt=self._jsbsim_inner_dt)
        self.fc_delta_heading_filter: SimpleScalarFilter = SimpleScalarFilter(alpha=0.01)
        self.fc_delta_pitch_filter: SimpleScalarFilter = SimpleScalarFilter(alpha=0.10)


    def _initialize_jsbsim(self) -> None:
        import jsbsim
        self._jsbsim_exec = jsbsim.FGFDMExec(self.JSBSim_dir)
        self.jsbsim_exec = self._jsbsim_exec
        self._jsbsim_exec.set_debug_level(0)
        self._jsbsim_exec.load_model(self.aircraft_model)

        props = self._jsbsim_exec.query_property_catalog("")
        if not isinstance(props, list):
            assert isinstance(props, str)
            props = props.split("\n")
            assert isinstance(props, list)
        Catalog.add_jsbsim_props(props)

        print_red(f"JSBSim dt: {self._jsbsim_inner_dt}")
        self._jsbsim_exec.set_dt(self._jsbsim_inner_dt)

        self._clear_default_condition()

    def _clear_default_condition(self) -> None:
        default_condition = {
            Catalog.ic_long_gc_deg: 120.0,
            Catalog.ic_lat_geod_deg: 60.0,
            Catalog.ic_h_sl_ft: 20000,
            Catalog.ic_psi_true_deg: 0.0,
            Catalog.ic_u_fps: 800.0,
            Catalog.ic_v_fps: 0.0,
            Catalog.ic_w_fps: 0.0,
            Catalog.ic_p_rad_sec: 0.0,
            Catalog.ic_q_rad_sec: 0.0,
            Catalog.ic_r_rad_sec: 0.0,
            Catalog.ic_roc_fpm: 0.0,
            Catalog.ic_terrain_elevation_ft: 0,
        }
        for prop, value in default_condition.items():
            self.set_property_value(prop, value)

    def reset(self, initial_state: Dict[str, Any]) -> None:
        position = np.array(initial_state['position'], dtype=float)
        velocity = np.array(initial_state['velocity'], dtype=float)

        lon, lat, alt = NWU2LLA(position[0], position[1], position[2])

        if np.linalg.norm(velocity[:2]) > 1e-6:
            yaw = math.atan2(-velocity[1], velocity[0])
        else:
            yaw = float(initial_state.get('yaw', 0.0))

        speed = np.linalg.norm(velocity)
        roll = float(initial_state.get('roll', 0.0))
        pitch = float(initial_state.get('pitch', 0.0))

        self.position = position
        self.velocity = velocity
        self.roll = roll
        self.pitch = pitch
        self.yaw = yaw

        self.fc_delta_heading_filter.reset()
        self.fc_delta_pitch_filter.reset()
        self._initialize_jsbsim()
        self._set_jsbsim_initial_conditions(lon, lat, alt, speed, roll, pitch, yaw)

        propulsion = self._jsbsim_exec.get_propulsion()
        n_engines = propulsion.get_num_engines()
        for i in range(n_engines):
            propulsion.get_engine(i).init_running()
        propulsion.get_steady_state()

        self._update_properties()
        self._initialized = True

        print_green(f"JSBSim {self.aircraft_model} reset at ({lon:.2f} E, {lat:.2f} N, N{self.position[0]:.2f}, W{self.position[1]:.2f}, U(true alt){alt:.0f}m, {meters_to_feet(alt):.0f}ft, {np.rad2deg(yaw):.2f} deg)")

    def get_mach(self) -> float:
        return self.mach

    def _run_jsbsim_step(self, action: Dict[str, float]) -> None:
        delta_heading = np.clip(action['delta_heading'], -1, 1) * np.deg2rad(100)
        delta_heading = self.fc_delta_heading_filter.update(delta_heading)
        self._delta_heading = delta_heading
        delta_pitch = -np.clip(action['delta_altitude'], -1, 1) * np.deg2rad(60)
        delta_pitch = self.fc_delta_pitch_filter.update(delta_pitch)
        self._delta_pitch = delta_pitch
        fix_vec = self.get_heading_vec(); fix_vec[2] = 0
        fix_vec = fix_vec.rotate_zyx_self(0, delta_pitch, delta_heading)

        mach = self.get_mach()
        intent_mach = mach + action['delta_speed']

        for _ in range(self._jsbsim_inner_steps):
            if self.terminate:
                break
            mach = self.get_mach()
            fake_fighter = obj()
            fake_fighter.roll = self.roll
            fake_fighter.pitch = -self.pitch
            fake_fighter.yaw = -self.yaw
            fake_fighter.mach = mach
            fake_fighter.vd = -self.velocity[2]
            fake_fighter.height = self.position[2]
            fake_fighter.heading = Vector3([1,0,0]).rotate_zyx_self(self.roll, -self.pitch, -self.yaw)

            fix_vec_neu = fix_vec.copy(); fix_vec_neu[1] = -fix_vec_neu[1]
            control_commands = self.fc.direct_LU_flight_controler(
                fighter=fake_fighter,
                fix_vec=fix_vec_neu,
                intent_mach=intent_mach,
                strength_bias=-1,
            )
            self._set_jsbsim_controls(control_commands)

            result = self._jsbsim_exec.run()
            if not result:
                raise RuntimeError("JSBSim step failed")

            self._update_properties()

    def step(self, action: Dict[str, float]) -> None:
        if not self._initialized:
            raise RuntimeError("JSBSimFDM must be reset before stepping")

        self._run_jsbsim_step(action)

    def set_property_value(self, prop: Property, value: float) -> None:
        if isinstance(prop, Property):
            if value < prop.min:
                value = prop.min
            elif value > prop.max:
                value = prop.max

            self.jsbsim_exec.set_property_value(prop.name_jsbsim, value)

            if "W" in prop.access:
                if prop.update:
                    prop.update(self)
        else:
            raise ValueError(f"prop type unhandled: {type(prop)} ({prop})")

    def get_property_value(self, prop: Property) -> float:
        if isinstance(prop, Property):
            if prop.access == "R":
                if prop.update:
                    prop.update(self)
            return self.jsbsim_exec.get_property_value(prop.name_jsbsim)
        else:
            raise ValueError(f"prop type unhandled: {type(prop)} ({prop})")

    def get_property_values(self, props: List[Property]) -> List[float]:
        return [self.get_property_value(prop) for prop in props]

    def _set_jsbsim_controls(self, controls: list) -> None:
        roll_cmd, pitch_cmd, yaw_cmd, throttle_cmd = controls

        self.set_property_value(Catalog.fcs_aileron_cmd_norm, float(roll_cmd))
        self.set_property_value(Catalog.fcs_elevator_cmd_norm, float(pitch_cmd))
        self.set_property_value(Catalog.fcs_rudder_cmd_norm, float(yaw_cmd))
        self.set_property_value(Catalog.fcs_throttle_cmd_norm, float(throttle_cmd))
        self.set_property_value(Catalog.fcs_mixture_cmd_norm, float(throttle_cmd))

    def _set_jsbsim_initial_conditions(self, lon: float, lat: float, alt: float,
                                     speed: float, roll: float, pitch: float, yaw: float) -> None:
        alt_ft = meters_to_feet(alt)

        v_nwu_n = self.velocity[0]
        v_nwu_w = self.velocity[1]
        v_nwu_u = self.velocity[2]

        v_ned_n = v_nwu_n
        v_ned_e = -v_nwu_w
        v_ned_d = -v_nwu_u

        v_ned_vector = Vector3([v_ned_n, v_ned_e, v_ned_d])

        body_velocity_vector = v_ned_vector.rev_rotate_zyx_self(roll, pitch, yaw)

        u_body = body_velocity_vector[0]
        v_body = body_velocity_vector[1]
        w_body = body_velocity_vector[2]

        u_body_fps = meters_to_feet(u_body)
        v_body_fps = meters_to_feet(v_body)
        w_body_fps = meters_to_feet(w_body)

        default_condition = {
            Catalog.ic_long_gc_deg: lon,
            Catalog.ic_lat_geod_deg: lat,
            Catalog.ic_h_sl_ft: alt_ft,
            Catalog.ic_psi_true_deg: math.degrees(yaw),
            Catalog.ic_u_fps: u_body_fps,
            Catalog.ic_v_fps: v_body_fps,
            Catalog.ic_w_fps: w_body_fps,
            Catalog.ic_p_rad_sec: 0.0,
            Catalog.ic_q_rad_sec: 0.0,
            Catalog.ic_r_rad_sec: 0.0,
            Catalog.ic_roc_fpm: 0.0,
            Catalog.ic_terrain_elevation_ft: 0,
        }
        for prop, value in default_condition.items():
            self.set_property_value(prop, value)

        success = self._jsbsim_exec.run_ic()
        if not success:
            raise RuntimeError("JSBSim failed to initialize simulation conditions")

    def _update_properties(self) -> None:
        geodetic = self.get_property_values([
            Catalog.position_long_gc_deg,
            Catalog.position_lat_geod_deg,
            Catalog.position_h_sl_m
        ])
        lon, lat, alt_m = geodetic

        n, w, u = LLA2NWU(lon, lat, alt_m)
        old_position = self.position.copy()
        self.position = np.array([n, w, u])

        posture = self.get_property_values([
            Catalog.attitude_roll_rad,
            Catalog.attitude_pitch_rad,
            Catalog.attitude_heading_true_rad,
        ])
        self.roll = posture[0]
        self.pitch = -1 * posture[1]
        self.yaw = -1 * norm_pi(posture[2])
        # self.yaw = posture[2]

        # velocity_ned = self.get_property_values([
        #     Catalog.velocities_v_north_mps,
        #     Catalog.velocities_v_east_mps,
        #     Catalog.velocities_v_down_mps,
        # ])
        # v_nwu_n = velocity_ned[0]
        # v_nwu_w = -velocity_ned[1]
        # v_nwu_u = -velocity_ned[2]
        # self.velocity = np.array([v_nwu_n, v_nwu_w, v_nwu_u])
        self.velocity = (self.position - old_position) / self._jsbsim_inner_dt

        self.mach = self.get_property_value(Catalog.velocities_mach)

        if alt_m < 25:
            self.terminate = True
            return

        for k, v in self.get_state_dict().items():
            if isinstance(v, (int, float, np.number)):
                if np.isnan(v):
                    self.terminate = True
                    break
            elif isinstance(v, np.ndarray):
                if np.isnan(v).any():
                    self.terminate = True
                    break
