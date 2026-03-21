import math
from typing import Tuple
from uhtk.c3utils.i3utils import norm, Vector3, get_mps

class StdFlightControllerNWU:
    """
    Standard F16-like Flight Controller adapted for NWU coordinate system.

    Original fc.py uses NEU (North-East-Up), but BVR3D uses NWU (North-West-Up).
    This version handles the coordinate system conversion.

    Inputs: roll, pitch, yaw, mach, height, vd, heading, etc. (NWU system)
    Outputs: [roll_cmd, pitch_cmd, yaw_cmd, throttle_cmd] (-1~1, throttle 0~1)
    """

    def __init__(self, dt: float = 0.05):
        # Roll PID gains
        self.kroll_p = 1.2
        self.kroll_i = 0.2
        self.kroll_d = -0.0

        # Pitch PID gains
        self.kpitch_p = -3.4
        self.kpitch_i = -0.0
        self.kpitch_d = 0.0

        # Throttle PID gains
        self.kthrottle_p = 0.03
        self.kthrottle_i = 0.06
        self.kthrottle_d = 500.0

        # PID memory
        self.dt = dt
        self.sum_err_roll = 0.0
        self.last_err_roll = 0.0
        self.sum_err_pitch = 0.0
        self.last_err_pitch = 0.0
        self.sum_err_throttle = 0.0
        self.last_err_throttle = 0.0

        # State memory
        self.right_turn = 0

    # ---------------------------------------------------------------
    # Utility
    # ---------------------------------------------------------------
    @staticmethod
    def norm_fc_output(action4: list) -> list:
        """Normalize roll, pitch, yaw (-1~1) and throttle (0~1)."""
        action4[0] = norm(action4[0])
        action4[1] = norm(action4[1])
        action4[2] = norm(action4[2])
        action4[3] = norm(action4[3], lower_side=0., upper_side=1.)
        return action4

    @staticmethod
    def get_throttle_base(
        height: float,
        pitch: float,
        mach: float,
        intent_mach: float
    ) -> float:
        base = 0.5
        if height > 7500:
            base += 0.5 * ((height - 7500) / 7500)
        if intent_mach > 1:
            base += (intent_mach - 1)
        if (height < 10000 or pitch > 0):
            base += 0.4 * pitch / (math.pi / 2)
        if mach < 0.7:
            base = 1
        return base

    @staticmethod
    def adapt_campus_action_nwu(
        action: dict,
        roll: float,
        pitch: float,
        yaw: float,
        mach: float,
        height: float,
        vd: float,
        heading_vec: Vector3,
        dt: float = 0.05
    ) -> dict:
        """
        Map action dict to flight controller inputs (NWU coordinate system).

        action keys:
            - delta_heading: rad/s (turning rate, positive = turn right/clockwise in NWU)
            - delta_altitude: m/s (climb rate, positive = climb)
            - delta_speed: m/s^2 (acceleration, positive = accelerate)
        """

        # --------------------------
        # 1. Compute target heading
        # --------------------------
        # In NWU: yaw=0 points North, positive yaw turns East (right turn)
        new_yaw = yaw + action['delta_heading'] * dt

        # Convert yaw to heading vector in NWU system
        # North component: cos(yaw), West component: -sin(yaw)
        intent_vec = Vector3([math.cos(new_yaw), -math.sin(new_yaw), 0])
        intent_vec.prod(1 / intent_vec.get_module())

        # --------------------------
        # 2. Compute target Mach
        # --------------------------
        current_speed = get_mps(mach, height)
        target_speed = current_speed + action['delta_speed'] * dt
        intent_mach = target_speed / get_mps(1.0, height)  # speed / speed of sound

        # --------------------------
        # 3. Compute target height
        # --------------------------
        target_height = height + action['delta_altitude'] * dt

        # --------------------------
        # 4. Return controller inputs
        # --------------------------
        return {
            'roll': roll,
            'pitch': pitch,
            'yaw': yaw,
            'mach': mach,
            'height': height,
            'vd': vd,
            'heading_vec': heading_vec,
            'intent_vec': intent_vec,
            'intent_mach': intent_mach,
            'target_height': target_height,
            'strength_bias': 0.0
        }

    def direct_LU_flight_control_nwu(
        self,
        roll: float,
        pitch: float,
        yaw: float,
        mach: float,
        height: float,
        vd: float,
        heading_vec: Vector3,
        intent_vec: Vector3,        # action input vec
        intent_mach: float,
        target_height: float = 0.0,
    ) -> list:
        """
        Main flight control law adapted for NWU coordinate system.

        Args:
            All inputs use NWU coordinate system convention
            - yaw=0 points North, positive turns East (right)
            - heading_vec points in current heading direction (NWU)
            - intent_vec points in desired heading direction (NWU)
        """

        # =======================================================
        # 1. Heading control (roll command)
        # =======================================================

        # Cross product to get turning direction in NWU
        cross_z = heading_vec[0] * intent_vec[1] - heading_vec[1] * intent_vec[0]

        # Positive cross_z means intent is to the right (East) of current heading
        # In NWU: right turn requires negative roll
        if cross_z > 0:
            self.right_turn = 1
        elif cross_z < 0:
            self.right_turn = -1

        # Calculate heading error
        dot_product = heading_vec[0] * intent_vec[0] + heading_vec[1] * intent_vec[1]
        heading_error = math.acos(max(-1, min(1, dot_product)))

        # Roll command based on heading error
        if heading_error > math.pi / 18:  # > 10 degrees
            roll_cmd = self.right_turn * 0.7
        elif heading_error > math.pi / 36:  # > 5 degrees
            roll_cmd = self.right_turn * 0.4
        else:
            roll_cmd = 0

        # =======================================================
        # 2. Altitude control (pitch command)
        # =======================================================

        height_error = target_height - height
        pitch_cmd = height_error / 10000.0  # Simple proportional control

        # Limit pitch command
        pitch_cmd = max(-0.5, min(0.5, pitch_cmd))

        # =======================================================
        # 3. Speed control (throttle command)
        # =======================================================

        throttle_base = self.get_throttle_base(height, pitch, mach, intent_mach)
        throttle_cmd = throttle_base

        # Adjust for speed error
        if mach < intent_mach * 0.95:
            throttle_cmd = min(1.0, throttle_cmd + 0.1)
        elif mach > intent_mach * 1.05:
            throttle_cmd = max(0.0, throttle_cmd - 0.1)

        # =======================================================
        # 4. Yaw command (rudder for coordination)
        # =======================================================

        # Simple yaw damping
        # yaw_cmd = -roll_cmd * 0.1  # Coordinate turn
        yaw_cmd = 0

        return [roll_cmd, pitch_cmd, yaw_cmd, throttle_cmd]