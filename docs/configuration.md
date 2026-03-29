# Configuration Guide

这份文档解释 `bvr-sim` 最重要的配置项，以及应该从哪些示例配置开始改。

## 从哪个配置文件开始

项目里现成的示例配置有两份：

- Python 环境：[`tests/demo_config.json`](G:\bvr_sim\tests\demo_config.json)
- C++ 环境：[`tests/demo_config_cpp.jsonc`](G:\bvr_sim\tests\demo_config_cpp.jsonc)

建议：

- 要快速试用，就改 `demo_config.json`
- 要验证原生后端或更复杂单位定义，就改 `demo_config_cpp.jsonc`

## Python 环境配置

Python 环境入口是 [`bvr_sim/bvr_env.py`](G:\bvr_sim\bvr_sim\bvr_env.py) 中的 `BVR3DEnv`。

一个最小 Python 配置通常包含：

```json
{
  "dt": 0.4,
  "max_steps": 1000,
  "red_fighters": {
    "A01": { "model": "F16", "record": false }
  },
  "blue_fighters": {
    "B01": { "model": "F16", "record": false }
  },
  "ground_units": {},
  "field_size": 100000.0,
  "obs_type": "text",
  "blue_opponent_type": "tactical",
  "reward_config": {}
}
```

### 关键字段

`dt`

- 仿真步长
- 在 Python 环境中会经过裁剪，代码里限制在 `0.05` 到 `0.5`

`max_steps`

- 单局最大步数

`red_fighters` / `blue_fighters`

- 红蓝方飞机定义
- key 是单位 ID，例如 `A01`、`B01`
- 最小字段通常包括：
  - `model`
  - `record`

`ground_units`

- 地面单位配置
- 当前代码里支持至少两类：
  - `static`
  - `slamraam`

`field_size`

- 战场尺寸参数

`obs_type`

- 观测空间类型
- 当前代码支持：
  - `compact`
  - `extended`
  - `shadow`
  - `canvas`
  - `lidar`
  - `entity`
  - `text`

观测空间工厂见 [`bvr_sim/src_py/observation_space.py`](G:\bvr_sim\bvr_sim\src_py\observation_space.py)。

`blue_opponent_type`

- 蓝方规则对手类型
- 常见值是 `tactical`
- 设为 `null` 时，环境会把蓝方也视作可控单元

`reward_config`

- 奖励配置字典
- 由 [`bvr_sim/src_py/reward/reward_components.py`](G:\bvr_sim\bvr_sim\src_py\reward\reward_components.py) 读取

## C++ 环境配置

C++ 环境入口是 [`bvr_sim/bvr_env_cpp.py`](G:\bvr_sim\bvr_sim\bvr_env_cpp.py) 中的 `BVR3DEnvCpp`。

`tests/demo_config_cpp.jsonc` 支持注释，适合维护更复杂的样例。

### 最常用字段

`red_meta` / `blue_meta`

- 红蓝方单元定义
- 常见字段：
  - `unit_spec`
  - `color`
  - `position`
  - `velocity`
  - `fdm_type`
  - `record`
  - `pylon_mounts`
  - `opponent_type`

`unit_spec`

- 单元型号，如 `F15`、`F16`

`fdm_type`

- 飞行动力学模型类型
- 示例里常见值包括 `jsbsim`

`position` / `velocity`

- 初始位置和速度
- 设为 `null` 时，部分场景会由 spawn manager 随机生成

`pylon_mounts`

- 挂点与武器配置

`opponent_type`

- 为单个单位指定规则对手类型

`blue_opponent_type`

- 在更高层控制蓝方是否由规则策略驱动
- 设为 `null` 时，通常意味着更接近双边可控模式

## 奖励配置

当前示例里的奖励项包括三类：

- 几何/态势类
  - `engage_enemy_weight`
  - `enemy_distance_weight`
  - `altitude_advantage_weight`
  - `safe_altitude_weight`
  - `speed_weight`
  - `survival_weight`
- 导弹过程类
  - `missile_evasion_weight`
  - `missile_launch_weight`
  - `missile_launch_reward`
  - `missile_duplicated_launch_penalty`
  - `missile_result_weight`
  - `missile_hit_reward`
  - `missile_miss_penalty`
- 终局类
  - `win_loss_weight`
  - `win_reward`
  - `loss_penalty`

此外还包括 distillation 相关参数：

- `distill_reward_weight`
- `distill_reward_norm`
- `distill_reward_include_shoot`
- `distill_reward_shoot_weight`

## 规则对手

Python 侧规则对手实现在：

- [`bvr_sim/src_py/baseline_opponents/__init__.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\__init__.py)
- [`bvr_sim/src_py/baseline_opponents/simple_opponents.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\simple_opponents.py)
- [`bvr_sim/src_py/baseline_opponents/tactical_opponent.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\tactical_opponent.py)
- [`bvr_sim/src_py/baseline_opponents/slamraam_policy.py`](G:\bvr_sim\bvr_sim\src_py\baseline_opponents\slamraam_policy.py)

如果你要给试用者一个稳定入口，优先使用仓库现有 demo config 里的默认策略组合，不要一开始就暴露太多实验性选项。

## 观测与动作

### 观测

Python 环境的 observation space 由 `obs_type` 决定。

C++ 环境中，`BVR3DEnvCpp` 也会把 `obs_type` 传给内部 RL manager。

### 动作

两套环境都围绕 [`bvr_sim/action_space.py`](G:\bvr_sim\bvr_sim\action_space.py) 中的动作空间工作。

概念上动作包含四个方向：

- `delta_heading`
- `delta_altitude`
- `delta_speed`
- `shoot`

## 建议的改配置顺序

如果你要让别人逐步理解项目，建议按这个顺序改：

1. 先改 `max_steps`
2. 再改 `red_fighters` / `blue_fighters` 或 `red_meta` / `blue_meta`
3. 再改 `obs_type`
4. 再改 `reward_config`
5. 最后再引入 `ground_units` 或更复杂的武器/机型组合

## 配置变更时如何验证

改完配置后，优先执行：

```bash
python tests/test_py.py
```

或：

```bash
python tests/test_cpp.py
```

如果你改的是原生后端逻辑，再补：

```bash
python tests/cpp_unit_tests.py
```
