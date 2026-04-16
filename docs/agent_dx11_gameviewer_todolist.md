# DX11GameViewer Current Architecture

## 当前决策

`DX11GameViewer` 继续沿用当前 `bvr_sim_cpp` 单一原生扩展架构，不再规划独立 `game_app.exe`。

当前方向：

- 不改变 `SimCore` 仿真语义
- 不破坏现有 `bvr_env_cpp` / `jsonc` / `core.handle()` 生态
- 不替换 `OpenGLViewer`
- 不新增独立 `game_app.exe`
- 继续沿用 `TelemetryBridge -> WorldSnapshot -> Command` 解耦架构
- 在同一个 `pyd` 内运行 DX11 viewer 线程
- 把 DX11 viewer 作为当前原生游戏画面方向继续迭代

---

## 当前实现

当前 `DX11GameViewer` 已经接入 `SimCore` 生命周期和 Python 绑定。

已具备：

- Windows Win32 窗口
- DX11 device / immediate context / swap chain
- render target / depth buffer
- 基础 shader、常量缓冲、顶点提交
- 天空、地面、网格
- 飞机 / 导弹 / 地面单位渲染
- OBJ mesh 资源加载和 primitive fallback
- 鼠标 / 键盘相机控制
- HUD 文本
- 从 `WorldSnapshot` 读取 sim time 和对象列表
- 通过 Python 查询状态

关键文件：

- `bvr_sim/src_cxx/telemetry/dx11_game_viewer.hxx`
- `bvr_sim/src_cxx/telemetry/dx11_game_viewer.cxx`
- `bvr_sim/src_cxx/telemetry/dx11_game_viewer_internal.hxx`
- `bvr_sim/src_cxx/telemetry/dx11_game_viewer_render.cxx`
- `example/run_dx11_viz.py`

---

## 架构边界

`DX11GameViewer` 必须保持以下边界：

- 只通过 snapshot provider 读取 `WorldSnapshot`
- 只通过 command submitter 写 `TelemetryCommand`
- 不直接访问 `SOPool`
- 不直接访问仿真对象内部字段
- 不改变 `SimCore` step/reset/reward/done 语义
- 不改变 Python 环境行为
- 不引入独立客户端进程

如果需要新增交互能力，应扩展 telemetry command，而不是让 viewer 直接改对象。

---

## Python 接口

当前接口与 `OpenGLViewer` 对齐：

- `start_dx11_game_viewer()`
- `stop_dx11_game_viewer()`
- `is_dx11_game_viewer_running()`
- `is_dx11_game_viewer_supported()`
- `get_dx11_game_viewer_status()`

状态至少包含：

- `running`
- `supported`
- `platform`
- `backend`
- `last_error`
- `last_sim_time`
- `last_object_count`
- `last_command_count`
- `last_draw_calls`
- `last_vertex_count`

当前渲染后端已经避免每个 draw 创建 transient immutable vertex buffer，改为复用 DX11 dynamic vertex buffer，并保留最小 state cache 来减少重复绑定。

---

## 运行方式

先构建原生扩展：

```powershell
bvr_sim\build_windows.bat
```

运行示例：

```bash
python example/run_dx11_viz.py
```

最小 Python 调用：

```python
from bvr_sim import bvr_sim_cpp

core = bvr_sim_cpp.SimCore(
    dt=0.2,
    log_file_path="./test_logs/dx11.log",
    acmi_file_path=""
)

core.start_telemetry_bridge()
core.start_dx11_game_viewer()
core.start()
```

---

## 后续任务边界

允许继续做：

- DX11 renderer 内部结构整理
- 相机模式
- HUD 增强
- mesh / material 资源改进
- 轨迹线、尾焰、爆炸等表现效果
- 对象选择和 focus 交互
- viewer 性能优化
- 更明确的错误日志和诊断状态
- 按 `Window / SnapshotRenderer / RenderCommandList / DX11Renderer / AssetCache` 继续拆分大文件

不要做：

- 新增独立 `game_app.exe`
- 把正式画面逻辑移出 `bvr_sim_cpp`
- 重构 `SimCore` 或仿真规则
- 让 viewer 绕过 `TelemetryBridge`
- 删除或替换 `OpenGLViewer`
- 继续按旧的独立客户端计划执行
- 做 snapshot 插值层或长期 presentation object 状态，除非后续 sim/render 频率关系发生变化

---

## 验收命令

DX11 viewer 相关改动至少说明并尽量验证：

```bash
python tests/cpp_unit_tests.py
python tests/test_cpp.py
python example/run_dx11_viz.py
```

如果只改文档，不需要重建或运行 DX11 示例。

---

## 输出要求

修改 DX11 viewer 时必须汇报：

- 修改了哪些文件
- 哪些接口新增
- 哪些限制仍然存在
- 如何编译
- 如何验证
- 还未完成的下一阶段工作

---

## 禁止事项

agent 不允许：

- 顺手把 OpenGL viewer 改成 DX11
- 顺手重构 telemetry 系统
- 顺手重构 Python 启动逻辑
- 顺手新增独立游戏客户端
- 顺手把渲染逻辑塞回仿真层
- 顺手设计抽象过度的通用 RHI

当前目标只有一个：

**在现有 `pyd` 架构里继续迭代 `DX11GameViewer`，并保持仿真、telemetry、渲染解耦。**
