<h2 align="center"><em>BVR Sim</em>: A Fast RL Environment for Heterogeneous Air-Combat</h2>

<p align="center"><sub>English | <a href="README_zh-CN.md">简体中文</a></sub></p>

<p align="center">
  <img alt="Python 3.8+" src="https://img.shields.io/badge/Python-3.8%2B-3776AB?logo=python&logoColor=white">
  <img alt="C++ backend" src="https://img.shields.io/badge/C%2B%2B-backend-00599C?logo=cplusplus&logoColor=white">
  <img alt="Gymnasium compatible" src="https://img.shields.io/badge/Gymnasium-RL-16A085">
  <img alt="PPO with skrl" src="https://img.shields.io/badge/PPO-skrl-7A3E9D">
  <img alt="License GPLv3" src="https://img.shields.io/badge/License-GPLv3-blue">
</p>

BVR-Sim is a 3D beyond-visual-range air-combat environment for reinforcement-learning research, with Python and accelerated C++ backends and a built-in skrl PPO training pipeline for immediate experimentation.

<div align="center">

| Heterogeneous F-22/F-16 6v6 | Human–AI Real-Time Air Combat | Heterogeneous Air Combat + Ground Air Defense |
|:---:|:---:|:---:|
| <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/f22-f16-heterogeneous-6v6.mp4"><img src=".github/media/demos/thumbnails/f22-f16-heterogeneous-6v6.jpg" width="100%" alt="Heterogeneous F-22 and F-16 6-vs-6 engagement"></a> | <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/human-ai-realtime-air-combat.mp4"><img src=".github/media/demos/thumbnails/human-ai-realtime-air-combat.jpg" width="100%" alt="Human and AI real-time air-combat game"></a> | <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/heterogeneous-air-ground-rl.mp4"><img src=".github/media/demos/thumbnails/heterogeneous-air-ground-rl.jpg" width="100%" alt="Heterogeneous air combat and ground air-defense reinforcement learning"></a> |

| Well-Tuned IPPO: 2v2 | Composite Missile Guidance + FDM | UnrealCV + UE5 Real-Time Rendering |
|:---:|:---:|:---:|
| <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/ippo-2v2.mp4"><img src=".github/media/demos/thumbnails/ippo-2v2.jpg" width="100%" alt="Well-tuned IPPO in a 2-vs-2 engagement"></a> | <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/missile-composite-guidance-fdm.mp4"><img src=".github/media/demos/thumbnails/missile-composite-guidance-fdm.jpg" width="100%" alt="Composite missile guidance with flight dynamics"></a> | <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/unrealcv-ue5-realtime-rendering.mp4"><img src=".github/media/demos/thumbnails/unrealcv-ue5-realtime-rendering.jpg" width="100%" alt="UnrealCV and Unreal Engine 5 real-time rendering"></a> |

</div>

<p align="center">
  <img src="docs/assets/game-mode.png" alt="BVR Sim game mode cockpit view" width="90%">
</p>

## System Architecture

<p align="center">
  <img src=".github/media/paper/system-architecture.png" width="100%" alt="BVR Sim system architecture">
</p>

The shared tactical interface maps heading, altitude, speed, and fire commands to aircraft-specific inner-loop controllers. Simulation, learning interfaces, and optional telemetry or rendering remain decoupled, allowing the same scenario to run through the Python reference backend or accelerated C++ backend.

## Supported Aircraft

The C++ JSBSim backend currently provides mappings for the following aircraft families:

- F-15
- F-16
- F/A-18
- F-22
- F-4N Phantom II
- AJ 37 and JA 37 Viggen

Different aircraft models, controller parameters, sensors, and weapon loadouts can coexist in the same scenario.

## Environment Comparison

The following comparison reproduces Table 1 of the paper for the cited public releases. A cross means that documented or direct support was not found in the corresponding release.

<div align="center">

| Capability | BVR Gym [3] | LAG [4, 5] | B-ACE [6] | BVR Sim |
|:---|:---:|:---:|:---:|:---:|
| Open source | ✓ | ✓ | ✓ | ✓ |
| JSBSim aircraft dynamics | ✓ | ✓ | × | ✓ |
| BVR-class missile engagement | ✓ | × | ✓ | ✓ |
| Mixed aircraft models in one scenario | × | × | × | ✓ |
| Built-in maneuver-and-fire interface | Maneuver only | ✓ | ✓ | ✓ |
| Interchangeable Python/native C++ backends | × | × | × | ✓ |
| Uniform fixed-width entity table | × | × | × | ✓ |
| Rule baseline and self-play | ✓ | ✓ | ✓ | ✓ |
| ACMI/Tacview export or telemetry | ✓ | ✓ | × | ✓ |
| Real-time 3D visualization | FlightGear | Tacview | Godot | Native viewers |

