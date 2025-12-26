import json, os
import numpy as np
from typing import Dict, Tuple, Optional
from gymnasium import spaces
from .spawn_manager import SpawnManager
from .action_space import CampusActionSpace
from .performance import StepProfiler


PRINT_STEP_TIME = False


import importlib

auto_import = False
try:
    import MISSION.bvr_sim.install.lib.bvr_sim_cpp as bvr_sim_cpp
    print(f"Successfully imported bvr_sim_cpp")
except ImportError as e:
    auto_import = True
    raise e

# if auto_import:
#     lib_dir = "MISSION/bvr_sim/install/lib"
#     lib_files = os.listdir(lib_dir)
#     for lib_file in lib_files:
#         if lib_file.endswith(".pyd"):
#             lib_name = lib_file[:-4]
#             if '.' in lib_name:
#                 lib_name = lib_name[:lib_name.find(".") + 1]
#             try:
#                 # import as bvr_sim_cpp
#                 bvr_sim_cpp = importlib.import_module(f"{lib_dir}/{lib_name}")
#                 print(f"Successfully imported {lib_name}")
#                 break
#             # except ImportError:
#             #     print
#             #     pass
#             finally:
#                 pass
# import MISSION.bvr_sim.install.bvr_sim_cpp_native as bvr_sim_cpp

os.environ["JSBSIM_DEBUG"] = "0"

