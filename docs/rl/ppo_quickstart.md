# PPO Quickstart

`bvr_sim_rl` is a lightweight training helper for running PPO on BVR Sim with
[`skrl`](https://github.com/Toni-SM/skrl). It supports both simulator backends:

- `--backend cpp`: uses `BVR3DEnvCpp`
- `--backend python`: uses `BVR3DEnv`

## Install

From the repository root:

```bash
pip install -e .
pip install skrl torch
```

Alternatively:

```bash
pip install -e ".[rl]"
```

## Train With The C++ Backend

Build the native extension first, then run PPO:

```bash
python run_tests.py
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

The installed console entry point is equivalent:

```bash
bvr-sim-ppo --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

## Train With The Python Backend

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 10000
```

## Notes

The simulator action space is `MultiDiscrete([15, 15, 9, 2])`. The PPO helper
exposes a continuous `Box(-1, 1, shape=(4,))` action space to skrl and quantizes
actions back to the simulator action before stepping.

Training logs and checkpoints are written under:

```text
runs/bvr_sim_rl/
```

For a quick smoke run, reduce the number of timesteps:

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 128 --rollouts 16
```