</div>

## MARL Validation

<p align="center">
  <img src=".github/media/paper/marl-training-reward.png" width="78%" alt="HAPPO and MAPPO mean episode reward on the BVR Sim 2v2 task">
</p>

The archived HAPPO [8] and MAPPO [7] traces above reproduce Fig. 3 of the paper and verify end-to-end integration on the same 2-vs-2 BVR task. Each curve is from one run, so the figure is an integration check rather than an algorithm ranking.

## Performance

BVR Sim provides two complementary flight-dynamics paths for different stages of reinforcement-learning development.

<div align="center">

| JSBSim FDM: Well-Tuned PPO 1v1 | Simple FDM: Rapid RL Validation |
|:---:|:---:|
| <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/ppo-1v1.mp4"><img src=".github/media/demos/thumbnails/ppo-1v1.jpg" width="100%" alt="Well-tuned PPO with JSBSim flight dynamics in a 1-vs-1 engagement"></a> | <a href="https://cdn.jsdelivr.net/gh/lizi-Margin/bvr_sim@master/.github/media/demos/simple-fdm-rl.mp4"><img src=".github/media/demos/thumbnails/simple-fdm-rl.jpg" width="100%" alt="Rapid reinforcement-learning validation with Simple FDM"></a> |

</div>

The JSBSim FDM path provides higher-fidelity, near-realistic aircraft dynamics for flight-control and engagement studies. Simple FDM is a lightweight alternative for fast RL pipeline validation, reward debugging, and early convergence checks.

Table 3 of the paper reports headless throughput at a 0.4-second decision interval. Values are mean ± standard deviation over three repeats.

<div align="center">

| Scale | Python steps/s | C++ steps/s | Speedup |
|:---:|---:|---:|---:|
| 1v1 | 95.84 ± 8.07 | 260.65 ± 2.75 | 2.72× |
| 2v2 | 51.01 ± 8.09 | 143.58 ± 4.56 | 2.81× |
| 4v4 | 22.43 ± 3.30 | 88.36 ± 16.56 | 3.94× |
| 6v6 | 13.07 ± 1.18 | 51.21 ± 12.33 | 3.92× |
| 8v8 | 9.63 ± 1.24 | 42.01 ± 12.06 | 4.36× |
| 10v10 | 8.46 ± 1.61 | 55.43 ± 38.71 | 6.55× |

</div>

## Core Features

- JSBSim-based flight-dynamics modeling [9]
- Air-to-air missile, loadout, launch, and engagement-outcome simulation
- Configurable red and blue teams, initial states, weapons, rule-based opponents, and reward terms
- Gymnasium-style observation and action spaces
- Pure-Python backend for inspection, debugging, and rapid validation
- C++ backend for performance-intensive training and simulation
- Tacview-compatible `.acmi` replay output
- Built-in lightweight PPO training helper in `bvr_sim_rl`
- Web, OpenGL, and DX11 visualization paths

## Supported Reinforcement-Learning Frameworks

