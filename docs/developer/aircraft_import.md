# FlightGear Aircraft-2024 批量导入

仓库根目录是外层工作区中的 `bvr_sim/`。导入器读取
`D:/Aircraft-2024/catalog.xml` 和 ZIP，不修改源文件。
最终复扫 664 个 ZIP，选择集合与导入清单一致，无未解决候选。

## 数据路径和边界

- `game/aircraft_import.json`：扫描清单、候选变体、评分、同系列去重依据。
  目前选择 147 个代表包，保留 23 个同系列包的排除依据。737 选择 737-800，
  747 选择 747-8i。包含带辅助喷气发动机的混合动力飞机。
- `bvr_sim/resources/aircraft/FG-*/`：实际 FDM、依赖、源文件校验值、版权说明、
  外部宿主属性及兼容性修复记录。110 个 YASim，37 个 JSBSim。
- `game/assets/cache/aircraft-2024/`：可重建的原始解压文件和转换 recipe。
- `game/assets/registered/FG-*/`：GLB、manifest、源动画清单。缓存及生成网格
  被 Git 忽略；在另一台机器上需使用源 ZIP 重新生成。
- `bvr_sim/resources/imported_aircraft_catalog.json`：独立导入库，包含真实文件
  校验值、后端、动画、喷口附件、测试轨迹和不可试飞原因。

普通任务的五架飞机仍由 `aircraft_catalog.json` 管理。导入库不为民航机或
原型机虚构雷达、武器和挂载；独立试飞使用空挂载、无敌方攻击的训练场景。
所有新模型使用 `FG-` 前缀，避免覆盖已有 F-22/F-16 资源。
`runtime.json` 的 `imported_models` 仅保存独立导入库路径；不把 147 架资源
混入普通场景的 `models` 验证和加载范围。

## 转换和运行

需要仓库的原生构建依赖、Blender，以及 Blender AC3D 插件
`../work/third_party/Blender-AC3D`（固定提交
`cf7fc194c547bc96486dc1c5147371e642143037`）。
Blender 可通过 `--blender` 指定。转换全部为后台 CPU 工作。

AC3D 插件来源：<https://github.com/NikolaiVChr/Blender-AC3D>。先将该仓库
克隆到上述目录，再 checkout 固定提交；无需在 Blender GUI 中启用。

```powershell
python game/tools/import_aircraft.py scan --source D:/Aircraft-2024
python game/tools/import_aircraft.py prepare
python game/tools/import_aircraft.py convert --resume
python game/tools/aircraft_metadata.py
cmake -S bvr_sim -B bvr_sim/build -DBVR_SIM_BUILD_NATIVE_VIEWERS=OFF
cmake --build bvr_sim/build --config Release --target bvr_sim_cpp --parallel 4
cmake --build game/build --config Release --parallel 4
python game/tools/validate_aircraft.py --output runs/aircraft-import/fdm-current.json
python game/tools/aircraft_catalog.py
python game/tools/review_aircraft.py
python -m bvr_game.aircraft_library list
python -m bvr_game.aircraft_library preview FG-737-800
python -m bvr_game.aircraft_library fly FG-A-10 --seconds 30
python -m bvr_game.aircraft_library fly FG-A-10 --render --interactive
```

`--only FG-...` 限定扫描后的处理范围。`convert --resume` 同时校验 GLB、
转换脚本和 recipe，脚本/源模型图变化时重新生成。
`--exclude` 可暂时冻结正在被其他进程验收的资源。
首次配置核心时保持 `BVR_SIM_BUILD_NATIVE_VIEWERS=OFF`。

## FDM 方法

YASim 直接编译上游求解器和积分器，由 `YASimFDM` 在进程内提供 typed API，
无 FlightGear 可执行程序、窗口或遥测依赖。JSBSim 继续使用原有后端，导入器
解析传递依赖并补齐 FlightGear 宿主输入。两者都可直接 `reset/step/advance`。
公开位置和速度采用 north/west/up 米制坐标，姿态采用弧度。

