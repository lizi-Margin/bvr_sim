import numpy as np


class SkillManager:
    """Manages tactical skills"""

    def __init__(self):
        self.skills = {
            "crank_maneuver": CrankManeuverSkill,
            "missile_evasion": MissileEvasionSkill,
            "disengage": DisengageSkill,
            "maintain_position": MaintainPositionSkill
        }

    def create_skill(self, skill_name, params=None):
        """Create skill instance"""
        if skill_name in self.skills:
            return self.skills[skill_name](params or {})
        return MaintainPositionSkill({})

    def list_skills(self):
        """List available skills"""
        return list(self.skills.keys())

class TacticalSkill:
    """Base tactical skill"""

    def __init__(self, skill_name, params):
        self.skill_name = skill_name
        self.params = params
        self.default_params = {}
        self.params = {**self.default_params, **params}

    def execute(self, obs):
        """Execute skill"""
        return self._execute(obs)

    def _execute(self, obs):
        """Skill-specific execution"""
        raise NotImplementedError

    def get_schema(self):
        """Get parameter schema"""
        return {"parameters": {}}


class CrankManeuverSkill(TacticalSkill):
    """Crank maneuver skill"""

    def __init__(self, params):
        super().__init__("crank_maneuver", params)
        self.default_params = {
            "direction": "left",
            "offset_angle": 30,
            "switch_frequency": 15,
            "altitude_change": -50,
            "speed_target": 300
        }
        self.params = {**self.default_params, **params}
        self.last_switch_time = 0

    def _execute(self, obs):
        """Execute crank maneuver"""
        current_time = obs.get("time", 0)
        direction = self.params["direction"]

        if current_time - self.last_switch_time > self.params["switch_frequency"]:
            direction = "right" if direction == "left" else "left"
            self.last_switch_time = current_time

        delta_heading = self.params["offset_angle"] / 180 * np.pi
        if direction == "left":
            delta_heading = -delta_heading

        delta_altitude = self.params["altitude_change"] / 4

        action = {
            "skill_name": self.skill_name,
            "delta_heading": delta_heading,
            "delta_altitude": delta_altitude,
            "delta_speed": 1,
            "shoot": 0,
        }

        return action, False




class MissileEvasionSkill(TacticalSkill):
    """Missile evasion skill"""

    def __init__(self, params):
        super().__init__("missile_evasion", params)
        self.default_params = {
            "break_direction": "right",
            "break_duration": 8,
            "max_g": 9
        }
        self.params = {**self.default_params, **params}
        self.start_time = 0

    def _execute(self, obs):
        """Execute missile evasion"""
        current_time = obs.get("time", 0)
        if self.start_time == 0:
            self.start_time = current_time

        if current_time - self.start_time < self.params["break_duration"]:
            direction = self.params["break_direction"]
            delta_heading = 0.5 if direction == "right" else -0.5
            delta_altitude = -100
            delta_speed = 100
            shoot = 0
            completed = False
        else:
            delta_heading = 0
            delta_altitude = 0
            delta_speed = 0
            shoot = 0
            completed = True

        action = {
            "skill_name": self.skill_name,
            "delta_heading": delta_heading,
            "delta_altitude": delta_altitude,
            "delta_speed": delta_speed,
            "shoot": shoot,
            "completed": completed
        }

        return action, completed

    def get_schema(self):
        """Get parameter schema"""
        return {
            "parameters": {
                "break_direction": {"type": "string", "enum": ["left", "right"]},
                "break_duration": {"type": "integer", "min": 3, "max": 15},
                "max_g": {"type": "integer", "min": 4, "max": 12}
            }
        }


class DisengageSkill(TacticalSkill):
    """Disengage skill"""

    def __init__(self, params):
        super().__init__("disengage", params)
        self.default_params = {
            "heading_home": 0,
            "climb_rate": 50,
            "speed_target": 350
        }
        self.params = {**self.default_params, **params}

    def _execute(self, obs):
        """Execute disengage"""
        action = {
            "skill_name": self.skill_name,
            "delta_heading": 0,
            "delta_altitude": self.params["climb_rate"],
            "delta_speed": self.params["speed_target"] - obs.get("self_status", {}).get("performance", {}).get("speed_mps", 250),
            "shoot": 0,
            "completed": False
        }

        return action, False

    def get_schema(self):
        """Get parameter schema"""
        return {
            "parameters": {
                "heading_home": {"type": "integer", "min": 0, "max": 360},
                "climb_rate": {"type": "integer", "min": -100, "max": 100},
                "speed_target": {"type": "integer", "min": 200, "max": 400}
            }
        }


class MaintainPositionSkill(TacticalSkill):
    """Maintain position skill"""

    def __init__(self, params):
        super().__init__("maintain_position", params)
        self.default_params = {
            "altitude_target": 8000,
            "speed_target": 250
        }
        self.params = {**self.default_params, **params}

    def _execute(self, obs):
        """Execute maintain position"""
        self_status = obs.get("self_status", {}).get("position", {})
        current_alt = self_status.get("altitude_m", 8000)
        current_speed = obs.get("self_status", {}).get("performance", {}).get("speed_mps", 250)

        action = {
            "skill_name": self.skill_name,
            "delta_heading": 0,
            "delta_altitude": (self.params["altitude_target"] - current_alt) / 10,
            "delta_speed": (self.params["speed_target"] - current_speed) / 10,
            "shoot": 0,
            "completed": False
        }

        return action, False

    def get_schema(self):
        """Get parameter schema"""
        return {
            "parameters": {
                "altitude_target": {"type": "integer", "min": 1000, "max": 15000},
                "speed_target": {"type": "integer", "min": 150, "max": 400}
            }
        }