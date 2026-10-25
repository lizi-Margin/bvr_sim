---
name: bvr-add-sim-object
description: "Add or refactor physical simulation objects in bvr_sim, including bombs, missiles, vehicles and sensors. Use for object physics, lifecycle, collision/damage and core integration, including objects first introduced by game features."
---

# BVR 仿真对象开发

将可独立运行的物理对象接入仿真核心，再接入任务和显示。适用于新增对象及把游戏层物理迁回核心；仅调整贴图、相机或 HUD 时无需启动这套流程。

## 定位与边界

以包含 `pyproject.toml` 和 `bvr_sim/src_cxx/` 的目录为仓库根目录，先读根目录 `AGENTS.md`。以下路径均相对此根目录。

| 当前入口 | 用途 |
|---|---|
| `bvr_sim/src_cxx/simulator/simulator.hxx`、`simulator.cxx` | `SimulatedObject`、`SOT`、通用对象 tick 与状态 |
| `bvr_sim/src_cxx/so_pool.hxx`、`so_pool.cxx` | `SOPool` 登记、查询、存活与回收 |
| `bvr_sim/src_cxx/core.cxx` | `SimCore` 调度；检查新对象当步进入对象池后的 tick 规则，避免重复推进 |
| `bvr_sim/src_cxx/simulator/missile/` | 现有导弹对象、气动和 FDM 参考 |
| `bvr_sim/src_cxx/simulator/weapon_factory.hxx`、`weapon_factory.cxx` | 当前武器工厂，仅提供返回 `Missile` 的 `create_missile` |
| `bvr_sim/src_cxx/simulator/unit_factory.hxx`、`unit_factory.cxx` | 当前载具/地面单位工厂 |
| `bvr_sim/src_cxx/simulator/pylon_manager.hxx`、`pylon_manager.cxx` | 挂载与剩余弹药 |
| `bvr_sim/src_cxx/gameplay/game_session.hxx`、`game_session.cxx` | 游戏指令、任务配置、typed frame/event 适配；不是新物理的落点 |
| `bvr_sim/src_cxx/CMakeLists.txt`、`pybind11_bindings.cxx` | 原生编译目标、测试源码列表和 Python 暴露 |

对象实现放在 `simulator/` 对应类别下。航弹建议新增 `simulator/bomb/`，这是目标目录，不代表已经存在。对象不需要为了复用工厂而继承语义不符的 `Missile`；按需增加 typed `create_bomb` 或其他合适的创建入口，保持现有导弹接口兼容。

## 实施时检查

1. **确定物理契约。** 明确坐标、单位、dt、初始条件、可配置参数、终止条件和已知近似。沿用核心 north/west/up 米制坐标，渲染坐标转换留在显示层。区分已接入的参数/模型与仅存在于资源目录的文件；不能声称未调用的 JSBSim XML 正在驱动对象。
2. **实现核心对象和公共服务。** 通常复用 `SimulatedObject`，通过 `SOPool` 交给核心调度。气动、弹道、导引、碰撞、引信及毁伤放在对象或核心服务中；质量、阻力、尺寸、引信和毁伤参数放在可解释的模型参数/配置中，不散落到任务或渲染代码。复用现有参数机制即可，不要求为单个对象搭建通用引擎。
3. **保持依赖向内。** 若需要地形/环境，使用核心数据或只读接口。当前 `GameTerrain` 在 gameplay 头文件里；迁移航弹时应下移共享类型或提供核心接口，不能从 `simulator/bomb/` 反向 include `gameplay/game_session.hxx`。CCIP 调用同一份核心弹道预测，不另抄一套常量，也不通过预测操作消耗弹药或改变 live world。
4. **接入创建和生命周期。** 根据实际需要更新工厂、模型名映射、`SOT`/字符串映射、参数加载、挂载释放及编译源文件。核对生成 UID/seed、出生时刻、dt、回收、reset、所属阵营与所有者。保持失败时弹药与创建结果一致，命中/引爆/毁伤只结算一次。
5. **接入调用方。** `GameSession` 将释放/发射指令交给核心，读取真实对象状态和结果，再生成任务事件或评分。typed snapshot/绑定只按需要扩展；已有遥测消费者需要兼容时才更新遥测，不能让遥测成为物理依赖。渲染/音效从快照与真实事件生成展示，不参与积分或战果修改。

## Mk-82 的现有核心实现

当前 `Mk82Bomb`、`ballistic_step()`、地形撞击、固定半径毁伤与 CCIP 预测位于 `simulator/bomb/mk82.hxx/.cxx`，共享 `Terrain` 位于 `simulator/environment.hxx`。`WeaponFactory::create_bomb` 和核心 `release_bomb` 执行创建及精确挂点扣弹，`GameSession` 只请求释放并读取结果。Agent 可通过 `SimCore.release_weapon`、`predict_bomb_impact`、`set_environment` 和 `spawn_ground` 直接验证，不构造游戏会话。

这次接入保留原有 Alpha 弹道与毁伤近似。后续重构仍须保存原轨迹、释放弹药、命中事件和任务结果作为基线；调整气动精度、毁伤模型或引信规则应与目录/依赖重构分开说明和验证。本 Skill 不授权顺便修改其他武器模型。

## 验证完成标准

- 至少有直接创建对象并推进物理的 headless 测试，**不构造 `GameSession`**，验证它确实能被仿真核心复用，而非只移了文件。
- 按对象风险覆盖可观测结果：轨迹/速度的物理合理性、相关 dt 误差、地形/目标碰撞、引爆与一次性毁伤、弹药变化、终止/回收、reset 和同 seed/输入的可复现性。不要仅测试类名或文件存在。
- 对航弹比较核心预测落点与实际碰撞落点；边界条件选有意义的低空、高速或坡面案例。避免测试直接设置击杀、健康值或瞬移来替代物理过程。
- 更新需要的原生测试目标源文件与链接依赖。当前原生测试源码在 `bvr_sim/src_cxx/test_*.cxx`，Python 游戏/地图回归在 `scripts/tests/`。选择相关回归；修改游戏集成时再验证相同输入的 rendered/headless 状态一致。
- 保持 `BVR_SIM_BUILD_NATIVE_VIEWERS=OFF` 的核心构建可用；先结束 native build，再运行加载该模块的测试。纯 Skill/规则文档修改只需校验内容和发现路径，不必重建引擎。
- 完成时报告对象所在层、创建/推进入口、参数来源、调用方、实际测试及尚未实现的近似。新增物理不应藏在 session、HUD 或 renderer 中。
