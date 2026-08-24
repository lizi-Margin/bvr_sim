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
uses four categorical policy branches with 15, 15, 9, and 2 logits. The action
optimized by PPO is therefore exactly the action executed by the simulator;
there is no continuous surrogate or post-sampling rounding step.

Training logs and checkpoints are written under:

```text
runs/bvr_sim_rl/
```

The command also writes a portable frozen-policy checkpoint named
`ppo_<backend>_seed<seed>.pt` in the selected log directory. Set the seed
explicitly for paper runs and evaluate without further learning:

```bash
python -m bvr_sim_rl --backend cpp --config experiments/paper/f16_1v1_cpp.jsonc \
  --timesteps 100000 --seed 1111 --logdir runs/paper/f16_1v1/seed_1111
python -m bvr_sim_rl.evaluate --backend cpp --config experiments/paper/f16_1v1_cpp.jsonc \
  --checkpoint runs/paper/f16_1v1/seed_1111/ppo_cpp_seed1111.pt \
  --episodes 500 --seed 30000 --output runs/paper/f16_1v1/seed_1111/eval.json
```

For a quick smoke run, reduce the number of timesteps:

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 128 --rollouts 16
```