- **skrl**: the repository includes the lightweight `bvr_sim_rl/` PPO entry point for installation checks, training, and evaluation. See the [skrl project](https://github.com/Toni-SM/skrl).
- **MARLBenchmark / off-policy**: [`rl_envs/env_marlbenchmark.py`](rl_envs/env_marlbenchmark.py) provides per-agent observations, centralized shared observations, and legacy Gym space interfaces. See the upstream [marlbenchmark/off-policy](https://github.com/marlbenchmark/off-policy) framework and the [lizi-Margin/off-policy](https://github.com/lizi-Margin/off-policy) branch maintained for this project.
- **HARL**: [`rl_envs/env_harl.py`](rl_envs/env_harl.py) implements HARL's local/shared observations, rewards, done flags, information dictionaries, and available-action tuple. See [PKU-MARL/HARL](https://github.com/PKU-MARL/HARL) and the corresponding paper, *Heterogeneous-Agent Reinforcement Learning* [1].
- **UHRL / HMP2G**: [`rl_envs/env_wrapper.py`](rl_envs/env_wrapper.py) targets the internal UHRL branch and implements `ScenarioConfig`, `make_env`, team mapping, state, and available-action interfaces. UHRL is a private branch developed from the public [HMP2G](https://github.com/binary-husky/hmp2g) framework; see Unreal-MAP [2] for the public background and application of HMP2G.

MARLBenchmark and UHRL support here means that framework interfaces are implemented; it does not imply validation of every algorithm provided by those frameworks. All adapters can select either the Python or C++ simulation backend.

## Quick Start: Train PPO Directly

Run all commands below from the repository root.

### 1. Create a Virtual Environment

Python 3.8 or later is required; Python 3.10 or later is recommended.

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Linux/macOS:

```bash
source .venv/bin/activate
```

### 2. Install the Project and Training Dependencies

```bash
pip install -e ".[rl]"
```

If the current shell does not accept the quoted extras syntax, install in two steps:

```bash
pip install -e .
pip install skrl torch
```

### 3. Train with the Python Backend

The Python backend requires no native-extension build and is suitable for initial installation and training-workflow checks.

```bash
python -m bvr_sim_rl --backend python --config scripts/tests/demo_config.json --timesteps 10000
```

To perform a short end-to-end check:

```bash
python -m bvr_sim_rl --backend python --config scripts/tests/demo_config.json --timesteps 128 --rollouts 16 --device cpu
```

Training logs and checkpoints are written by default to:

```text
runs/bvr_sim_rl/
```

### 4. Train with the C++ Backend

The C++ backend is intended for longer, higher-throughput training. Build the native extension first.

Windows:

```powershell
bvr_sim\build_windows.bat
```

Linux:

```bash
bash bvr_sim/build_linux.sh
```

Then run:

```bash
python -m bvr_sim_rl --backend cpp --config scripts/tests/demo_config_cpp.jsonc --timesteps 10000
```

After installation, the command-line entry point is also available:

```bash
bvr-sim-ppo --backend cpp --config scripts/tests/demo_config_cpp.jsonc --timesteps 10000
```

## Minimal Python Example

Pure-Python backend:

```python
import json
from bvr_sim import BVR3DEnv

with open("scripts/tests/demo_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

env = BVR3DEnv(config, logdir="./test_logs")
obs, info = env.reset()

done = False
while not done:
    obs, reward, dones, info = env.step({})
    done = info["episode_done"]
```

C++ backend:

```python
import commentjson
from bvr_sim import BVR3DEnvCpp

with open("scripts/tests/demo_config_cpp.jsonc", "r", encoding="utf-8") as f:
    config = commentjson.load(f)

env = BVR3DEnvCpp(config, rl_index=[0], log_file_path="./test_logs/bvr_sim.log")
obs, info = env.reset()

done = False
while not done:
    action = env.action_space.sample().reshape(1, -1)
    obs, reward, dones, info = env.step(action)
    done = info["episode_done"]
```

## PPO Training Entry Point

The lightweight training module is located at:

```text
bvr_sim_rl/
```

It creates either `BVR3DEnv` or `BVR3DEnvCpp`, converts simulator observations into tensors accepted by `skrl`, and quantizes the continuous actions produced by PPO back into the simulator's discrete actions.

The simulator's native action space is:

```text
MultiDiscrete([15, 15, 9, 2])
```

The four dimensions represent:

```text
delta_heading, delta_altitude, delta_speed, shoot
```

The PPO side uses a continuous action space:

```text
Box(-1, 1, shape=(4,))
```

See [docs/rl/ppo_quickstart.md](docs/rl/ppo_quickstart.md) for details.

## Validate the Simulator

Python backend smoke test:

```bash
python scripts/tests/test_py.py
```

C++ backend smoke test:

```bash
python scripts/tests/test_cpp.py
```

C++ unit tests:

```bash
python scripts/tests/cpp_unit_tests.py
```

Run the complete test suite, which rebuilds the native extension:

```bash
python scripts/run_tests.py
```

## Replay Output

Some tests and examples generate Tacview-compatible replays at:

```text
test_logs/*.acmi
```

Open the `.acmi` files with Tacview to inspect an engagement.

## Visualization

The C++ backend provides several real-time visualization paths:

- Web visualization: `EmbeddedWebServer` + `bvr_sim/web/`
- Native OpenGL viewer
- Native Windows DX11 game mode

After building the C++ backend, run:

```bash
python scripts/experimental/run_web_viz.py
python scripts/experimental/run_opengl_viz.py
python scripts/experimental/run_dx11_viz.py
```

## Documentation Navigation

<p align="center">
  <a href="https://www.bilibili.com/video/BV115SvBaEGn">Demo Video</a>
  ·
  <a href="docs/getting_started.md">Quick Start</a>
  ·
  <a href="docs/rl/ppo_quickstart.md">PPO Training</a>
  ·
  <a href="docs/configuration.md">Configuration</a>
  ·
  <a href="docs/integration.md">RL Integration</a>
</p>

## Documentation Index

- [Getting Started](docs/getting_started.md)
- [PPO Training Guide](docs/rl/ppo_quickstart.md)
- [Installation](docs/installation.md)
- [Configuration](docs/configuration.md)
- [External RL Framework Integration](docs/integration.md)
- [Developer Architecture](docs/developer/architecture.md)

## Project Structure

```text
.github/
  media/                     README demo videos, thumbnails, and paper figures
bvr_sim/                     Main Python package and C++ sources
  src_py/                    Python simulation, rewards, and rule-based opponents
  src_cxx/                   C++ simulation core
  web/                       Web visualization frontend
bvr_sim_rl/                  Lightweight skrl PPO training entry point
scripts/                     Development and evaluation entry points
  benchmarks/               Benchmark configurations and scripts
  experimental/             Experimental scenarios and visualization examples
  experiments/paper/        Paper experiment scripts and configurations
  tests/                    Smoke tests and unit tests
docs/                        Documentation, design notes, and usage guides
```

Do not edit generated directories manually:

```text
bvr_sim/build/
bvr_sim/install/
test_logs/
benchmark_logs/
runs/
```

## License

BVR Sim is released under GPLv3. See [LICENSE](LICENSE).

For third-party dependencies and bundled-resource notices, see [docs/legal/THIRD_PARTY_LICENSES.md](docs/legal/THIRD_PARTY_LICENSES.md).

## References

1. Yifan Zhong, Jakub Grudzien Kuba, Xidong Feng, Siyi Hu, Jiaming Ji, and Yaodong Yang. “Heterogeneous-Agent Reinforcement Learning.” *Journal of Machine Learning Research*, 25(32):1–67, 2024. [Paper](https://jmlr.org/papers/v25/23-0488.html)
2. Tianyi Hu, Qingxu Fu, Zhiqiang Pu, Yuan Wang, and Tenghai Qiu. “Unreal-MAP: Unreal-Engine-Based General Platform for Multi-Agent Reinforcement Learning.” *Proceedings of the AAAI Conference on Artificial Intelligence*, 40(35):29486–29494, 2026. [Paper](https://ojs.aaai.org/index.php/AAAI/article/view/40190) · [DOI](https://doi.org/10.1609/aaai.v40i35.40190)
3. Edvards Scukins, Markus Klein, Lars Kroon, and Petter Ögren. “BVR Gym: A Reinforcement Learning Environment for Beyond-Visual-Range Air Combat.” *arXiv preprint arXiv:2403.17533*, 2024. [Paper](https://arxiv.org/abs/2403.17533) · [DOI](https://doi.org/10.48550/arXiv.2403.17533)
4. Qihan Liu, Yuhua Jiang, and Xiaoteng Ma. “Light Aircraft Game: A Lightweight, Scalable, Gym-Wrapped Aircraft Competitive Environment with Baseline Reinforcement Learning Algorithms.” GitHub repository, 2022. [Repository](https://github.com/liuqh16/LAG)
5. Hanzhong Cao. “Light Aircraft Game: Basic Implementation and Training Results Analysis.” *arXiv preprint arXiv:2506.14164*, 2025. [Paper](https://arxiv.org/abs/2506.14164)
6. André R. Kuroswiski, Annie S. Wu, and Angelo Passaro. “B-ACE: An Open Lightweight Beyond Visual Range Air Combat Simulation Environment for Multi-Agent Reinforcement Learning.” *2024 Interservice/Industry Training, Simulation and Education Conference (I/ITSEC)*, Paper No. 24464, 2024.
7. Chao Yu, Akash Velu, Eugene Vinitsky, Jiaxuan Gao, Yu Wang, Alexandre Bayen, and Yi Wu. “The Surprising Effectiveness of PPO in Cooperative Multi-Agent Games.” *Advances in Neural Information Processing Systems*, 35:24611–24624, 2022. [DOI](https://doi.org/10.52202/068431-1787)
8. Jakub Grudzien Kuba, Ruiqing Chen, Muning Wen, Ying Wen, Fanglei Sun, Jun Wang, and Yaodong Yang. “Trust Region Policy Optimisation in Multi-Agent Reinforcement Learning.” *International Conference on Learning Representations*, 2022. [Paper](https://openreview.net/forum?id=EcGGFkNTxdJ)
9. Jon S. Berndt. “JSBSim: An Open Source Flight Dynamics Model in C++.” *AIAA Modeling and Simulation Technologies Conference and Exhibit*, AIAA Paper 2004-4923, 2004.
