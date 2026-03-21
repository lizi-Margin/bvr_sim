import math
from typing import Tuple
from uhtk.c3utils.i3utils import norm, Vector3, get_mps


class StdFlightController:
    """
    Standard F16-like Flight Controller (JSBSim compatible)
    Inputs: roll, pitch, yaw, mach, height, vd, heading, etc.
    Outputs: [roll_cmd, pitch_cmd, yaw_cmd, throttle_cmd]
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


    # NWU ver.
    def direct_LU_flight_control(
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
        dodge_vec: Vector3 = None,  # action input vec (used by rule)
        dodge_range: float = 1e9,
        target_height: float = 0.0,
        strength_bias: float = 0.0
    ) -> list:
        # -----------------------------
        # Step 1. Basic heading decision
        # -----------------------------
        dodge_active = dodge_vec is not None and dodge_range < 40_000
        intent_heading = dodge_vec if dodge_active else intent_vec

        # -----------------------------
        # Step 2. Height-based protection
        # -----------------------------
        crashing, over_height = self._safety_protection(
            height, pitch, vd, mach, dodge_active
        )

        if crashing:
            intent_heading = Vector3(heading_vec.get_list())
            intent_heading[2] = 0

        # -----------------------------
        # Step 3. Convert to body coordinates
        # -----------------------------
        intent_heading = Vector3(intent_heading)
        intent_heading.rev_rotate_zyx_self(roll, pitch, yaw)
        intent_heading.prod(1 / intent_heading.get_module())

        # -----------------------------
        # Step 4. Compute pitch/roll errors
        # -----------------------------
        err_pitch, err_roll, roll_angle = self._attitude_error(
            intent_heading, roll, pitch, vd, height
        )

        # -----------------------------
        # Step 5. Compute throttle error
        # -----------------------------
        err_throttle = intent_mach - mach

        # -----------------------------
        # Step 6. PID + bias scaling
        # -----------------------------
        throttle_base = self.get_throttle_base(height, pitch, mach, intent_mach)
        kset = self._adaptive_pid_scaling(
            height, mach, err_pitch, strength_bias
        )

        action = self.pid(
            err_roll, err_pitch, err_throttle,
            *kset,
            throttle_base
        )

        # -----------------------------
        # Step 7. Post-condition corrections
        # -----------------------------
        if not (dodge_active or crashing):
            if abs(roll_angle) > math.pi / 4 and abs(roll_angle) < 3 * math.pi / 4:
                action[1] = 0  # disable pitch when high bank angle

        # low-speed or high-speed protection
        if mach < 0.18:
            action[1] /= 10
            action[0] /= 2
            action[3] = 1
        if height < 3200 and pitch < -1.15 and mach > 1.2:
            action[3] = 0

        return self.norm_fc_output(action)

    def _safety_protection(self, height, pitch, vd, mach, dodge_active) -> Tuple[bool, bool]:
        crashing = False
        over_height = False

        if (
            (height < 4000 and (height / vd < 25 and vd > 0)) or
            (pitch < -math.pi / 4 and height < 3500) or
            height < 400
        ) and (height < 1500 or mach > 0.5) and not dodge_active:
            crashing = True

        if (
            ((15000 - height) / (-vd) < 25 and vd < 0) or
            (pitch > math.pi / 4 and height > 12000)
        ) and not dodge_active and height > 10000:
            over_height = True
            crashing = True

        return crashing, over_height

    def _attitude_error(self, intent_heading, roll, pitch, vd, height) -> Tuple[float, float, float]:
        err_pitch = math.asin(intent_heading[2])
        if err_pitch < 0:
            err_pitch *= 4
        err_pitch = max(min(err_pitch, math.pi / 6), -math.pi / 6)
        err_pitch *= 0.75  # scale

        # gain = math.tanh(-(vd - 50 * (height - 6000) / 11500) * 1e-2)
        err_roll = math.atan2(intent_heading[1], intent_heading[0])
        roll_angle = err_roll

        if abs(err_roll) > math.pi / 3:
            err_roll = math.copysign(math.pi / 3, err_roll)

        return err_pitch, err_roll, roll_angle

    def _adaptive_pid_scaling(self, height, mach, err_pitch, strength_bias):
        roll_bias = 0.5 * norm(strength_bias, -1., 1.) + 1.
        pitch_bias = 0.5 * norm(strength_bias, -1., 0.) + 1.

        kroll_p = self.kroll_p * roll_bias
        kroll_i = self.kroll_i * roll_bias
        kroll_d = self.kroll_d * roll_bias
        kpitch_p = self.kpitch_p * pitch_bias
        kpitch_i = self.kpitch_i * pitch_bias
        kpitch_d = self.kpitch_d * pitch_bias

        if height > 11000:
            scale = (20000 - height) / 9000
            kpitch_p *= scale
            kpitch_i *= scale
            kroll_p *= (16000 - height) / 5000
            kroll_i *= (16000 - height) / 5000

        if mach > 0.3:
            kpitch_p *= (mach + 0.2)
            kpitch_i *= (mach + 0.2)
            kroll_p *= 0.7 + 0.3 * (abs(err_pitch) / (1.5 * math.pi / 12))
            kroll_i *= 0.7 + 0.3 * (abs(err_pitch) / (1.5 * math.pi / 12))
        else:
            kpitch_p *= 0.5
            kpitch_i *= 0.5
            kroll_p *= 0.8
            kroll_i *= 0.8

        kpitch_d *= mach

        return (kroll_p, kroll_i, kroll_d, kpitch_p, kpitch_i, kpitch_d)

    def pid(self, err_roll, err_pitch, err_throttle,
            kroll_p, kroll_i, kroll_d,
            kpitch_p, kpitch_i, kpitch_d,
            throttle_base=0.5) -> list:
        pid_output = [0, 0, 0, 1]

        # roll
        # I
        self.sum_err_roll += err_roll * self.dt
        # D
        d_err_roll = (err_roll - self.last_err_roll)/self.dt 
        # output
        pid_output[0] = kroll_p * err_roll +  kroll_d * d_err_roll 
        if(abs(err_roll)<0.32):pid_output[1] +=kroll_i * self.sum_err_roll # 引入积分
        self.sum_err_roll = norm(self.sum_err_roll, -2.5, 2.5)

        # pitch
        # I
        if abs(err_pitch ) < math.pi/6 : 
            if  (err_pitch <= math.pi/90 ) and (err_pitch>=-math.pi/90): 
                self.sum_err_pitch = 0
            else :self.sum_err_pitch += err_pitch * self.dt
        else :
            self.sum_err_pitch = 0
        # D
        d_err_pitch = (err_pitch - self.last_err_pitch)/self.dt 
        # output
        pid_output[1] = kpitch_p * err_pitch  + kpitch_d * d_err_pitch            
        if abs(err_pitch ) < math.pi/6 : 
            pid_output[1] +=kpitch_i * self.sum_err_pitch  # 引入积分

        self.sum_err_pitch = norm(self.sum_err_pitch, -8., 8.)

        # throttle 
        # I
        self.sum_err_throttle += err_throttle
        # D
        d_err_throttle = (err_throttle - self.last_err_throttle)
        # output
        pid_output[3] = throttle_base + self.kthrottle_p * err_throttle + self.kthrottle_i * self.sum_err_throttle + self.kthrottle_d * d_err_throttle
        pid_output[3] = norm(pid_output[3], 0., 1.)

        self.sum_err_throttle = norm(self.sum_err_throttle, -10., 10.)

        self.last_err_roll =err_roll
        self.last_err_pitch= err_pitch
        self.last_err_throttle = err_throttle

        return pid_output
