# Architecture Overview

这份文档面向准备修改代码的贡献者。

## 顶层结构

项目主体在 [`bvr_sim/`](G:\bvr_sim\bvr_sim) 下，分成两层：

- Python 主逻辑
- C++ 原生核心

大体结构如下：

```text
bvr_sim/
  bvr_env.py           Python 环境主入口
  bvr_env_cpp.py       C++ 环境包装入口
  action_space.py      动作空间定义与转换
  spawn_manager.py     出生阵位与初始编队逻辑
  src_py/
    simulator/         Python 仿真要素
    reward/            奖励系统
    baseline_opponents/规则对手
  src_cxx/             C++ 核心源码
```

## Python 环境主线

入口：[`bvr_sim/bvr_env.py`](G:\bvr_sim\bvr_sim\bvr_env.py)

主线流程大致是：

1. 读配置
2. 创建 spawn manager
3. 创建红蓝方飞机与地面单位
4. 创建 observation space 和 reward manager
5. `reset()` 时初始化实体与状态
6. `step()` 时应用动作、更新飞行器和导弹、计算奖励、打包输出

这个文件是理解整个项目行为的第一入口。

## C++ 环境主线

入口：[`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py)

它本质上是一个 Python adapter，负责：

- 加载原生扩展
- 创建 `SimCore`
- 把 Python 侧配置翻译成原生命令
- 读取原生 observation / reward / done
- 维持与 Python 环境相近的接口

如果你要改原生行为，通常要同时看：

- [`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py)
- `bvr_sim/src_cxx/`

## 奖励系统

奖励相关代码在：

- [`bvr_sim/src_py/reward/reward_components.py`](G:\bvr_sim\bvr_sim\src_py\reward\reward_components.py)
- [`bvr_sim/src_py/reward/reward_visualization.py`](G:\bvr_sim\bvr_sim\src_py\reward\reward_visualization.py)

设计上：

- 配置从 `reward_config` 进入
- 环境 step 后统一计算奖励
- 可以输出 reward breakdown 供可视化或调试

## 规则对手

规则对手代码在：

- [`bvr_sim/src_py/baseline_opponents/simple_opponents.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\simple_opponents.py)
- [`bvr_sim/src_py/baseline_opponents/tactical_opponent.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\tactical_opponent.py)
- [`bvr_sim/src_py/baseline_opponents/slamraam_policy.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\slamraam_policy.py)

如果你要增加一种新 opponent，优先遵循这里已有的模式，不要把策略逻辑散落回 `bvr_env.py`。

## 观测空间

观测空间工厂在：

- [`bvr_sim/src_py/observation_space.py`](G:\bvr_sim\bvr_sim\src_py\observation_space.py)

当前支持多种 `obs_type`。如果你要新增一种观测形式，最好：

1. 在这个文件里单独实现
2. 在工厂函数里注册
3. 给 demo config 或测试补一个可运行示例

## 动作空间

动作相关定义在：

- [`bvr_sim/action_space.py`](G:\bvr_sim\bvr_sim\action_space.py)

这是 Python 环境、C++ 环境和外部包装层之间的重要边界。改动作编码时，要同步检查：

- `bvr_env.py`
- `bvr_env_cpp.py`
- `example/` 下包装文件

## 出生阵位与初始化

位置随机化和编队参数主要经过：

- [`bvr_sim/spawn_manager.py`](G:\bvr_sim\bvr_sim\spawn_manager.py)

配置里常见的：

- `initial_separation_nm`
- `formation_max_spread_nm`

都和这里直接相关。

## 外部框架包装层

示例包装在：

- [`example/env_wrapper.py`](G:\bvr_sim\example\env_wrapper.py)
- [`example/env_harl.py`](G:\bvr_sim\example\env_harl.py)
- [`example/env_marlbenchmark.py`](G:\bvr_sim\example\env_marlbenchmark.py)

如果你要维护兼容层，尽量把框架特定逻辑放在这些包装层里，不要污染核心环境。

## 建议的修改策略

### 改奖励

优先改 `src_py/reward/`，然后跑：

```bash
python tests/test_py.py
```

### 改 C++ 核心

改完后优先跑：

```bash
python tests/cpp_unit_tests.py
python tests/test_cpp.py
```

### 改环境行为

至少跑：

```bash
python tests/test_py.py
python tests/test_cpp.py
```

如果改动范围大，再跑：

```bash
python tests/test_everything.py
```
