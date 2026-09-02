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
python -m bvr_sim_rl --backend cpp --config scripts/tests/demo_config_cpp.jsonc \
  --timesteps 100000 --num-envs 8 --rollouts 256
```

The installed console entry point is equivalent:

```bash
bvr-sim-ppo --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

## Train With The Python Backend

```bash
python -m bvr_sim_rl --backend python --config scripts/tests/demo_config.json \
  --timesteps 100000 --num-envs 8 --rollouts 256
```

## Notes

The simulator action space is `MultiDiscrete([15, 15, 9, 2])`. The PPO helper
uses four categorical policy branches with 15, 15, 9, and 2 logits. The action
optimized by PPO is therefore exactly the action executed by the simulator;
there is no continuous surrogate or post-sampling rounding step.

`--num-envs` creates complete independent simulator instances. Aircraft in one
battle are not treated as vector environments because they share state,
termination, and reset. The PPO adapter currently requires one RL-controlled
red aircraft per instance and a scripted blue opponent. The default is 8,
following the parallel trajectory sampling used by the UHRL setup while
keeping local resource use moderate.

`--timesteps` counts vector steps, so collected transitions are approximately
`timesteps * num_envs`. For the default 1,000-step BVR horizon, use at least
`--rollouts 256`; the former 64-step single-instance batches were small and
highly correlated.

TensorBoard additionally records `Info / return_per_step` for completed
episodes. Prefer it to raw episode return when episode lengths are changing:
an improving policy that survives twice as long can otherwise accumulate more
step costs even while its reward rate and combat behavior improve.

Training logs and checkpoints are written under:

```text
runs/bvr_sim_rl/
```

For learning runs, use the convergence configuration ported from the UHRL
1v1 F16 setup:

```bash
python -m bvr_sim_rl --backend cpp \
  --config scripts/experiments/ppo/f16_1v1_convergence_cpp.jsonc \
  --timesteps 100000 --num-envs 8 --rollouts 256 --seed 1111 \
  --logdir runs/bvr_sim_rl/f16_1v1_seed1111
```

The demo and paper configurations are simulator examples and reproducibility
artifacts, respectively; their reward weights are not the recommended PPO
training objective. In particular, an absolute negative distance reward makes
longer surviving episodes accumulate a lower return and can make a better
policy look worse in the training curve.

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
python -m bvr_sim_rl --backend cpp --config scripts/tests/demo_config_cpp.jsonc \
  --timesteps 128 --num-envs 1 --rollouts 16
```
