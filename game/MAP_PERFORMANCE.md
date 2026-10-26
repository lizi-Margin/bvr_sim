# 地图性能与区域地形（2026-10-26）

本轮八张已发布地图的两段实飞，平均 FPS 均超过30。**没有达到全程锁30**：密林低空仍有短时长帧。原地图的 JSON、地形、实例数量和位置没有缩减；近景树木 GLB 字节不变，远景采用明确的 LOD 近似。

启动入口已增加独立加载窗口：校验、读取、图形初始化期间均显示当前阶段，取消/关窗能终止自己的加载进程；Ctrl-C 也经过实际验证。初次加载本机约52–62秒。确认出击若仍使用当前地图，会直接复用已载入场景；换图才重新校验及装载，期间恢复加载提示。诊断日志位于 `game/logs/startup/<时间-进程号>/`，含 `status.json`、`events.jsonl`、`worker.log`。本轮修复记录在 `work/startup-fix-20261026/`。

| 地图 | 原低空 / 巡航 FPS | 当前低空 / 巡航 FPS | 当前 1% low（低空 / 巡航） |
|---|---:|---:|---:|
| 河谷机场 v56 | 149.89 / 161.32 | 171.98 / 198.17 | 94.58 / 100.90 |
| 河谷林冠 v60 | 3.29 / 3.66 | 32.24 / 172.65 | 14.04 / 96.95 |
| 连续森林 v61 | 1.41 / 1.44 | 41.87 / 115.81 | 13.20 / 82.96 |
| 战雷原树河谷 v91 | 9.64 / 10.34 | 80.09 / 94.28 | 44.81 / 64.66 |
| 源地形道路森林 v237 | 0.71 / 0.71 | 38.39 / 39.13 | 22.74 / 27.19 |
| 战雷原资源·原始法线 v259 | 0.70 / 0.70 | 39.42 / 38.76 | 26.56 / 23.60 |
| 林缘地表 v268 | 0.71 / 0.70 | 38.87 / 39.15 | 25.19 / 27.40 |
| 连续森林·远景优化 v326 | 19.68 / 20.00 | 38.57 / 40.08 | 20.07 / 26.22 |

条件：F16、seed101、High、1920×1080、原生100%比例、各地图保存的天气，HUD、物理和出击日志开启。每图独立进程串行运行；850米和2400米各20秒墙钟时间，预热至少5秒。加载、预热、截图和编码不计入 FPS。硬件是 Ryzen5950X 和 RTX2080Ti（本机22528MiB），驱动610.88；其他用户进程保持原状。1% low 为最慢1%帧的平均帧时间取倒数。结果仅覆盖这些有限航线。

原始数据在仓库 `work/fps-quality-20261026/final-fps.json` / `.csv`；各行关联原始报告和真实截图。FIR 最终 manifest 修正了来源元数据，实际测试与最终近/远 GLB 的字节哈希完全相同；统一的核心和渲染二进制哈希也写在汇总中。

## 修改内容

- 静态树木使用世界矩阵并去除无用根节点；清场时显式删除扁平化的子实体。LOD 的千米空间索引保留原阈值及滞回，初次加载仍完整初始化。
- 原本重复遍历/复制的树木包围盒、源树索引改在引擎普通上传中写入。稳定几何前缀、对象身份、网格、布局和环形上传缓冲区均参与有效性检查；发生变化即重新计算。动态对象继续普通更新。
- WT 远树使用来源可追溯的原色/原法线卡片和线性光、alpha 加权 mip；FIR 使用原源顶点支撑凸包、原线性颜色。近 GLB、批次姿态、树干位置和空间覆盖全部核对。
- 修正引擎16位半精度绘制距离超过65504米变成无穷大的问题：内部保存公里，读取恢复米，保持结构大小和相对精度。
- 共享核心只把细节高度网格的验证上限从1024放宽到4096（与既有基础网格一致），没有更改插值、飞行动力学或时间步长。换图前重置已暂停的旧出击，满足核心 tick0 才允许换地形的约束。

静态上传 A/B/A 为25.17→39.23→25.26 FPS；画面差异低于两次关闭缓存之间的时间噪声。八个空间 LOD 相机/跳转检查的状态字节一致。原/新核心同种子、相同 typed 指令300 ticks 的帧完全一致。原生直接执行测试52/52通过；CTest 本次没有注册测试，不计作通过。相关 Python 回归、换图和大网格测试另有日志。

