# 玩家指向飞控与调参

当前为开发候选。F-22、F-16、A-10已有实际响应输入带和调参记录；完整包线、地图画面和最终性能尚未验收。其他机型保持“模板配置，未逐架调校”标记。

## 控制和显示

- 鼠标指定世界方向；靠近窗口边缘可持续转向。投影使用真实窗口尺寸、相机姿态和垂直 FOV。
- 鼠标移动按当前投影转换为世界目标的方向变化；相机追随、滚转、缩放本身不改变目标。窗口尺寸变化与自由观察结束会重设指针基准，停在原位不会产生新的飞行意图。将光标移回屏幕中心会反向修正目标，并不直接命令机翼水平。
- Agent 经 `FlightGame.submit_player(...)` 提交世界意图后，客户端会同步已滤波与未滤波目标，清除旧边缘转向并在下一次鼠标采样时重建指针基准。静止光标不会把意图拉回旧目标，即使此前从未采样鼠标、光标停在边缘或目标接近垂直/位于后方。真实鼠标位移后重新开始指向控制。普通鼠标帧走同一个核心提交入口，但保留自身的连续滤波状态。
- W 压低机头，S 拉起；A/D 滚转。W/S 同按表示中立俯仰请求，仍接管该轴并阻尼角速度。
- 辅助模式的手动俯仰请求角速度，实际舵面仍受变化率、迎角和可取得的过载反馈约束。松键后按机型配置平滑恢复指向跟随。
- 辅助模式的 A/D 也请求配置中的最大滚转角速度，通过源 FDM 实测角速度闭环控制；原始手动模式仍直接控制副翼。`max_edge_pan` 限制边缘持续转向领先当前视线的夹角，不限制累计转过的世界航向；`edge_recenter_seconds` 是边缘角速度请求的平滑时间。
- C 自由观察冻结原世界飞行意图，期间键盘仍可接管。右键缩放。
- F5 切换辅助/原始手动模式。原始手动模式保留直接舵面和正常失速、失控可能。
- P 暂停；暂停时 F6 安全加载配置，`.` 精确推进。F9 打开本次或最近一次出击日志目录。
- 琥珀色 AIM 为原始指向目标，白色 NOSE 为机体前向，青色 PATH 为实测速度方向。
- `ENERGY / CLIMB DEMAND LIMITED` 表示辅助层降低了爬升请求；原始 AIM 仍保留。`ASSIST / ENVELOPE LIMIT` 表示迎角/过载等保护正在限制输入。

这些文字不证明飞机能持续跟踪任意目标。持续85度爬升会耗尽能量；控制器只能改变输入，不能添加推力或强制姿态。

## 逐机型配置

从仓库根目录运行：

```powershell
python -m bvr_game.player_profiles validate
python -m bvr_game.player_profiles show F22
python -m bvr_game.player_profiles list
python -m bvr_game.player_profiles set F22 --key input.sensitivity --value 1.1
```

`show` 返回 `profile`、`units`、源文件与文件哈希；有效配置自身的哈希仍只覆盖配置及其继承元数据。资源获取、转换、注册和地图生成命令见 [RESOURCE_LIBRARY.md](RESOURCE_LIBRARY.md)。

配置在 `game/config/player_flight_profiles.json`。152个机库条目均显式关联模板，允许机型覆盖。查询结果包含继承链、最终参数、版本、调校状态和有效配置SHA256。文件区分 `control`、`input`、`camera`，并列出单位。

保存先验证完整候选，再原子替换文件。重新加载在暂停边界生效，仅清理玩家控制器状态，不改变 dt、核心 tick 或随机序列。正式评测应冻结配置；客户端的 `player_profiles_frozen` 会拒绝F6重新加载。出击日志保存有效配置，重放验证记录哈希后应用记录值。

`reference_speed` 和 `min_speed` 均以 `reference_density` 对应密度为校准条件，不是所有高度下固定的真空速门槛。控制器用FDM实测密度换算当前速度门槛和动压增益。此归一速度并非默认海平面EAS。`energy_horizon` 是玩家辅助的能量预留时间，`recovery_speed_ratio` 用于恢复退出滞回；它们不是修改FDM性能的参数。

