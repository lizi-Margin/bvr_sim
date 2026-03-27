# BVR Sim

`bvr-sim` 是一个面向多智能体强化学习的 3D 超视距空战仿真环境，提供两套后端：

- 纯 Python 环境，便于调试和快速验证
- C++ + Python 混合环境，便于更高性能训练和扩展

项目当前已经包含：

- 3D 飞机动力学与高度控制
- 空空导弹与地面防空单位仿真
- 多种 observation space
- 可配置 reward shaping
- 基于 ACMI 的 Tacview 回放输出
- 规则对手与外部 RL 框架适配入口

## 仓库结构

```text
bvr_sim/               Python 包与 C++ 核心源码
  src_py/              Python 仿真、奖励、规则对手
  src_cxx/             C++ 仿真核心
  build_windows.bat    Windows 构建脚本
  build_linux.sh       Linux 构建脚本
tests/                 smoke tests、unit tests、示例配置
example/               外部框架适配示例
docs/                  研究材料与补充文档
```

## 环境要求

- Python 3.8+
- Windows 或 Linux
- `git`
- C++ 后端构建需要 `cmake` 和本地 C++ 编译器
  - Windows: 建议使用 Visual Studio / MSVC
  - Linux: 建议使用 `gcc` 或 `clang`

Python 依赖定义在 [`pyproject.toml`](G:\bvr_sim\pyproject.toml) 中，核心依赖包括：

- `numpy`
- `scipy`
- `gymnasium`
- `opencv-python`
- `commentjson`
- `JSBSim==1.1.14`

## 快速开始

### 1. 安装 Python 包

在仓库根目录执行：

```bash
pip install -e .
```

这会安装 Python 版本环境所需依赖，并以 editable mode 暴露 `bvr_sim` 包。

### 2. 运行纯 Python smoke test

```bash
python tests/test_py.py
```

这个脚本会：

- 加载 [`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json)
- 创建 [`BVR3DEnv`](G:\bvr_sim\bvr_sim\bvr_env.py)
- 在 `test_logs/` 下输出 ACMI 回放

如果你只是第一次体验项目，建议先跑这一步。

### 3. 构建 C++ 后端

Windows:

```powershell
bvr_sim\build_windows.bat
```

Linux:

```bash
bash bvr_sim/build_linux.sh
```

构建脚本会自动拉取 C++ 依赖到 `bvr_sim/src_cxx/extern/`，然后生成并安装原生库到 `bvr_sim/install/`。

### 4. 运行 C++ smoke test

```bash
python tests/test_cpp.py
```

这个脚本会：

- 加载 [`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc)
- 创建 [`BVR3DEnvCpp`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py)
- 在 `test_logs/` 下输出日志与 ACMI 回放

### 5. 运行完整测试

```bash
python tests/test_everything.py
```

该脚本会依次执行：

1. 重建 C++ 后端
2. 安装当前包
3. 运行 C++ unit tests
4. 运行 C++ smoke test
5. 运行 Python smoke test

## 最小使用示例

### 纯 Python 环境

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

### C++ 环境

```python
import commentjson
from bvr_sim import BVR3DEnvCpp

with open("tests/demo_config_cpp.jsonc", "r", encoding="utf-8") as f:
    config = commentjson.load(f)

env = BVR3DEnvCpp(config, rl_index=[], log_file_path="./test_logs/bvr_sim.log")
obs, info = env.reset()

done = False
while not done:
    obs, reward, dones, info = env.step({})
    done = info["episode_done"]
```

说明：

- Python 环境里，传入 `{}` 时红方会退回默认 baseline 行为
- C++ 环境里，`rl_index=[]` 表示没有 RL 控制单元，环境可作为纯规则推演运行

## 配置说明

示例配置见：

- [`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json)
- [`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc)

常见字段：

- `dt`: 仿真步长
- `max_steps`: 单局最大步数
- `red_fighters` / `blue_fighters`: Python 环境的红蓝方飞机定义
- `red_meta` / `blue_meta`: C++ 环境的红蓝方单元定义
- `ground_units`: 地面单位配置
- `obs_type`: 观测空间类型，当前代码支持 `compact`、`extended`、`shadow`、`canvas`、`lidar`、`entity`、`text`
- `blue_opponent_type`: 蓝方规则对手类型；设为 `null` 时可改成双边可控
- `reward_config`: 奖励项权重
- `initial_separation_nm`: 初始交战距离
- `formation_max_spread_nm`: 编队横向散布

## 输出结果

默认运行后你会看到：

- `test_logs/*.acmi`: 可用 Tacview 打开回放
- `test_logs/bvr_sim.log`: C++ 后端运行日志
- `bvr_sim/install/`: 原生构建产物

不要手工编辑以下生成目录：

- `bvr_sim/build/`
- `bvr_sim/install/`
- `benchmark_logs/`
- `test_logs/`

## 与外部框架集成

仓库中已经有一些适配入口或示例：

- [`example/env_wrapper.py`](G:\bvr_sim\example\env_wrapper.py)
- [`example/env_harl.py`](G:\bvr_sim\example\env_harl.py)
- [`example/env_marlbenchmark.py`](G:\bvr_sim\example\env_marlbenchmark.py)

其中 [`example/env_wrapper.py`](G:\bvr_sim\example\env_wrapper.py) 展示了如何把环境包装成外部 MARL 框架可用的接口。

## 文档导航

如果你是第一次试用，建议按这个顺序看：

1. 本页 README
2. [`docs/getting_started.md`](G:\bvr_sim\docs\getting_started.md)
3. [`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json) 或 [`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc)
4. [`example/env_wrapper.py`](G:\bvr_sim\example\env_wrapper.py)

已有研究/设计材料：

- [`docs/doc.md`](G:\bvr_sim\docs\doc.md)
- `docs/*.md`
- `docs/*.tex`

这些材料更偏研究记录，不是首次上手文档。

## 常见问题

### `bvr_sim_cpp` 无法导入

先确认你已经执行过 C++ 构建脚本，并且 `bvr_sim/install/lib/` 下已经生成对应动态库。

### 运行 C++ 测试时报找不到 unit test 可执行文件

先构建原生后端，再执行：

```bash
python tests/cpp_unit_tests.py
```

该脚本依赖 `bvr_sim/install/bin/bvr_sim_unit_tests(.exe)`。

### Tacview 没有回放文件

确认测试或脚本是否显式启用了 render，输出通常在 `test_logs/` 下。

## 许可证

见 [`LICENSE`](G:\bvr_sim\LICENSE) 和 [`LICENSE.GPL`](G:\bvr_sim\LICENSE.GPL)。