普通机库的 `F15` 保留名称、雷达及空空挂载，气动数据通过共享目录的
`fdm.model = FG-F15C` 使用导入的 `aircraft/FG-F15C/fdm.xml`，与导入库
F-15C 使用同一组源系统及宿主控制器。JSBSim 初始化按目录解析气动资源，
不再把普通机型 ID 固定映射回旧 F-15 文件。缺少指定导入文件时直接报错。

YASim 的中立航向输入（`delta_heading` 绝对值不大于 `1e-4`）只提供滚转
速率阻尼，不再施加回到零滚转角的反馈。因此释放 A/D、将鼠标横向回中后，
已建立的倾斜仍可继续产生转弯；飞机自身的气动稳定性仍由源模型决定。
非零航向指令继续使用倾斜角辅助，显式副翼输入优先且不受辅助覆盖。
这仍是宿主辅助控制，不表示执行了源 Nasal 飞控程序。

交互客户端的 YASim 滚转另走明确的速率模式：`PilotCommand.roll_rate`
（可空，rad/s）经 `Fighter` 传至核心 `ActionSpace.roll_rate_cmd`。
优先级是原始副翼输入 > 滚转速率 > 航向辅助，不能用航向误差的大小猜测
用户是否松开键。鼠标左右可达边界对应 ±60°/s，回中对应零速率；即使鼠标
仍略微偏离中心，也不会再启用接近零度的倾斜角目标。鼠标的向外滚转指令
在接近 65° 倾斜时逐渐减弱；该限制不会主动拉回更大的倾斜，A/D 原始副翼
不受此限制。Agent 的原有航向跟踪接口默认保持可用，`roll_rate=None`。
独立 FDM 可用 `advance(..., roll_rate=0.)` 显式选择速率辅助；JSBSim 不接受
该模式。源气动造成的自然稳定性和执行机构延迟仍然保留。

源控制输入使用确切的命令通道名称，不能按包含 `aileron`、`elevator` 等
子串无差别写入。YF-23 的 `speedbrake-aileron-norm`、Buccaneer 的
`aileron-autostab` / `aileron-droop` 是独立的源系统分支，不重复接收主操纵杆指令。
A-10 的 `sim/model/A-10/controls/flight/sas-elevator` 则是源 hstab 的唯一主输入，
必须明确接入俯仰通道；名称含 SAS 不代表它是重复支路。其源 `square=true` 映射保留。
此修复不改任何飞机的翼面或气动参数。

```python
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native
fdm = native.YASimFDM(0.02, "bvr_sim/resources/aircraft/FG-A-10/fdm.xml")
fdm.reset([0, 0, 5000], [200, 0, 0])
fdm.step(aileron=0.1, elevator=0.0, throttle=0.7)
print(fdm.position, fdm.velocity, fdm.rpy, fdm.visual_properties())
```

源 XML 校准点可能在海平面；验证器对低于 1000 m 的点采用 5000 m 空中初始
高度，并在报告记录原因。`passed` 表示报告中给定条件和时长的有限状态运行，
不是整个包线、起降、原有飞控或全部系统的认证。失败模型保留外观和诊断，
在目录中禁止试飞，不能用其他飞机的物理冒充通过。

B-2 的源尾翼有未连接输入的 `INCIDENCE control-speed`，它会创建一个恒为零
的控制输出，覆盖 YASim 求解器的尾翼配平。导入器移除该孤立速率设置，并保留
`source-fdm.xml` 和 `normalizations.json`；不调整质量、翼面或发动机参数。

## 网格、动画和喷口

递归解析源 XML 模型图、include、omit-node、偏移、选择条件和 AC3D 对象名。
保留对象层级，将 rotate/translate 转换成具名枢轴；按源插值表、倍率、中心、
轴和静态初值转换。运行时读取 typed 快照中的可用属性驱动这些枢轴；缺失
属性保持导入姿态。源 XML 动画完整保留在 `animation_inventory.json`。
AC3D 名称自带的 `.001` 等后缀不能当成 Blender 自动后缀删除。
清除 AC3D 编辑器隐藏标记，再按 XML 的运行时条件选择网格。嵌套 XML 偏移
直接写入局部 basis，避免 Blender `matrix_local` 的父变换补偿；XML 旋转顺序
与 SimGear 的 pitch/roll/heading 一致。近距离 LOD 在导入时选择，未实现动态 LOD。

