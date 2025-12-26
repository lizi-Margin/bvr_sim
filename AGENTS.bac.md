# AGENT NOTES — BVR Sim Mission

This file captures repository knowledge for future Codex agents working inside `MISSION/bvr_sim`.

## Quick Start
- **Entry point:** `env_wrapper.py` exposes `ScenarioConfig` and `make_env` for UHRL. Training is launched via `python main.py --cfg MISSION/bvr_sim/conf_system/<cfg>.jsonc`.
- **Lightweight check:** Use `conf_system/random-1v1-test.jsonc` (or similar) for a fast smoke test.
- **Rendering:** Wrapper auto-creates Tacview `.txt.acmi` files under `<logdir>/acmi_recordings/` when `ScenarioConfig.render=True`.

## Directory Map
- `bvr_env.py` – Core Gymnasium-style environment. Handles action unpacking, physics stepping, reward aggregation, and info dict assembly.
- `env_wrapper.py` – Bridges the env with UHRL: MultiDiscrete action spec (`15×15×9×2`), observation space setup, reward visualization, and ACMI logging.
- `simulator/` – Physics stack:
  - `aircraft/` (e.g., `f16.py`) uses pluggable FDMs and encapsulates autopilot-style controls.
  - `missile/` contains AIM-120C variants with Mach-indexed drag tables (`aim120c_adv_sim.py`), gravity, and guidance logic.
  - `sense/` implements radar, radar warning, missile warning, and SA datalink sensors; `data_obj.py` serializes noisy detections.
- `observation_space.py` – Compact/Extended/Shadow encoders with missile warnings, lock indicators, and TTI features.
- `reward/` – Modular reward components plus `RewardManager`; `RewardVisualizer` plots per-component curves to `<logdir>/reward_plot_path`.
- `baseline_opponents/` – Scripted opponents (random/simple/tactical) usable as blue-team adversaries or distillation references.
- `spawn_manager.py` – Randomized spawn geometry (default 37.2 NM separation, 2 NM spread).
- `bvr_sim_arxiv.tex` – Short arXiv-style report summarizing the environment and comparisons to BVR-Gym, B-ACE, WUKONG.

## Key Behaviors / Gotchas
- **Observation setup:** Wrapper auto-derives `obs_shape` from `ScenarioConfig.obs_type` and injects ally/enemy relative states plus up to four in-flight friendly missiles (with missile-on-me indicators). Adjust ids/teams via `AGENT_ID_EACH_TEAM`.
- **Action mapping:** `bvr_env._unnorm_campus_action` scales MultiDiscrete bins into heading/altitude/speed deltas before commanding the FDM.
- **Reward shaping:** Dense components (engage_enemy, altitude_advantage, missile_evasion, etc.) and sparse components (launch/hit/win). Optional `DistillReward` compares RL actions against baseline tactical policies (`baseline_opponents/tactical_opponent.py`).
- **Distillation / teacher forcing:** Enable by setting `ScenarioConfig.reward_config.distill_reward_weight > 0`; optionally flip `USE_DISTILL_REWARD_ACTION = True` in `bvr_env.py` to have the tactical baseline action executed when computing the imitation penalty. This is useful for curriculum starts or safety-critical experiments where you need a fallback policy.
- **Trajectory recording:** `simulator/aircraft/recorder.py` logs obs, kinematics, Mach, command deltas, and shoot flags every step, then writes chunked pools to `<logdir>/aircraft_records/` via `safe_dump_traj_pool`. Data is produced automatically for all controllable aircraft once `cfg.logdir` is set—no extra toggles required.
- **Baseline fallback:** Red team gets default scripted policies (see `RED_BASELINE_TYPES`) when RL control is absent; blue team baseline type configurable via `ScenarioConfig.blue_opponent_type`.
- **Episode termination:** `BVR3DEnv` waits until all missiles in flight resolve before producing `team_ranking`; this prevents premature wins/losses for long-range shots. Keep this in mind when trimming `MaxEpisodeStep`.
- **Performance profiling:** Set `PRINT_STEP_TIME = True` (in `bvr_env.py` or `simulator/aircraft/f16.py`) to gather per-stage timing stats via `performance.StepProfiler`; output shows running mean/std for aircraft, missile, reward, and pack stages.

## Testing / Tooling Tips
- **Tacview review:** Open generated `.txt.acmi` files in Tacview to inspect flight paths and missile events.
- **Reward plots:** Confirm `ScenarioConfig.reward_plot_enabled`; outputs land in `<logdir>/reward_plot_path/` as PNG+JSON (symlog scale) per agent.
- **Distillation sweeps:** When iterating on imitation weights, add entries to `conf_system/*.jsonc` overriding `reward_config.distill_reward_weight` and, if needed, toggle `USE_DISTILL_REWARD_ACTION` for teacher forcing.
- **Spawn variance:** Modify `initial_separation_nm` and `formation_max_spread_nm` in `ScenarioConfig` for curriculum-style difficulty changes.

## References
- BVR-Gym (arXiv:2403.17533) – open PN-based env for comparison.
- B-ACE – Godot-based lightweight MARL sim.
- WUKONG (IEEE 2020) – self-play RL study; provides conceptual reward shaping (KAERS) but no public code.

Keep this file updated when major behaviors, configs, or workflows change.
