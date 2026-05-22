# BVR Sim

面向强化学习的 3D 超视距空战仿真环境。

这个仓库的首页只解决一件事：让第一次接触项目的人，按步骤直接跑通一个 PPO 空战训练任务。更细的配置、架构、可视化说明放在 `docs/` 里。

## 你可以做什么

- 用 `skrl` 直接训练一个 PPO 策略
- 选择纯 Python 后端 `BVR3DEnv`，方便先跑通
- 选择 C++ 后端 `BVR3DEnvCpp`，用于更快训练
- 生成 Tacview 可打开的 `.acmi` 空战回放
- 修改飞机、武器、奖励、观测、规则对手和场景配置

## 最快跑通 PPO 训练

下面所有命令都在仓库根目录执行。

### 1. 创建 Python 环境

需要 Python 3.8+，推荐 Python 3.10+。

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

### 2. 安装项目和 RL 依赖

```bash
pip install -e ".[rl]"
```

如果你的 shell 不接受引号，可以分两步：

```bash
pip install -e .
pip install skrl torch
```

### 3. 先用 Python 后端训练

这一步不需要编译 C++，最适合新手确认环境能跑。

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 10000
```

如果只是想快速确认安装成功：

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 128 --rollouts 16 --device cpu
```

训练日志和 checkpoint 默认写到：

```text
runs/bvr_sim_rl/
```

### 4. 再切到 C++ 后端训练

C++ 后端更适合长时间训练。先编译原生扩展。

Windows:

```powershell
bvr_sim\build_windows.bat
```

Linux:

```bash
bash bvr_sim/build_linux.sh
```

然后运行：

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

安装后也可以用命令行入口：

```bash
bvr-sim-ppo --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

## 这个 PPO 例子做了什么

轻量训练代码在：

```text
bvr_sim_rl/
```

它做的事情很少：

1. 创建 `BVR3DEnv` 或 `BVR3DEnvCpp`
2. 把仿真观测转换成 `skrl` 可以使用的 tensor
3. 把 PPO 的连续动作转换回仿真器的离散动作
4. 用一个小 MLP 跑 PPO

仿真器原始动作空间是：

```text
MultiDiscrete([15, 15, 9, 2])
```

对应四个动作：

```text
delta_heading, delta_altitude, delta_speed, shoot
```

PPO 侧看到的是：

```text
Box(-1, 1, shape=(4,))
```

更详细的 RL 说明见：[docs/rl/ppo_quickstart.md](docs/rl/ppo_quickstart.md)

## 单独验证仿真器

Python 后端 smoke test:

```bash
python tests/test_py.py
```

C++ 后端 smoke test:

```bash
python tests/test_cpp.py
```

C++ unit tests:

```bash
python tests/cpp_unit_tests.py
```

完整测试，会重新编译原生扩展：

```bash
python run_tests.py
```

## 看空战回放

部分测试和示例会生成 Tacview 回放：

```text
test_logs/*.acmi
```

用 Tacview 打开 `.acmi` 文件即可查看空战过程。

## 最小 Python 调用示例

纯 Python 后端：

```python
import json
from bvr_sim import BVR3DEnv

with open("tests/demo_config.json", "r", encoding="utf-8") as f:
    config = json.load(f)

env = BVR3DEnv(config, logdir="./test_logs")
obs, info = env.reset()

done = False
while not done:
    obs, reward, dones, info = env.step({})
    done = info["episode_done"]
```

C++ 后端：

```python
import commentjson
from bvr_sim import BVR3DEnvCpp

with open("tests/demo_config_cpp.jsonc", "r", encoding="utf-8") as f:
    config = commentjson.load(f)

env = BVR3DEnvCpp(config, rl_index=[0], log_file_path="./test_logs/bvr_sim.log")
obs, info = env.reset()

done = False
while not done:
    action = env.action_space.sample().reshape(1, -1)
    obs, reward, dones, info = env.step(action)
    done = info["episode_done"]
```

## 重要目录

```text
bvr_sim/                     主 Python 包和 C++ 源码
bvr_sim_rl/                  轻量 skrl PPO 训练入口
tests/demo_config.json       Python 后端入门配置
tests/demo_config_cpp.jsonc  C++ 后端入门配置
tests/                       smoke tests 和小测试
benchmarks/                  benchmark 配置和脚本
experimental/                更大的示例和可视化脚本
docs/                        额外文档
```

这些是生成目录，不要手动编辑：

```text
bvr_sim/build/
bvr_sim/install/
test_logs/
benchmark_logs/
runs/
```

## 文档

- [PPO 快速开始](docs/rl/ppo_quickstart.md)
- [新手上手指南](docs/getting_started.md)
- [安装说明](docs/installation.md)
- [配置说明](docs/configuration.md)
- [外部框架集成](docs/integration.md)
- [开发者架构说明](docs/developer/architecture.md)

## 可视化

C++ 后端包含几条实时可视化路径：

- Web 可视化：`EmbeddedWebServer` + `bvr_sim/web/`
- 原生 OpenGL viewer
- Windows 原生 DX11 game mode

先编译 C++ 后端，然后可以尝试：

```bash
python experimental/run_web_viz.py
python experimental/run_opengl_viz.py
python experimental/run_dx11_viz.py
```

## 许可证

BVR Sim 使用 GPLv3 发布，见 [LICENSE](LICENSE)。

第三方依赖和内置资源说明见 [docs/legal/THIRD_PARTY_LICENSES.md](docs/legal/THIRD_PARTY_LICENSES.md)。