座舱仪表、地面维修设备、源阴影、灯光锥、烟雾和阻力伞不烘焙为空中静态网格。
Nasal、OSG/shader 特效、动态材质及纹理动画不执行；缺失贴图和跳过特征记录
在 manifest。3DS 使用几何/UV 读取器，旧材质颜色有近似。
`game/aircraft_visual_overrides.json` 记录人工检查后的例外，例如 G91 的远离机体
座舱家具和 Canberra 未连接动画的内部舱门。排除项及原因随 recipe 保存。

喷口优先从具名 nozzle/exhaust 几何测量。找不到时，用源 FDM 发动机位置
投影到附近后向网格，并明确标记 `requires_visual_review` 和近似方法。
运行时生成油门驱动的发光附件；它不是对原 FlightGear 着色器效果的逐项复刻。
渲染器按文件缓存网格/材质，再实例化层级；重复切换不会反复解析同一 GLB。

## 验收证据

本次验证结果：147/147 独立 FDM 在各自报告的初始条件下推进 10 秒，
147/147 在真实 `GameSession` 导入库模式推进 2 秒；不是全包线验证。
6 项独立 YASim 回归通过。A-10、苏-37、737 的渲染/无窗口逐帧状态精确一致。
分别改变舵面及喷口油门，均测得真实 GPU 像素变化；连续五次重建实例后
网格/材质资源数保持稳定，同一 GLB 仅导入一次。
机器可读汇总为 `game/aircraft_import_validation.json`，逐架绑定最终 GLB 和
实际 GPU 截图的 SHA256。Hunter 的外部视角补拍已替换最终联系表中的旧画面。

`runs/aircraft-import/` 保留独立子进程 FDM 轨迹、转换日志和构建日志。
`game/captures/aircraft-library/` 保留 Wicked/DX12 真正捕获的画面与资源统计。
最终逐架检查的 147 架画面位于 `accepted-gallery/`，共 17 张联系表。
`review_aircraft.py` 每组最多九架，生成联系表供逐架检查。代码、文件存在和
shader_errors=0 都不能代替检查像素。修改转换器后须重新生成和检查受影响模型。
`validate_aircraft_runtime.py` 在隔离进程中比较 YASim/JSBSim 的渲染及无窗口
轨迹，并测量实际舵面响应、喷口像素变化、五次重建后的缓存与资源数量。

2026-10-24 控制修复回归：8 项独立 YASim 测试及 16 项会话/客户端测试
通过。新增三种 YASim 飞机双向倾斜保持、双向航向辅助，以及 A-10/苏-37
释放手动副翼后继续转弯的测试；普通 F15 与 FG-F15C 的 300 帧气动轨迹
完全一致。真实客户端 F15、A-10、苏-37 双向键盘输入共 1,200 帧，渲染与
无渲染回放逐帧精确一致，并检查实际 DX12 截图。证据保存在
`runs/aircraft-import/f15-yasim/`，构建及回归日志以 `f15-yasim-` 为前缀。

后续回平反馈复查：旧测试只覆盖鼠标精确回中，漏掉实际客户端鼠标仍偏侧
时的航向辅助重新接管。原实现鼠标移至可达边界只形成约 5° 倾斜目标，
轻微偏侧时目标接近零，足以抵消 A/D 建立的倾斜。源码检查及中立原始
舵面 30 秒对照表明，这不是 YASim 引擎的通用自动改平特性。
交互速率模式及输入别名修复后，30 项回归通过，包含鼠标偏置松键、鼠标
建立倾斜、回中持续转弯、反向操纵、原始副翼优先和辅助通道保留。
A-10、苏-37、Hunter、YF-23 双向输入共 2,800 帧渲染/无渲染状态完全一致，
并检查对应实际 GPU 截图；记录位于 `runs/yasim-roll-followup/`。