JSBSim提供迎角、侧滑、机体系角速度、法向过载和密度。YASim提供实测自身状态、角速度、迎角、侧滑和其实际大气密度；当前宿主没有标定法向过载通道，日志保留 `None`。

## Python玩家与AI入口

```python
from bvr_game.app import FlightGame, serialize

g = FlightGame()  # headless；不构造渲染器
try:
    g.config.mission = "training"
    g.start(start_position=[-20000, 0, 8500], initial_speed=300)
    g.submit_player(direction=[1, .2, .05], throttle=.85)
    g.step(50)
    print(serialize(g.sim.player_flight_state()))
    # 旧AI入口保持原动作语义，使用它会退出玩家辅助路径。
    g.command(heading=.1, pitch=.05, throttle=.85)
    g.step(50)
finally:
    g.close()
```

玩家控制算法在 `bvr_sim/src_cxx/simulator/aircraft/player_flight.hxx`。`GameSession`只适配命令、武器动作和任务；两条路径使用同一JSBSim/YASim物理、动力、执行机构和环境。

也可直接构造 `native.JSBSimFDM` / `native.YASimFDM`，把 `world_flight_measurements()` 交给 `native.PlayerFlightController.update()`，再调用同一个FDM的 `step_surfaces()`；不需要GameSession、SimCore或渲染器。`game/tools/player_core_only.py`提供实际倒飞、近垂直和跨180度示例。测试会检查实际初始姿态，避免把被忽略的初始化误认成有效测试。

玩家 typed 意图、测量、物理快照与渲染姿态统一为固定地图 NWU；测量中的 `reference_frame` 必须为 `map_nwu`，`gravity_up` 表达实际源 FDM 的反重力方向。JSBSim 原来的速度/姿态 getter 使用随位置变化的局部坐标，位置却已转换到固定地图坐标；长航迹不能混用这两种轴。新世界测量只旋转读出的向量和姿态，不改变源力学或积分。旧 AI/RL getter 和动作语义继续保留，JSBSim 旧 `flight_measurements()` 明确标记为混合坐标诊断数据，不能交给新的玩家控制器。玩家实体和武器释放使用统一后的实测速度；ACMI 继续记录地理位置配套的源局部姿态。每版修改仍须通过完整 AI/RL 帧对比与实际运动验证。

## Agent和重放

驻留宿主的step请求可使用 `player_intent`；与旧 `command` 互斥。Agent策略继续只接收 `ResidentPlaytest.observe()` 的本机状态、实际传感器联系人、告警和任务信息。完整世界帧、ACMI和敌方真值仅供离线诊断，不能作为策略输入。

```powershell
python -m bvr_game.agent game step --state sortie.json --ticks 25 --player-intent '{"direction":[1,0.2,0.05],"throttle":0.85}'
python -m bvr_game.playtest replay TAPE.json --output REPLAY_OUTPUT
python -m bvr_game.playtest replay RESPONSE_TAPE.json --output REPLAY_OUTPUT --render --video --window-start 0 --window-end 20 --visual-profile game/recipes/player_daylight.json
```

普通客户端输入日志支持旧指令、玩家意图、暂停、精确步进和配置重新加载。未知动作会报错。响应输入带逐端点比较完整核心帧；渲染采样不能替代物理积分。普通日志支持 `--render`，采样录像使用响应/航线输入带。

响应实验：

```powershell
python game/tools/player_flight_response.py --output NEW_EXPERIMENT_DIRECTORY --speeds 180 300 500 --cases fine up down turn_45 turn_90 turn_180 vertical circle reversal climb_turn dive_recovery sustained
python game/tools/player_core_only.py --output NEW_CORE_EXPERIMENT_DIRECTORY
python game/tools/capture_player_visuals.py --action projection --output NEW_GPU_EXPERIMENT_DIRECTORY
python game/tools/validate_player_handler.py --case edge --model F16 --map game/maps/river_valley_airfield/generated-map.json --profile-file game/config/player_flight_profiles.json --output NEW_EDGE_INPUT_DIRECTORY --video
python game/tools/validate_player_handler.py --case manual --model FG-A-10 --map game/maps/river_valley_airfield/generated-map.json --profile-file game/config/player_flight_profiles.json --output NEW_MANUAL_INPUT_DIRECTORY --video
python game/tools/validate_player_handler.py --case handoff --model F16 --map game/maps/river_valley_airfield/generated-map.json --profile-file game/config/player_flight_profiles.json --output NEW_HANDOFF_INPUT_DIRECTORY --video
```

