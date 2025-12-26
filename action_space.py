import numpy as np
from gymnasium import spaces
from typing import TYPE_CHECKING, Dict, List, Tuple

max_delta_heading = np.deg2rad(45.)
max_delta_altitude = 80
max_delta_speed = 80

class CampusActionSpace:
    def __init__(self):
        # Action space: discrete 3D control
        # heading: 15 discrete values (0-14)
        # altitude: 15 discrete values (0-14)
        # speed: 9 discrete values (0-8)
        # shoot: 2 discrete values (0, 1)
        self.action_space = spaces.MultiDiscrete([15, 15, 9, 2])
        self.action_space_mid_value = np.array([7, 7, 4, 0.5], dtype=float)
        # self.action_space_mid_value = (self.action_space.nvec - 1) / 2

    def is_dict_action(self, action) -> bool:
        return isinstance(action, dict)

    def is_array_action(self, action) -> bool:
        return isinstance(action, (np.ndarray, list))

    def dict_to_array(self, action_dict: Dict) -> np.ndarray:
        arr = np.array([
            float(action_dict['delta_heading']),
            float(action_dict['delta_altitude']),
            float(action_dict['delta_speed']),
            float(action_dict['shoot'])
        ], dtype=float)
        return self.std1_to_md(arr)

    def array_to_dict(self, action_array) -> Dict:
        action_array = self.md_to_std1(action_array)
        return {
            'delta_heading': float(action_array[0]),
            'delta_altitude': float(action_array[1]),
            'delta_speed': float(action_array[2]),
            'shoot': float(action_array[3]),
            'other_commands': {}
        }

    def extract_other_commands(self, action) -> Dict:
        if self.is_dict_action(action):
            return action.get('other_commands', {})
        elif self.is_array_action(action):
            return {}
        else:
            raise ValueError(f"Unsupported action type: {type(action)}")

    # def _unnorm_campus_action(self, act: np.ndarray, agent: Aircraft) -> np.ndarray:
    #     # Convert discrete action to continuous 3D control
    #     act = np.array(act.copy(), dtype=float)

    #     act[0] = (act[0] - 1) * agent.max_turn_rate  # -1, 0, +1
    #     act[1] = (act[1] - 1) * agent.max_climb_rate  # -1, 0, +1
    #     act[2] = (act[2] - 1) * agent.max_acceleration  # -1, 0, +1
    #     return act

    def md_to_std1(self, act: np.ndarray) -> np.ndarray:
        # Convert discrete action to continuous 3D control
        act = np.array(act.copy(), dtype=float)
        act[0] = (act[0] - self.action_space_mid_value[0]) / self.action_space_mid_value[0]  # -1, 0, +1
        act[1] = (act[1] - self.action_space_mid_value[1]) / self.action_space_mid_value[1]  # -1, 0, +1
        act[2] = (act[2] - self.action_space_mid_value[2]) / self.action_space_mid_value[2]  # -1, 0, +1
        return act
    
    def std1_to_md(self, act: Dict, quantilize: bool = False) -> Dict:
        act = act.copy()
        act['delta_heading'] = act['delta_heading'] * self.action_space_mid_value[0] + self.action_space_mid_value[0]
        act['delta_altitude'] = act['delta_altitude'] * self.action_space_mid_value[1] + self.action_space_mid_value[1]
        act['delta_speed'] = act['delta_speed'] * self.action_space_mid_value[2] + self.action_space_mid_value[2]

        if quantilize:
            act['delta_heading'] = np.round(act['delta_heading'])
            act['delta_altitude'] = np.round(act['delta_altitude'])
            act['delta_speed'] = np.round(act['delta_speed'])
        return act

    # def unnorm_campus_action(self, act: np.ndarray) -> np.ndarray:
    #     # Convert discrete action to continuous 3D control
    #     act = np.array(act.copy(), dtype=float)

    #     act = self.md_to_std1(act)

    #     act[0] *= max_delta_heading
    #     act[1] *= max_delta_altitude
    #     act[2] *= max_delta_speed
    #     return act

    def legacy_norm_campus_action(self, act: Dict, to_std1: bool = False, quantilize: bool = False) -> Dict:
        act = act.copy()

        act['delta_heading'] = np.clip(float(act['delta_heading']), -max_delta_heading, max_delta_heading)/max_delta_heading
        act['delta_altitude'] =np.clip(float(act['delta_altitude']), -max_delta_altitude, max_delta_altitude)/max_delta_altitude
        act['delta_speed'] =   np.clip(float(act['delta_speed']), -max_delta_speed, max_delta_speed)/max_delta_speed

        if not to_std1:
            act = self.std1_to_md(act, quantilize=quantilize)
        return act

    # def _unnorm_campus_action(self, act: np.ndarray, agent: Aircraft) -> np.ndarray:
    #     # Convert discrete action to continuous 3D control
    #     act = np.array(act.copy(), dtype=float)

    #     act[0] = act[0] - 1  # -1, 0, +1
    #     act[1] = act[1] - 1  # -1, 0, +1
    #     act[2] = act[2] - 1  # -1, 0, +1
    #     return act

    # def _norm_campus_action(self, act: Dict, agent: Aircraft) -> Dict:
    #     act = act.copy()
    #     act['delta_heading']  = float(act['delta_heading'] ) + 1
    #     act['delta_altitude'] = float(act['delta_altitude']) + 1
    #     act['delta_speed']    = float(act['delta_speed']   ) + 1
    #     return act

