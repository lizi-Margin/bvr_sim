# BVR Sim Getting Started

这份文档面向第一次试用 `bvr-sim` 的人，目标是尽快完成三件事：

1. 安装项目
2. 跑通一个 smoke test
3. 知道下一步从哪里改配置、看回放、接 RL 框架

## 1. 你会接触到哪两套环境

### 纯 Python 环境

入口是 [`bvr_sim/bvr_env.py`](G:\bvr_sim\bvr_sim\bvr_env.py) 里的 `BVR3DEnv`。

适合：

- 快速理解环境逻辑
- 调试奖励、观测、规则对手
- 不依赖原生编译先跑起来

### C++ + Python 混合环境

入口是 [`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py) 里的 `BVR3DEnvCpp`。

适合：

- 更高性能训练
- 使用 C++ 核心能力
- 跑原生 unit tests

如果你只是第一次试用，先从 Python 环境开始。

## 2. 安装

仓库根目录执行：

```bash
pip install -e .
```

如果你后面需要 C++ 环境，还需要本地具备：

- `git`
- `cmake`
- C++ 编译器

Windows 使用：

```powershell
bvr_sim\build_windows.bat
```

Linux 使用：

```bash
bash bvr_sim/build_linux.sh
```

## 3. 第一次运行

### 跑 Python 版

```bash
python tests/test_py.py
```

它读取 [`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json)。

运行成功后你通常会得到：

- `test_logs/replay.acmi`

### 跑 C++ 版

先完成构建，再执行：

```bash
python tests/test_cpp.py
```

它读取 [`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc)。

运行成功后你通常会得到：

- `test_logs/replay_0.acmi`
- `test_logs/replay_1.acmi`
- `test_logs/bvr_sim.log`

### 跑一个较新的 C++ 示例

如果你想直接看最近加入的多机混编场景，可以执行：

```bash
python example/run_custom_5v5_acmi.py
```

它读取 [`example/custom_5v5_f22_f16.jsonc`](G:\bvr_sim\example\custom_5v5_f22_f16.jsonc)，会生成一份 5v5 的 ACMI 回放。
这个示例同时覆盖了：

- `F22` / `F16` 混编
- `AIM-120C7` 与 `AIM-9M` 混合挂载
- 单机级别 `opponent_type`

## 4. 配置文件先看什么

### Python 版配置

[`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json) 里最重要的是：

- `red_fighters`
- `blue_fighters`
- `ground_units`
- `obs_type`
- `blue_opponent_type`
- `reward_config`

### C++ 版配置

[`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc) 里最重要的是：

- `red_meta`
- `blue_meta`
- `pylon_mounts`
- `fdm_type`
- `opponent_type`
- `obs_type`
- `reward_config`

如果你想看最近新增的武器与编组配置，再看：

- [`example/custom_5v5_f22_f16.jsonc`](G:\bvr_sim\example\custom_5v5_f22_f16.jsonc)

## 5. 先理解哪些代码文件

建议按这个顺序读：

1. [`tests/test_py.py`](G:\bvr_sim\tests\test_py.py)
2. [`tests/test_cpp.py`](G:\bvr_sim\tests\test_cpp.py)
3. [`bvr_sim/__init__.py`](G:\bvr_sim\bvr_sim\__init__.py)
4. [`bvr_sim/bvr_env.py`](G:\bvr_sim\bvr_sim\bvr_env.py)
5. [`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py)

如果你要改行为逻辑，再继续看：

- `bvr_sim/src_py/simulator/`
- `bvr_sim/src_py/reward/`
- `bvr_sim/src_py/baseline_opponents/`
- [`bvr_sim/src_py/observation_space.py`](G:\bvr_sim\bvr_sim\src_py\observation_space.py)

## 6. RL 框架集成从哪里开始

仓库里已经有适配示例：

- [`example/env_wrapper.py`](G:\bvr_sim\example\env_wrapper.py)
- [`example/env_harl.py`](G:\bvr_sim\example\env_harl.py)
- [`example/env_marlbenchmark.py`](G:\bvr_sim\example\env_marlbenchmark.py)

如果你的试用者是想把环境接进自己训练框架，先看这些文件比直接翻核心源码更有效。

## 7. 常见排查

### Python 版能跑，C++ 版不能跑

优先检查：

- 是否执行过构建脚本
- `bvr_sim/install/lib/` 下是否生成原生库
- `bvr_sim/install/bin/` 下是否有 unit test 可执行文件

### unit test 找不到

执行：

```bash
python tests/cpp_unit_tests.py
```

如果报可执行文件不存在，说明构建还没完成。
完整回归时，[`tests/test_everything.py`](G:\bvr_sim\tests\test_everything.py) 还会额外执行 `test_c3utils`。

### 回放没有生成

检查：

- 运行脚本是否启用了 render
- `test_logs/` 是否存在
- 是否被中断得太早

## 8. 建议的试用路径

如果你要把项目发给别人，可以直接让对方按下面顺序操作：

1. `pip install -e .`
2. `python tests/test_py.py`
3. 打开 `test_logs/replay.acmi`
4. 如果需要 C++ 后端，再执行构建脚本
5. `python tests/test_cpp.py`
6. 看 `example/` 下的外部框架适配

如果要体验最近一轮能力更新，可以在第 5 步后再补一条：

7. `python example/run_custom_5v5_acmi.py`

## 9. 相关文档

更偏研究和设计材料的文档在 `docs/` 下，例如：

- [`docs/doc.md`](G:\bvr_sim\docs\doc.md)
- [`docs/installation.md`](G:\bvr_sim\docs\installation.md)
- [`docs/configuration.md`](G:\bvr_sim\docs\configuration.md)
- [`docs/integration.md`](G:\bvr_sim\docs\integration.md)
- `docs/开发日志.md`
- `docs/毕业设计中期报告.md`

这些适合了解背景，不适合当首次上手说明。