class BVR3DEnvCpp:
    """BVR 3D environment adapter for C++ simulation core (new 3-segment protocol)"""

    def __init__(self, config: Dict):
        self.config = config
        self.dt = config.get("dt", 0.4)
        self.core = bvr_sim_cpp.SimCore(dt=self.dt)

        self.max_steps = config.get('max_steps', 1200)

        if config.get("cpp_env_init_file", None) is not None:
            import commentjson
            with open(config["cpp_env_init_file"], 'r') as f:
                init_config = commentjson.load(f)
            self.red_meta = init_config['red_meta']
            self.blue_meta = init_config['blue_meta']
        else:
            self.red_meta: Dict = config.get("red_meta", {})
            self.blue_meta: Dict = config.get("blue_meta", {})
        self.num_red = len(self.red_meta)
        self.num_blue = len(self.blue_meta)
        self.red_ids = list(self.red_meta.keys())
        self.blue_ids = list(self.blue_meta.keys())

        self.n_agents = self.num_red + self.num_blue
        self.agent_uids = list(self.red_meta.keys()) + list(self.blue_meta.keys())

        # Determine controllable teams (ego_ids)
        self.blue_opponent_type = config.get('blue_opponent_type', 'tactical')
        if self.blue_opponent_type is None:
            self.ego_ids = self.red_ids + self.blue_ids  # Both teams controllable
        else:
            self.ego_ids = self.red_ids  # Only red team controllable

        self.spawn_manager = SpawnManager(config)


        # cpp rl manager
        self.rl_manager = bvr_sim_cpp.RLManager()
        self.disable_render()  # by default, core render acmi files, we disable it here
        
        # obs
        obs_type = config.get('obs_type', 'entity')
        self.rl_manager.set_observation_space(obs_type)

        # reward
        reward_config = config.get('reward_config', {})
        self.rl_manager.load_reward_config_str(json.dumps(reward_config))

        # Action space
        self.act_manager = CampusActionSpace()

        # Current step counter
        self.current_step = 0

        self._step_profiler = StepProfiler(name=self.__class__.__name__) if PRINT_STEP_TIME else None


        # i don't want to pass red/blue num to the cpp core, so just reset, then call get_obs_dim, use internal state
        self.reset()
        # space export
        self._setup_spaces()

    def _setup_spaces(self):
        """Setup observation and action spaces"""
        # Observation space (uses pluggable system)
        obs_dim = self.rl_manager.get_obs_dim()
        self.obs_length = obs_dim

        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(obs_dim,) if isinstance(obs_dim, int) else obs_dim,
            dtype=np.float32
        )
        self.action_space = self.act_manager.action_space

    def enable_render(self, filepath: str):
        """Enable render to filepath"""
        self.core.set_acmi_file_path(filepath)
    
    def disable_render(self):
        """Disable render"""
        self.core.set_acmi_file_path("")


    # ============================================================
    # Reset
    # ============================================================
    def reset(self, seed: Optional[int] = None) -> Tuple[np.ndarray, Dict]:
        """Reset simulation and initialize all agents"""

        if seed is not None:
            np.random.seed(seed)

        self.current_step = 0
        result = self.core.handle("clear all {}")
        assert isinstance(result, dict), f"Failed to clear all units: {result}"
        assert result.get("status") == "ok", f"Failed to clear all units: {result}"
        self.core.step_sync(1)
        for uid in self.ego_ids:
            self._override_baseline_action(uid)

        self.rl_manager.reset()

        # Generate randomized spawn positions
        red_positions, blue_positions, engagement_axis = self.spawn_manager.generate_spawn(
            self.num_red, self.num_blue
        )

        init_spec = self.red_meta.copy()
        init_spec.update(self.blue_meta)

        # Build initialization spec for red
        for i, uid in enumerate(self.red_ids):
            position = red_positions[i]

            # Heading: face towards enemy (along engagement axis)
            heading = engagement_axis
            speed = 300.0
            velocity = np.array([
                speed * np.cos(heading),
                speed * np.sin(heading),
                0.0  # Initially level flight
            ])
            init_spec[uid]["position"] = position.tolist()
            init_spec[uid]["velocity"] = velocity.tolist()


        # Build initialization spec for blue
        for i, uid in enumerate(self.blue_ids):
            position = blue_positions[i]

            # Heading: face towards enemy (opposite direction)
            heading = engagement_axis + np.pi  # 180 degrees opposite
            speed = 300.0
            velocity = np.array([
                speed * np.cos(heading),
                speed * np.sin(heading),
                0.0  # Initially level flight
            ])
            init_spec[uid]["position"] = position.tolist()
            init_spec[uid]["velocity"] = velocity.tolist()



        for uid, config in init_spec.items():
            init_cmd = f"init {uid} {json.dumps(config)}"
            result = self.core.handle(init_cmd)
            if not isinstance(result, dict) or result.get("status") != "ok":
                raise RuntimeError(f"Failed to initialize units: {result}")

        # Get initial observations
        obs = self._get_observations()
        info = self._get_info()

        # Return observations for ego_ids (red only, or red+blue for self-play)
        ego_obs = {uid: obs[uid] for uid in self.ego_ids}
        return self._pack_obs(ego_obs), info
    
    def _override_baseline_action(self, uid: str):
        control_action = {
            "delta_heading": 0.0,
            "delta_altitude": 0.0,
            "delta_speed": 0.0
        }
        self.core.handle(f"set {uid} {json.dumps(control_action)}")
        self._handle_shoot_action(uid, shoot=False)

    # ============================================================
    # Step
    # ============================================================
    def step(self, action) -> Tuple[np.ndarray, np.ndarray, np.ndarray, Dict]:
        """Execute one simulation step"""

        if self._step_profiler:
            self._step_profiler.start()

        self.current_step += 1

        # Convert action array back to dictionary for each agent
        if isinstance(action, dict):
            actions = action
        else:
            actions = self._unpack_actions(action)

        if self._step_profiler:
            self._step_profiler.mark("handel_actions")
        # Execute actions for all agents
        for uid, action_array in actions.items():
            if uid not in self.agent_uids:
                continue  # Skip if agent doesn't exist

            # Convert array action to dict format
            action_dict = self.act_manager.array_to_dict(action_array)

            # Three-segment: set UID JSON
            control_action = {
                "delta_heading": float(action_dict['delta_heading']),
                "delta_altitude": float(action_dict['delta_altitude']),
                "delta_speed": float(action_dict['delta_speed'])
            }
            self.core.handle(f"set {uid} {json.dumps(control_action)}")
            # print(action_dict['shoot'])

            # Handle shooting
            if action_dict['shoot'] > 0.5:
                self._handle_shoot_action(uid, shoot=True)
            else:
                self._handle_shoot_action(uid, shoot=False)
             

        if self._step_profiler:
            self._step_profiler.mark("step_sync")

        # Step simulation
        self.core.step_sync(1)

        if self._step_profiler:
            self._step_profiler.mark("get ordi")
        # Get current state for info
        episode_done, dones, red_alive, blue_alive = self.episode_done()
        info = self._get_info()
        info.update({
            "episode_done": episode_done,
        })

        info_for_reward_calc = {
            "current_step": self.current_step,
            "episode_done": episode_done,
            "lastRLActions": actions,
            "actionNormFunc": self.act_manager.legacy_norm_campus_action,
        }

        # Compute obs, rewards, dones
        obs = self._get_observations()
        rewards = self._get_rewards(info_for_reward_calc)

        if episode_done:
            if red_alive > blue_alive:
                info["team_ranking"] = [0, 1]  # Red wins
            elif blue_alive > red_alive:
                info["team_ranking"] = [1, 0]  # Blue wins
            else:
                info["team_ranking"] = [-1, -1]  # Draw

        # Pack results for ego_ids (red only, or red+blue for self-play)
        ego_obs = {uid: obs[uid] for uid in self.ego_ids}
        ego_rewards = {uid: rewards[uid] for uid in self.ego_ids}
        ego_dones = {uid: dones[uid] for uid in self.ego_ids}

        if self._step_profiler:
            self._step_profiler.stop()
            self._step_profiler.report()

        return (
            self._pack_obs(ego_obs),
            self._pack_rewards(ego_rewards),
            self._pack_dones(ego_dones),
            info
        )

    # ============================================================
    # Observations
    # ============================================================
    def _get_observations(self) -> Dict[str, np.ndarray]:
        """Collect full observation for each agent using C++ RL manager"""
        obs = {}
        for uid in self.ego_ids:
            obs[uid] = self.rl_manager.get_observation(uid)

        return obs

    # ============================================================
    # Rewards
    # ============================================================
    def _get_rewards(self, info: dict) -> Dict[str, float]:
        """Calculate rewards for all agents using C++ RL manager"""
        rewards = {}
        for uid in self.ego_ids:
            rewards[uid] = self.rl_manager.get_reward(uid, info)
        return rewards
    
    def get_reward_breakdown(self, uid: str, info: dict) -> Dict[str, float]:
        """Calculate rewards breakdown for all agents using C++ RL manager"""
        return self.rl_manager.get_reward_breakdown(uid)

    # ============================================================
    # Dones
    # ============================================================
    def _get_dones(self) -> Dict[str, bool]:
        """Get done flags for ego agents"""
        dones = {}
        for uid in self.ego_ids:
            dones[uid] = self.rl_manager.get_done(uid)
        return dones

    def episode_done(self):
        """Check if the episode is done"""
        # Count alive agents in each team
        episode_done = self.rl_manager.get_episode_done()
        red_alive = self.red_ids.__len__()
        blue_alive = self.blue_ids.__len__()

        dones = self._get_dones()
        # RL_controlled_all_dead = bool(np.all(list(dones.values()), axis=None))
        RL_controlled_all_dead = False
        time_limit_reached = self.current_step >= self.max_steps
        episode_done = self.rl_manager.get_episode_done() or RL_controlled_all_dead or time_limit_reached

        for uid in self.red_ids:
            this_done = self.rl_manager.get_done(uid)
            if this_done:
                red_alive -= 1

        for uid in self.blue_ids:
            this_done = self.rl_manager.get_done(uid)
            if this_done:
                blue_alive -= 1
        
        if episode_done:
            dones = {uid: True for uid in self.ego_ids}

        if episode_done:
            if RL_controlled_all_dead:
                print(f"\nepsiode done, done reason = RL_controlled_all_dead, red_alive = {red_alive}, blue_alive = {blue_alive}")
            elif time_limit_reached:
                print(f"\nepsiode done, done reason = time_limit_reached, red_alive = {red_alive}, blue_alive = {blue_alive}")
            else:
                print(f"\nepsiode done, done reason = (cpp), red_alive = {red_alive}, blue_alive = {blue_alive}")

        return episode_done, dones, red_alive, blue_alive

    # ============================================================
    # Info
    # ============================================================
    def _get_info(self) -> Dict:
        expert_action = []
        for ui, baseline_action in self._get_baseline_action().items():
            md_action = self.act_manager.legacy_norm_campus_action({
                'delta_heading': baseline_action[0],
                'delta_altitude': baseline_action[1],
                'delta_speed': baseline_action[2],
                'shoot': baseline_action[3],
            }, to_std1=False, quantilize=True)
            
            expert_action.append([
                md_action['delta_heading'],
                md_action['delta_altitude'],
                md_action['delta_speed'],
                md_action['shoot'],
            ])
        expert_action = np.array(expert_action)
        expert_action = np.expand_dims(expert_action, 0)
        
        return {
            "current_step": self.current_step,
            "expert_action": expert_action,
            "episode_done": False,
        }
    
    def _get_baseline_action(self) -> Dict[str, np.ndarray]:
        expert_action = {}
        for uid in self.ego_ids:
            bsl_action = self.rl_manager.get_baseline_action_vec(uid)
            if bsl_action is None:
                print(f"Warning: Baseline action for agent {uid} is None.")
                assert False
            assert len(bsl_action) == 4, f"Baseline action for agent {uid} is not 4D"
            # if np.allclose(bsl_action, np.zeros(4)):
            #     print(f"Warning: Baseline action for agent {uid} is all zeros.")
            expert_action[uid] = bsl_action
        
        return expert_action


    # ============================================================
    # Shoot Action
    # ============================================================
    def _handle_shoot_action(self, uid: str, shoot = True):
        assert uid is not None, "uid is None"
        if shoot == False:
            # send the fire command to clear any pending fire orders
            self.core.handle(f"set {uid} {json.dumps({'fire': None})}")
            return
        # target_uid = self._find_nearest_enemy(uid)
        info = self.core.handle(f"get {uid} {{}}")
        if not isinstance(info, dict) or info.get("status") != "ok":
            # print(f"Warning: Failed to get info for agent {uid}, {info}")
            return
        enemies_lock = info["enemies_lock"]
        assert isinstance(enemies_lock, list), f"enemies_lock for agent {uid} is not a list, {enemies_lock}"
        if len(enemies_lock) == 0:
            # No enemy found, but still send the fire command to clear any pending fire orders
            # self.core.handle(f"set {uid} {json.dumps({'fire': {'nops': 114514}})}")
            self.core.handle(f"set {uid} {json.dumps({'fire': None})}")
            return

        fire_cmd = {
            "fire": {
                "target_uid": enemies_lock[0],
                "weapon_spec": "AIM-120C",
            }
        }

        self.core.handle(f"set {uid} {json.dumps(fire_cmd)}")

    # ============================================================
    # Nearest Enemy
    # ============================================================
    def _find_nearest_enemy(self, uid: str) -> Optional[str]:
        my_data = self.core.handle(f"get {uid} {{}}")
        if not isinstance(my_data, dict) or my_data.get("status") != "ok":
            if my_data['message'] == 'uid not found':
                return None
            print(f"Warning: Failed to get position for agent {uid}, {my_data}")
            return None
        my_pos = np.array(my_data["position"])
        assert len(my_pos) == 3, f"Position for agent {uid} is not 3D"

        is_red = uid in self.red_meta
        enemy_uids = list(self.blue_meta.keys()) if is_red else list(self.red_meta.keys())

        nearest_uid = None
        nearest_dist = float("inf")

        for enemy_uid in enemy_uids:
            data = self.core.handle(f"get {enemy_uid} {{}}")
            if isinstance(data, dict) and data.get("status") == "ok":
                enemy_pos = np.array(data["position"])
                try:
                    enemy_under_missiles_size = int(data["under_missiles.size()"])
                except (KeyError, ValueError):
                    enemy_under_missiles_size = 0
                    print(f"Warning: Failed to get under_missiles.size() for agent {enemy_uid}, {data}")
                assert len(enemy_pos) == 3, f"Position for agent {enemy_uid} is not 3D"
                dist = np.linalg.norm(my_pos - enemy_pos) + enemy_under_missiles_size * 10_000

                if dist < nearest_dist:
                    nearest_dist = dist
                    nearest_uid = enemy_uid
            else:
                print(f"Warning: Failed to get position for agent {enemy_uid}, {data}")

        return nearest_uid

    # ============================================================
    # Packing/Unpacking for gymnasium compatibility
    # ============================================================
    def _pack_obs(self, obs_dict: Dict[str, np.ndarray]) -> np.ndarray:
        """Pack observations into array"""
        return np.array([obs_dict[uid] for uid in self.ego_ids])

    def _pack_rewards(self, rewards_dict: Dict[str, float]) -> np.ndarray:
        """Pack rewards into array"""
        return np.array([rewards_dict[uid] for uid in self.ego_ids])

    def _pack_dones(self, dones_dict: Dict[str, bool]) -> np.ndarray:
        """Pack dones into array"""
        return np.array([dones_dict[uid] for uid in self.ego_ids])

    def _unpack_actions(self, actions: np.ndarray) -> Dict[str, np.ndarray]:
        """Unpack actions from array to dictionary"""
        actions_dict = {}
        for i, uid in enumerate(self.ego_ids):
            actions_dict[uid] = actions[i]
        return actions_dict

    # ============================================================
    # Cleanup
    # ============================================================
    def close(self):
        self.core.stop()

    def __del__(self):
        try:
            self.close()
        except:
            pass
