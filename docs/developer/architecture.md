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
python run_tests.py
```

## 实时可视化与调试架构

当前实时可视化链路有三个 viewer 后端，共享同一条 telemetry 契约：

1. `SimCore`
2. `TelemetryBridge`
3. `EmbeddedWebServer`、`OpenGLViewer` 或 `BVR Sim Game Mode`
4. `web/` 前端、进程内原生 OpenGL 窗口或进程内原生 DX11 窗口

当前确定继续使用单一 `bvr_sim_cpp` 原生扩展架构。`BVR Sim Game Mode` 是进程内游戏模式，不规划独立 `game_app.exe`。

关键入口：

- [`core.cxx`](G:\bvr_sim\bvr_sim\src_cxx\core.cxx)
- [`telemetry_bridge.cxx`](G:\bvr_sim\bvr_sim\src_cxx\telemetry\telemetry_bridge.cxx)
- [`embedded_web_server.cxx`](G:\bvr_sim\bvr_sim\src_cxx\telemetry\embedded_web_server.cxx)
- [`opengl_viewer.cxx`](G:\bvr_sim\bvr_sim\src_cxx\telemetry\opengl_viewer.cxx)
- [`dx11_game_mode.cxx`](G:\bvr_sim\bvr_sim\src_cxx\telemetry\dx11_game_mode.cxx)
- [`dx11_game_mode_render.cxx`](G:\bvr_sim\bvr_sim\src_cxx\telemetry\dx11_game_mode_render.cxx)
- [`main.ts`](G:\bvr_sim\web\src\main.ts)

### 职责边界

`SimCore`

- 负责仿真生命周期和步进
- 处理 `pause` / `resume` / `step`
- 不向浏览器直接暴露对象实例

`TelemetryBridge`

- 运行在独立守护线程
- 从 `SOPool` 读取当前对象
- 通过 [`register.hxx`](G:\bvr_sim\bvr_sim\src_cxx\simulator\register.hxx) 构建严格 `WorldSnapshot`
- 保存最新快照
- 处理 `focus_uid` 和 `subscription_filter`

`EmbeddedWebServer`

- 暴露 `GET /health`
- 暴露 `GET /diagnostics`
- 暴露 WebSocket `/ws`
- 转发浏览器命令到桥接层
- 可选直接托管 `web/dist` 下的静态前端入口

`OpenGLViewer`

- 运行在进程内独立线程
- 直接读取 `TelemetryBridge` 的最新 `WorldSnapshot`
- 将原生窗口输入转换成 telemetry 命令
- 不直接访问仿真对象实例

`BVR Sim Game Mode`（当前 DX11 后端）

- 运行在进程内独立线程
- 使用 Win32 + Direct3D 11 渲染当前实时快照
- 直接读取 `TelemetryBridge` 的最新 `WorldSnapshot`
- 将原生窗口输入转换成 viewer 状态或 telemetry 命令
- 不直接访问仿真对象实例
- 不要求或创建独立客户端进程

`web/`

- 只读 `WorldSnapshot`
- 只写结构化命令
- 不依赖 C++ 内部对象模型

进程内 OpenGL viewer 和 BVR Sim Game Mode 也遵守同一原则：

- 只读 `WorldSnapshot`
- 只写结构化命令
- 不依赖 C++ 内部对象模型

### 为什么必须经过 Register

渲染与仿真解耦的核心做法是：

1. 仿真对象把调试所需状态写入 `Register`
2. `TelemetrySnapshotBuilder` 从 `Register` 严格取值
3. `TelemetryBridge` 发布标准化快照
4. Web 前端或原生 viewer 只消费该快照

这样做可以避免：

- 表现层与仿真内部类结构强耦合
- 调试代码侵入 `SimCore`
- 后续渲染器切换时重复绑定内部对象

### 快照契约

当前桥接层要求至少有这些字段：

- `uid`
- `Type`
- `color`
- `is_alive`
- `position`
- `velocity`

字段缺失或类型错误时，桥接层会直接失败，而不是跳过对象或偷偷填默认值。

### 命令模型

当前命令集合包括：

- `pause`
- `resume`
- `step`
- `set_focus_uid`
- `set_subscription_filter`
- `object_debug`

这条模型意味着前端交互同样解耦。未来如果要支持对象级调试命令，应继续扩展命令队列，而不是让前端直接写对象。

当前 `object_debug` 的 phase-1 语义是：

- 浏览器发出 `target_uid`
- 负载里携带 `register_key` 和 `value`
- `SimCore` 找到目标对象后，把值写入该对象 `Register`

也就是说，对象级调试仍然是“写寄存器”，而不是浏览器直接拿到对象引用。

桥接层当前还会在诊断状态里暴露：

- `last_command_result`

这个字段用于给前端和自动化测试提供最近一次命令执行结果，区分 queued 之后到底是 applied 还是 error。

### 当前验证

```bash
python tests/cpp_unit_tests.py
python tests/test_web_bridge_smoke.py
npm --prefix web run build
```

`test_web_bridge_smoke.py` 当前会验证：

- 打包后的前端入口可由内嵌服务器直接托管
- 可视化服务可启动
- HTTP `health` / `diagnostics` 正常
- WebSocket 首帧快照正常
- WebSocket 命令回执正常
- `focus_uid` / `subscription_filter` 会反映到桥接诊断状态