`validate_player_handler` 经实际 `FlightGame.input` 输入键鼠事件，运行同一源 FDM 和追随相机；`--video` 保存 DX12 画面。默认边缘转向持续120秒，手动协议79秒，涵盖接管/松键、W/S同按、自由观察加俯仰及有限组合操纵。`--headless` 可独立诊断核心响应。它检查具体协议中的操纵方向、意图保持、舵面变化率和渲染姿态，不能代替完整包线、稳定时间、地图和性能验收。事件为确定性的客户端处理器输入，不代表物理键鼠硬件注入。

`handoff` 是 18 秒衔接协议：普通输入、相对本机实测航向的 typed 方向请求、静止鼠标保持、C 自由观察/返回及真实鼠标位移恢复。F-22、F-16 和 FG-A-10 的当前协议均有实际录像、渲染姿态矩阵核对和完整最终核心帧重放，验证的是衔接语义，不代表其完整机动包线已经调好。

响应实验保存候选模块、控制器源码、参数、输入带、原始观测和摘要；意图每0.5秒更新，当前实现每0.1秒记录状态。摘要中的极值是采样极值，不能当作每个0.02秒核心tick的严格包线保证。最终调参后仍需冻结配置、重新生成正式输入带并完成渲染/无渲染重放。

河谷地图继续使用现有注册库和Baker：

```powershell
python game/tools/build_river_valley_recipe.py --bake
python game/tools/prepare_player_visuals.py
python game/tools/capture_player_visuals.py --action map --output NEW_MAP_REVIEW_DIRECTORY
```

生成器保留不可变地图版本，验证完成后原子更新根指针。依赖同一地图的重放应固定其版本目录和哈希。地图校验、零shader错误、参数存在和文件齐全均不代表画面已经验收。

## 独立玩家试飞

交互试飞现在直接使用 `FlightGame.run_client_frame`，与普通游戏共享键鼠/手柄适配、固定核心 tick 调度、相机、HUD、暂停/单步、F6 和 F9。两种入口默认加载 `player_daylight.json`。独立入口提供无武装训练，Escape 直接关闭窗口；普通游戏仍返回机库。全部 152 项目录（含 147 项导入飞机）均可选择，其他机型继续保持原有模板/未逐架调校标记。

```powershell
python -m bvr_game.aircraft_library fly FG-A-10 --interactive --map game/maps/river_valley_airfield/generated-map.json
python -m bvr_game.aircraft_library fly F16 --interactive --hidden --max-client-frames 120 --map game/maps/river_valley_airfield/generated-map.json --output NEW_BOUNDED_OUTPUT
python game/tools/validate_standalone_player.py --model F22 --map game/maps/river_valley_airfield/generated-map.json --output NEW_STANDALONE_VALIDATION --video
python game/tools/validate_standalone_player.py --catalog-smoke --map game/maps/training.json --output NEW_CATALOG_READINESS
```

`--max-client-frames` 限制客户端帧数；物理仍按原有 `config.dt` 推进，它不表示核心 tick 或仿真秒数。Agent 也可调用 `player_test_flight(aircraft(id), output, render=False, map_path=...)` 得到同一个客户端，再用 `submit_player`/`step` 调试，或向 `run_client_frame` 提交事件。`fly_interactive` 的 `event_source(game,index)` 与 `frame_dt` 用于可复现的入口验证，不需要点击屏幕。

独立入口现在生成带地图、有效玩家配置和资源上下文的标准输入日志，可直接交给 `bvr_game.playtest replay`。F-22/F-16/A-10 的 22 秒协议含实际窗口缩放到 1600×1000 再恢复 1920×1080、暂停/单步、重载与原始手动模式；窗口缩放阶段的录像保留原像素并加黑边，不作为性能验收。三种机型各有 220 帧录像和完整最终核心帧重放。全部 152 项另做 10 tick 的真实启动检查，只证明基本可运行，不能称为逐机型手感调校。

不带 `--interactive` 的原有 `fly --seconds ...` 仍使用旧 AI `PilotCommand` 诊断入口，控制语义与环境保持；4 秒 A-10 的修改前后最终帧及四个轨迹采样完全一致。
