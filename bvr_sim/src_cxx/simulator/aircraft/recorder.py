import os, uuid
import numpy as np
from typing import List, Optional, Tuple, TYPE_CHECKING, Dict
from uhtk.UTIL.colorful import print亮绿, print亮蓝, print_red, print_green
from uhtk.imitation.utils import safe_dump_traj_pool
from .base import Aircraft



class AircraftRecorder:
    def __init__(self, aircraft: Aircraft, traj_limit: int = 2000):
        from uhtk.imitation.traj import trajectory
        self.uid = aircraft.uid
        self.aircraft = aircraft
        self.traj = trajectory(traj_limit=traj_limit, env_id=0)
        setattr(self.traj, 'action_dict', [])

    def step(self, true_obs: np.ndarray, action_dict: Dict) -> Dict:
        agent = self.aircraft
        if not agent.is_alive:
            return

        self.traj.remember('position', agent.position.astype(np.float32))
        self.traj.remember('velocity', agent.velocity.astype(np.float32))

        roll = agent.get_roll()
        pitch = agent.get_pitch()
        yaw = agent.get_heading()
        posture = np.array([roll, pitch, yaw], dtype=np.float32)
        self.traj.remember('posture', posture)

        speed_mps = agent.get_speed()
        mach = agent.get_mach()
        self.traj.remember('speed_mps', np.array([speed_mps], dtype=np.float32))
        self.traj.remember('mach', np.array([mach], dtype=np.float32))

        self.traj.remember('alive', np.array([float(agent.is_alive)], dtype=np.float32))

        self.traj.remember('obs', true_obs.astype(np.float32))

        self._handle_action(action_dict)
        self.traj.time_shift()
        
        return action_dict
    
    def _handle_action(self, action_dict: Dict):
        if 'shoot' in action_dict:
            shoot = action_dict['shoot']
            self.traj.remember('shoot', np.array(shoot, dtype=np.float32))
        else:
            raise ValueError("Action dict must contain 'shoot' key")

        if self.aircraft._is_compas_action(action_dict):
            delta_heading = action_dict['delta_heading']
            delta_altitude = action_dict['delta_altitude']
            delta_speed = action_dict['delta_speed']
            campas_action = np.array([delta_heading, delta_altitude, delta_speed], dtype=np.float32)
            self.traj.remember('campas_action', campas_action)
            self.traj.remember('campas_action_and_shoot', np.concatenate([campas_action, np.array([shoot], dtype=np.float32)]))
        if self.aircraft._is_physics_action(action_dict):
            aileron = action_dict['aileron']
            elevator = action_dict['elevator']
            throttle = action_dict['throttle']
            rudder = action_dict['rudder']
            physics_action = np.array([aileron, elevator, throttle, rudder], dtype=np.float32)
            self.traj.remember('physics_action', physics_action)
            self.traj.remember('physics_action_and_shoot', np.concatenate([physics_action, np.array([shoot], dtype=np.float32)]))
    
        
        if hasattr(self.traj, 'action_dict'):
            self.traj.action_dict.append(action_dict)

    def finalize(self):
        if self.traj.time_pointer > 0:
            self.traj.cut_tail()
        return self.traj
    
    def __len__(self):
        return self.traj.time_pointer


        
class AircraftRecorderManager:
    def __init__(self, traj_limit, max_len, save_dir):
        self.recorders: Dict[str, AircraftRecorder] = {}
        self.traj_limit = traj_limit
        self.save_dir = save_dir
        self.max_len = max_len
        self.completed_trajs: List = []
        self.completed_traj_names: List[str] = []
        self.episode_count = 0
        self.save_batch_count = 0


        # timestamp = time.strftime('%Y%m%d%H%M%S')
        self.pool_name = f"ACRecord_{uuid.uuid4().hex[:2]}"
        # self.traj_dir = f"{self.save_dir}/{self.pool_name}-{timestamp}-{uuid.uuid4().hex}"
        self.traj_dir = f"{self.save_dir}/AircraftRecorderManager-traj_dir"
        os.makedirs(self.traj_dir, exist_ok=True)

        self.last_obs = {}

    def register_aircraft(self, aircraft: Aircraft):
        uid = aircraft.uid
        # BUG # if uid not in self.recorders:
        self.recorders[uid] = AircraftRecorder(aircraft, traj_limit=self.traj_limit)

    def get_recorder(self, uid: str) -> AircraftRecorder:
        return self.recorders[uid]
    
    def reset(self):
        # print_red(f"[RecorderManager] reset, episode_count: {self.episode_count}")
        for uid, recorder in self.recorders.items():
            self.recorders[uid] = AircraftRecorder(recorder.aircraft, traj_limit=self.traj_limit)

    def on_episode_done(self):
        # print_green(f"[RecorderManager] on_episode_done, episode_count: {self.episode_count}")
        for uid, recorder in self.recorders.items():
            if len(recorder) > 0:
                traj = recorder.finalize()
                self.completed_trajs.append(traj)
                self.completed_traj_names.append(f"{self.pool_name}_{uid}_{recorder.aircraft.__class__.__name__}_{uuid.uuid4().hex[:4]}")
        self.reset()

        self.episode_count += 1

        if len(self.completed_trajs) >= self.max_len:
            self._save_trajectories()
    
    def __len__(self):
        return len(self.completed_trajs)
    
    def __contains__(self, uid: str) -> bool:
        return uid in self.recorders
    
    def set_last_obs(self, all_obs: Dict[str, np.ndarray]):
        self.last_obs = all_obs
    
    def step_recorder(self, uid: str, action_dict: Dict):
        if uid not in self.last_obs:
            raise ValueError(f"uid {uid} not in last_obs")
        true_obs = self.last_obs.pop(uid)
        recorder = self.get_recorder(uid)
        recorder.step(true_obs, action_dict)

    def _save_trajectories(self):
        if len(self.completed_trajs) == 0:
            return

        

        safe_dump_traj_pool(self.completed_trajs, self.completed_traj_names, traj_dir=self.traj_dir)

        # print亮绿(f"[RecorderManager] Saved {len(self.completed_trajs)} trajs to {self.traj_dir}/{self.pool_name}")

        self.completed_trajs = []
        self.completed_traj_names = []
        self.save_batch_count += 1

    def finalize(self):
        self._save_trajectories()
        # print(f"[RecorderManager] Finalized. Episodes: {self.episode_count}, Batches: {self.save_batch_count}")