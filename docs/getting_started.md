# 新手上手指南

这份文档只面向一个目标：让第一次接触项目的人，先跑通一个强化学习空战训练任务。

你不需要先理解空战模型、C++ 绑定、奖励函数或观测空间。先跑通，再看配置。

## 最终目标

先跑这条最小训练命令：

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 128 --rollouts 16 --device cpu
```

它会用纯 Python 后端启动一个很短的 PPO 训练任务。跑通后，再切到 C++ 后端做更快训练。

## 1. 安装

在仓库根目录创建虚拟环境：

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

安装项目和 RL 依赖：

```bash
pip install -e ".[rl]"
```

如果引号导致 shell 报错，就分两步：

```bash
pip install -e .
pip install skrl torch
```

## 2. 跑一个最小 PPO 训练

先用 Python 后端，因为它不需要编译 C++。

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 128 --rollouts 16 --device cpu
```

这不是为了训练出强策略，而是为了确认：

- Python 包能导入
- 仿真环境能 reset/step
- `skrl` PPO 能拿到观测和动作
- 日志和 checkpoint 能写出

输出目录：

```text
runs/bvr_sim_rl/
```

想跑久一点：

```bash
python -m bvr_sim_rl --backend python --config tests/demo_config.json --timesteps 10000
```

## 3. 使用 C++ 后端训练

C++ 后端更适合正式训练。先编译：

Windows:

```powershell
bvr_sim\build_windows.bat
```

Linux:

```bash
bash bvr_sim/build_linux.sh
```

快速确认 C++ 后端能训练：

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 128 --rollouts 16 --device cpu
```

正式一点的训练：

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

## 4. 这个训练入口在哪里

核心文件只有两个：

```text
bvr_sim_rl/env.py
bvr_sim_rl/ppo.py
```

`env.py` 负责把 BVR Sim 包装成 `skrl` 可以训练的环境。

`ppo.py` 负责创建 PPO 模型、memory、agent 和 trainer。

## 5. 动作是怎么接上的

仿真器原始动作空间是：

```text
MultiDiscrete([15, 15, 9, 2])
```

四个维度分别是：

```text
delta_heading, delta_altitude, delta_speed, shoot
```

`bvr_sim_rl` 直接保留仿真器的离散动作空间：

```text
MultiDiscrete([15, 15, 9, 2])
```

PPO 使用四个 categorical 分支分别建模航向、高度、速度和发射动作，
训练时优化的动作与仿真器实际执行的动作一致，不再经过连续值量化。

## 6. 单独验证仿真器

如果训练失败，先确认仿真器本身能跑。

Python 后端：

```bash
python tests/test_py.py
```

C++ 后端：

```bash
python tests/test_cpp.py
```

完整测试：

```bash
python run_tests.py
```

## 7. 查看空战回放

部分测试和示例会生成：

```text
test_logs/*.acmi
```

用 Tacview 打开 `.acmi` 文件，可以查看空战轨迹。

训练命令默认不一定生成回放。如果你想确认回放功能，先跑：

```bash
python tests/test_py.py
python tests/test_cpp.py
```

## 8. 接下来读什么

建议顺序：

1. [PPO 快速开始](rl/ppo_quickstart.md)
2. [Python 后端入门配置](../tests/demo_config.json)
3. [C++ 后端入门配置](../tests/demo_config_cpp.jsonc)
4. [RL 环境适配代码](../bvr_sim_rl/env.py)
5. [PPO 训练代码](../bvr_sim_rl/ppo.py)

想继续改仿真和任务，再看：

- [配置说明](configuration.md)
- [外部框架集成](integration.md)
- [开发者架构说明](developer/architecture.md)

## 常见问题

### 找不到 `skrl` 或 `torch`

执行：

```bash
pip install skrl torch
```

### `bvr_sim_cpp` 不能导入

说明 C++ 后端还没有编译，先执行：

```powershell
bvr_sim\build_windows.bat
```

或：

```bash
bash bvr_sim/build_linux.sh
```

### Python 后端能跑，C++ 后端不能跑

先跑：

```bash
python tests/test_cpp.py
```

如果这里失败，问题在 C++ 构建或原生扩展导入，不在 PPO。

### 训练很慢

先确认你用的是 C++ 后端：

```bash
python -m bvr_sim_rl --backend cpp --config tests/demo_config_cpp.jsonc --timesteps 10000
```

### 没有看到回放文件

训练默认关注 checkpoint 和日志，不一定打开 ACMI。需要回放时先跑 smoke test 或专门的示例脚本。
