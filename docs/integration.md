# Integration Guide

这份文档面向两类人：

- 想把 `bvr-sim` 接进自己的 RL 训练框架的人
- 想理解项目现在已经提供了哪些包装层的人

## 先看哪些文件

项目里已经有三类入口：

- 通用/外部框架包装示例：[`rl_envs/env_wrapper.py`](../rl_envs/env_wrapper.py)
- HARL 适配：[`rl_envs/env_harl.py`](../rl_envs/env_harl.py)
- MARLBenchmark 适配：[`rl_envs/env_marlbenchmark.py`](../rl_envs/env_marlbenchmark.py)

如果你是第一次做集成，不要从 `src_py/` 或 `src_cxx/` 开始读，先从这三个包装文件入手。

## 核心环境接口

无论是 Python 版还是 C++ 版，最核心的交互形式都很接近：

```python
obs, info = env.reset()
obs, reward, done, info = env.step(action)
```

主入口：

- Python 环境：[`bvr_sim/bvr_env.py`](bvr_sim/bvr_env.py)
- C++ 环境：[`bvr_sim/bvr_env_cpp.py`](bvr_sim/bvr_env_cpp.py)

## 什么时候用 Python 环境

优先用于：

- 先把训练循环接通
- 调试观测、奖励、done 条件
- 不想先处理原生编译

## 什么时候用 C++ 环境

优先用于：

- 更高性能训练
- 使用原生后端功能
- 需要与 C++ unit tests 一起维护

## HARL 适配

参考 [`rl_envs/env_harl.py`](../rl_envs/env_harl.py)。

这个文件做的事情主要有：

- 维护一份环境默认参数字典
- 根据配置选择 Python 或 C++ 后端
- 把单智能体/多智能体观测整理成 HARL 需要的格式
- 构造 shared observation
- 在适当时机输出 ACMI 与奖励可视化

如果你要接 HARL，先从这个文件复制最小实现，而不是直接改核心环境。

## MARLBenchmark 适配

参考：

- [`rl_envs/env_marlbenchmark.py`](../rl_envs/env_marlbenchmark.py)

这个文件已经处理了几件关键事情：

- `gymnasium` 到 `gym` space 的转换
- 多智能体包装
- shared observation 构造
- 渲染开关和输出目录

如果你的框架接口和 MARLBenchmark 类似，这个文件通常是最好的起点。

## UHRL / 其他自定义框架

参考：

- [`rl_envs/env_wrapper.py`](../rl_envs/env_wrapper.py)

这个文件更接近“项目方自己使用的包装层”，特点是：

- 有较完整的 `ScenarioConfig`
- 会处理 reward breakdown 可视化
- 会维护一些框架侧约定字段
- 会额外塞入 `avail_act`、`State`、`team_ranking` 等信息

如果你的外部框架需要更多辅助字段，这个文件最有参考价值。

## 集成时最常见的适配点

### 1. 观测 shape

环境返回通常是按 agent 打包的 `numpy` 数组。

你要先确认自己的框架需要的是：

- 每个 agent 单独 observation
- 所有 agent 拼接 observation
- 字典形式 observation

### 2. 动作格式

当前环境动作语义围绕四个控制量：

- `delta_heading`
- `delta_altitude`
- `delta_speed`
- `shoot`

但不同包装层可能接受：

- 数组动作
- 字典动作
- 框架自定义的 MultiDiscrete 编码

### 3. done / episode_done

很多外部框架只看 `done`，但这个项目通常还会在 `info` 里给出：

- `episode_done`
- `team_ranking`
- `current_step`

接框架时要先决定谁是最终 episode 终止信号。

### 4. shared observation

集中训练框架通常需要 shared observation。

现有适配里常用策略是：

- 先拿每个 agent 的 obs
- 再沿特征维拼接
- 最后复制成每个 agent 都可见的一份 shared obs

## 推荐的集成流程

1. 先用 Python 后端接通框架训练循环
2. 先只保留最小配置和默认规则对手
3. 确认 observation、action、done 形状完全对齐
4. 再替换成 C++ 后端
5. 最后再引入更复杂配置，如更多机型、地面单位、entity observation

## 集成完成后建议验证

最少做这些检查：

1. `reset()` 是否稳定返回
2. 连续 `step()` 100 步是否不崩
3. episode 结束时 `done` / `episode_done` 是否一致
4. action shape 错误时是否能快速暴露
5. 是否正常产生回放文件和日志

仓库里现成可以参考的脚本：

- [`tests/test_py.py`](tests/test_py.py)
- [`tests/test_cpp.py`](tests/test_cpp.py)
- [`tests/test_mmodelA_smoke.py`](tests/test_mmodelA_smoke.py)

## 对外开源时的建议

如果你准备让社区用户集成：

- README 里只保留一个最小集成示例
- 复杂框架适配全部放进 `docs/integration.md`
- 每个 `rl_envs/` 文件顶部都写清楚“这个文件是给哪个框架用的”