## 2048公里区域候选

`source-regional-horizon-v327@8d00e8c01c008c2dab680bab`，菜单名称为“林缘地表·2048km天际线 v327”，质量标记 `candidate`。双击 `game/Launch-Regional-Horizon.cmd` 可打开 F16/High。源地图是林缘地表 v268。

保留原128公里区域的40米网格和原20/5米细节网格；区域外增加4公里采样的2048×2048公里共享高度场，并以4公里过渡带接上原范围。外围高度和宏观地表复用源数据的镜像采样，**没有新增地理测绘数据**。外圈宏观图使用未绘制中央森林掩码的原源图，避免把中央森林方块重复到地平线。核心与渲染加载同一个版本化高度文件；没有额外背景地平线网格或新加遮挡雾。

实际固定机位：低空37.13 FPS、8500米41.15 FPS、12000米斜视50.41 FPS。16000个区域高度点的核心/已上传网格最大误差约7.56e-12米，12000个原区域点差异约3.70e-12米；实际 GPU 树根抽样误差小于0.01米，shader错误0。森林原有色块边界在高空仍可见，尚未达到战雷参考画面一致性。对比图及逐项复查在 `work/fps-quality-20261026/horizon-before-after.png` 和 `regional-release-review.json`。

新地图包冻结在 D 盘资源库，由原菜单索引管理；原八个版本保留。所有检查范围均有限，不能代替全地图、全视角和所有硬件验证。

## 构建与复现

本机默认运行时指向 `D:/bvr_sim_resources/iteration-cache/fps-quality-20261026/` 下的 `engine`、`renderer-final/Release` 和 `core-regional/Release`；实际源码/二进制已冻结，未修改原上游引擎。注册远 LOD 位于同一 D 盘资源库，配置含 manifest 哈希。换机器应连同这些资源迁移并更新绝对路径。

在已准备宽图元标识、材质缓存及诊断的**独立引擎副本**上，依次执行（不要对当前运行中的二进制或唯一源副本重复打补丁）：

```powershell
python game/tools/prepare_inline_ground_bounds.py --engine NEW_ENGINE
python game/tools/prepare_static_upload.py --engine NEW_ENGINE
python game/tools/prepare_far_distance.py --engine NEW_ENGINE
cmake --build NEW_ENGINE_BUILD --config Release --target WickedEngine_ext_shaders --parallel 4
cmake -S game/native -B NEW_RENDERER_BUILD -DWICKED_SOURCE=NEW_ENGINE -DWICKED_BUILD=NEW_ENGINE_BUILD -DBVR_WIDE_PRIMITIVE_IDS=ON
cmake --build NEW_RENDERER_BUILD --config Release --parallel 4
cmake -S bvr_sim -B NEW_CORE_BUILD -DBVR_SIM_BUILD_NATIVE_VIEWERS=OFF -DBVR_SIM_BUILD_TESTS=ON
cmake --build NEW_CORE_BUILD --config Release --parallel 4
python game/tools/benchmark_map_flights.py --output NEW_OUTPUT --seconds 20 --hidden
```

引擎父版本是 `D:/bvr_sim_resources/engine/wide-primitive-v257/engine`；先为新副本配置相应引擎构建目录。补丁从该父版本重放后，两个修改源文件与实际构建源的 SHA256 完全一致，见 `patch-reproduction.json`。补丁工具的来源检查失败时应停止，不能盲目覆盖。`renderer-final` 是验证过的 Release 副本；编译产物不会自动覆盖它，应在重新验证后更新 runtime。

离线扩大区域使用 `game/tools/extend_source_region.py --map SOURCE_MAP --output NEW_EMPTY_DIRECTORY --macro-report SOURCE_MACRO_REPORT`，然后按 MAP_AUTHORING 流程重新抓图、复查及发布。不要直接修改已发布版本。

未采用的试验包括暗色整树卡片、无净收益的静态姿态缓存、批次合并、前向渲染诊断和夹取边缘生成的背景网格；失败产物保留在工作目录，均未进入默认路径。
