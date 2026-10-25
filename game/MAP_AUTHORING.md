# 离线地图创作与版本迭代

游戏只加载已保存的地图、高度、材质和注册模型。地图生成、资源下载、Blender 转换和美术迭代均在游戏进程外完成；改变出击的仿真种子不会重生成地图。

流程：**创建可编辑工作区 → 修改配方/资源 → 离线烘焙 → 固定机位渲染 → 对照参考图复查 → 发布版本 → 游戏选择版本**。

## 将地图包保存到其他磁盘

版本目录仍由原来的 `game/maps/catalog.json` 管理，地图包可以保存在 D 盘。目录可显式配置 `"storage_roots": {"resources": "D:/bvr_sim_resources/map-library"}`；发布时指定 `--storage-root resources`，临时冻结目录和最终 `published/` 都会写到该目录，C 盘只更新小型索引。再配置 `"default_storage_root": "resources"` 即可让后续发布默认使用该盘。两项均未配置时保留原有库内存储方式；旧版条目没有存储别名，仍从索引所在目录加载。恢复中断的发布会读取 release.json 中保存的存储别名，核对其仍在配置的目录内。

```powershell
python game/tools/maps.py publish --map SAVED_MAP.json --name MAP_FAMILY --label "地图候选版本" --review REVIEW.json --storage-root resources
```

游戏依然通过“战斗准备 → 地图版本”读取同一索引；各版本内部的相对路径和文件哈希校验不变。移动地图库到另一台电脑时应更新索引中的绝对存储根目录；不能用未配置的任意路径或越界路径代替版本包。

## 完整森林的图元标识

源森林 v237 的实际分配曾达到185,661,621个 meshlet。原32位像素编号只给 meshlet 留25位，最多表示33,554,431个；原缓冲区扩容的32位乘法也会溢出。小范围树木探针正常，并不能证明整图渲染正确。该问题会影响从像素编号重建的深度、速度与屏幕空间效果。

当前游戏使用独立源码派生的直接64位编号：32位三角形索引、24位实例索引、8位子集索引，对应 `R32G32_UINT`。索引光栅路径不再建立全局 meshlet 查找表；树木和源网格保持完整。Mesh shader 与 compute visibility shading 显式关闭，path tracing 不属于此模式。新的 shader 源码/缓存与原生模块必须配对，已有上游 checkout 和历史缓存保留。

`prepare_wide_primitive_ids.py --engine SOURCE --profile PROFILE --output OUTPUT` 创建独立引擎和 shader 副本，保存源码修补记录与哈希。构建引擎使用实际目标 `WickedEngine_ext_shaders`，原生模块配置 `BVR_WIDE_PRIMITIVE_IDS=ON` 并指向该独立构建。`validate_wide_primitive_shaders.py` 编译实际编号生产和消费路径；之后仍需原地图、原机位的真实整图截图，以及地形/桥面和核心帧核对。`primitive_id_state()` 返回当前编号模式与实际分配，不能单独证明画面通过参考验收。

## 创建与烘焙

从仓库根目录运行，用新的工作区名称保存每次创作。Agent 可直接编辑 `scene-recipe.json` 中的树林区域（含空地孔洞）、道路、河流、地表材质、载具/建筑资源和散布规则，然后重烘焙。无需游戏窗口或鼠标点击。

```powershell
python game/tools/maps.py create --recipe game/recipes/river_valley_airfield.json --workspace ../work/map-authoring/my-valley
python game/tools/maps.py bake --workspace ../work/map-authoring/my-valley
```

每次配方产生独立的 `bakes/<recipe-hash>/generated-map.json`，已有烘焙目录不会被覆盖。专用河谷/机场派生工具同样在离线运行；输出也能进入下面的渲染、复查与发布流程。地图物理高度、接触网格和建筑碰撞必须与渲染保持一致，不能为了画面单独移动其物理对象。

## Agent 闭环审阅

```powershell
python game/tools/maps.py render --map BAKED_MAP.json --runtime game/runtime-ui.json --output ../work/map-authoring/review-001
```

渲染工具使用真实 DX12 和固定高空、河流斜视、低空树林、地平线、云层机位。保存截图、完整相机、地图/核心/渲染模块哈希和 shader 错误；渲染时核心保持暂停。Agent 逐图检查树冠连续性、树高/密度、空地边界、地表重复、河岸颜色、水面和天空，与用户参考图对照，然后修改工作区配方或注册资产再重复烘焙、渲染。

新版渲染器还会冻结 shader 的云层/水波时钟，场景上传、相机和可见性仍正常更新，让慢帧下的时间累积保持稳定。每个机位先保存第4帧预览与进度，再完成正式截图；可用 `capture_reference_map.py --render-scale 2` 以4K内部采样输出1080p，或用 `--animate-weather` 检查动态天气。报告分别记录核心是否变化、展示时钟是否冻结、内部/输出分辨率，不改变模型细节或植被裁剪策略。旧模块不支持冻结时，会在报告明确记录。

复查必须记录具体问题，不能仅凭构建成功、三角形数量或截图文件存在宣布画质达标。当前历史版本只标为 `baseline` 或 `candidate`，尚未达到参考图效果。可建立如下 `review.json`（使用真实的源地图哈希与渲染报告）：

```json
{
  "schema_version": 1,
  "map_sha256": "SHA256_OF_BAKED_MAP_JSON",
  "quality": "candidate",
  "capture_report": "ABSOLUTE_PATH_TO_CAPTURE_REPORT.json",
  "reference_images": ["ABSOLUTE_PATH_TO_USER_REFERENCE.png"],
  "notes": "逐图对照的具体发现、已解决问题和仍不符合参考图的部分。"
}
```

只有实际完成参考对照后才使用 `reference_matched`；候选版本可以发布供游戏内 A/B 比较，会明确显示“候选”。发布要求渲染报告属于同一地图哈希、有实际截图且 shader 错误为零。

## 发布与选择

```powershell
python game/tools/maps.py publish --map BAKED_MAP.json --name my-valley --label "河谷地图 第一次美术迭代" --review review.json
python game/tools/maps.py list
python game/tools/maps.py verify "my-valley@RETURNED_VERSION_HASH"
python -m bvr_game.app play --map-version "my-valley@RETURNED_VERSION_HASH"
```

发布会把地图高度、高度图、地表贴图、配方、渲染报告、截图和复查意见冻结到 `game/maps/published/<name>/<version>/`；`release.json` 为每个文件记录 SHA256。模型共享注册资源库，但逐级 GLB 和资源 manifest 的哈希被冻结，不能在相同资产 ID 下偷偷替换模型。工作区继续修改不会改变已发布版本。

渲染报告中的实际天空、云层采样、太阳、曝光和雾设置也随版本冻结。游戏确认切换地图时恢复这些设置；切回没有保存天气的旧版本时恢复启动配置。地图不能指定 shader 路径或更改客户端材质策略。离线试调天气可传 `render --visual-profile PROFILE.json --ignore-map-environment`，重做截图与审阅后发布新版本。

若 Windows 文件占用导致最后的目录重命名中断，完整暂存目录会保留；用 `python game/tools/maps.py recover --staging STAGING_DIRECTORY` 核对全部文件后继续发布，无需重新生成地图。

游戏“战斗准备 → 地图版本”列出已发布版本；当前通过 `--map` 显式打开的地图也会保留为“当前地图”。地图选择是准备草稿，取消不会改变当前地图、任务或核心状态；确认出击后才验证并加载新版本。一次客户端中可切换不同版本，出击日志记录实际加载的地图文件及其哈希。自定义资源库可用 `--map-catalog CATALOG.json`。

植被默认为 `vegetation_full_detail=true`：固定使用资源最高级网格，不按地图 LOD 距离切换，不按距离隐藏或淡出。保留正确的视锥、地形遮挡和深度测试。旧策略仅可在独立复现配置中用 `false` 对照，游戏的画质档位不会开启树木距离裁剪。

## 固定几何的地表材质迭代

已有烘焙地图可以单独衍生一个本地战雷贴图候选，避免为了试材质重新生成数百万棵树：

```powershell
python game/tools/build_wt_material_variant.py --source SOURCE_GENERATED_MAP.json --textures LOCAL_TEXTURE_IMPORT_REPORT.json --output NEW_MAP_DIRECTORY --resolution 8192
python game/tools/capture_reference_map.py --map NEW_MAP_DIRECTORY/generated-map.json --output NEW_CAPTURE_DIRECTORY --views woodland_aerial daylight_horizon --warmup-frames 8
```

工具检查源纹理哈希，保留原始地形高度文件、全部实例、河流与道路表面、核心环境和任务，并逐项核对一致性。森林地表使用真实航空树冠纹理，草地和农田使用真实源颜色图；各角色的 `macro_tile_m` 记录明确的世界铺设尺寸。`aerial_canopy_albedo` 防止旧的均值替换逻辑抹掉树冠纹理。平坦法线和粗糙度0.9是工程近似，三维树木不因此删减或远距隐藏。

这是专用的离线材质衍生流程。`scene-recipe.json` 中保存源地图与导入报告的哈希以及衍生参数；应通过该工具重放，不能把它当作普通全量 `bake` 配方能逐字节重现的声明。运行时仅加载已保存结果。新候选仍须完成真实原生渲染和逐图复查，`variant-report.json` 的一致性检查不代表画质达标。

通用本地 PBR 材质替换可使用 `rebake_map_materials.py`。策略 JSON 的 `materials` 按 `grass`、`farmland`、`forest`、`soil`、`rock` 指定要替换的角色；每项必须为 `provider: local_texture`，并给出 `base_color`、`normal`、`roughness_map` 及各自的 `_sha256`。`color` 为线性颜色乘数，`tile_m` 为细节实际米制尺寸，`macro_tile_m` 为离线宏观采样尺寸。

```powershell
python game/tools/rebake_map_materials.py --source SOURCE_GENERATED_MAP.json --policy GROUND_POLICY.json --output NEW_MATERIAL_DIRECTORY --resolution 8192
python game/tools/build_reference_woodland.py --source-map SOURCE_GENERATED_MAP.json --forest-asset REGISTERED_GROVE_ID --clearing-policy CLEARINGS.json --output NEW_WOODLAND_DIRECTORY --resolution 8192
```

小型空地策略示例为 `{"count":320,"radius_range_m":[35,125],"seed_offset":149}`。它重做装饰性森林分布与地表掩码，保留机场和聚落开口，并核对共享高度、接触、障碍物、水域、道路和任务不变。生成结果须经真实视角复查后再发布。

若高空看到笔直的林区外缘，应先核对实际种植范围。关闭运行时 LOD 无法补出范围外不存在的实例。已有中央林地可离线扩展：

```powershell
python game/tools/extend_baked_woodland.py --source SOURCE_GENERATED_MAP.json --output NEW_EXTENDED_MAP_DIRECTORY --outer-half-m 40000
```

此工具保留中央所有实例、物理高度、接触面、水域和任务，增加同一注册原树网格的独立树木位置，并扩大与核心三角形对齐的 R32 树根高度图。40公里半宽、5米间距对应16001×16001像素，约1GB；旧高度图区域必须逐值一致。新增点来自固定世界网格的随机偏移，近远密度过渡是保存进地图的空间布局，运行时不读取相机距离作删减。每棵树仍使用原资源最高网格。种植范围和素材当前针对 `WT-OakMediumGrove64-v91` 中央±9800米候选，不能直接用于任意来源地图。扩展后的范围、树间距、道路和水域避让会再做空间验证；这不代替真实截图审阅。

已烘焙材质可与另一份相同地形/地表掩码的树木布局组合：

```powershell
python game/tools/rebake_map_materials.py --source GEOMETRY_MAP.json --reuse-materials MATERIAL_MAP.json --output NEW_COMPOSED_MAP_DIRECTORY
```

组合工具核对高度文件哈希、全部地表掩码声明、道路、河流、机场、聚落和物理环境一致；不满足时拒绝复用。结果保留几何地图的实例、分块、任务及高度图，使用材质地图已有的哈希校验图像，并记录两份输入的哈希。仍需对组合结果重新抓图，不能把两份输入各自的截图当作组合版本的验收。

若原绿地与枯草直接替换的对比过强，可增加 `--mix-source-ground`。它只对实际使用的地表宏观颜色图进行线性光混合，固定世界分布的枯草比例为0.25至0.7，法线和粗糙度保留复用材质的通道；这是明确记录的美术混合，不是实测植被/BRDF。输入图像尺寸、地形和掩码必须相同，原文件保持不变。

抓图时可增加 `--ground-check-extent-m 40000`：除保存真实画面外，再抽取12000处 GPU 高度、已上传地形网格及四组原树顶点，与 typed 核心高度和保存的树木位置核对。该选项用于有独立原树批次的地图，误差阈值为0.01米；报告明确限定抽样范围，不代表逐树或全顶点认证。

## 离线云层覆盖图与远景雾色

```powershell
python game/tools/bake_cloud_weather.py --output NEW_WEATHER_DIRECTORY
```

该工具烘焙固定种子的周期性 RGBA8 数据图：R 为云覆盖、G 为云类型、B 为降雨、A 为1。它是人为设计的分布，云的光照和体积仍由 Wicked 原生体积云渲染器计算。视觉配置通过 `cloud_weather_map: {"file":"ABSOLUTE_PNG_PATH","sha256":"FILE_SHA256"}` 指定图像，并从生成的 manifest 取 `cloud_layer.weather_scale_per_m`。要求支持 `BAKED_CLOUD_WEATHER_MAP` 的渲染模块；数据必须为线性 RGBA8、宽高128至4096。

`horizon_height_fog.color_linear` 可指定三通道线性雾色，要求 `FOG_COLOR_PROFILE_V1`。未指定时恢复引擎默认雾色。发布工具核对云图哈希，将图像冻结进版本目录；地图加载时再次核对。切换到没有自定义数据的版本会清除旧云图和雾色覆盖。无效环境配置在验证完成前不会替换当前天气。以上配置属于美术近似，不代表实测大气。

`--grass-texture air_smolensk_meadows_b` 可选择另一张已解码草地/田块源图，避免把自带大尺度沟壑的 `meadows_a` 重复铺到平地。应保留各候选与真实截图，再判断素材和世界铺设尺寸是否合适。

远处随地形铺设的旧水面另可离线修复：

```powershell
python game/tools/repair_outer_water.py --source SOURCE_GENERATED_MAP.json --output NEW_WATER_VARIANT_DIRECTORY
```

它按共享核心高度网格的每个实际三角形裁分远处水面，避免采用另一条对角线后内部穿入地形；常规间隙为0.25米，区域接缝保持原0.025米。水域平面覆盖范围不变，区域内恒定水位和自然岸线交会保留；地形、接触、障碍物和任务不变。报告对新三角形内部多组重心坐标调用真实 typed 核心高度核对。完整地图配方可显式设置 `landscape.outer_water_core_plane_conform=true`，使用相同修复方法。此修复保留旧的远河随地形起伏近似，未将其变成有统一水位的真实长河。

## 原始地形采样的独立地图流程

`build_source_terrain_map.py` 直接使用已提取、带哈希的原始地形采样。它绕过旧的正弦山丘与手绘河带，生成128公里范围、40米基础网格，以及20米和5米局部网格；原始样本间距为32米，细化属于重采样，不代表新增测量精度。跑道、滑行道和停机坪做明确记录的局部平整，其余地形来自同一份源采样。

```powershell
python game/tools/build_source_terrain_map.py --template TEMPLATE_MAP.json --height-report HEIGHT_REPORT.json --macro-report MACRO_REPORT.json --output NEW_SOURCE_MAP_DIRECTORY
python game/tools/validate_source_terrain_map.py --map NEW_SOURCE_MAP_DIRECTORY/generated-map.json --output NEW_HEADLESS_REPORT_DIRECTORY
```

当前候选水位由美术设为0米，尚未确认原游戏水位。水面轮廓逐个裁分共享核心的实际三角形，保留低于水位的部分和干燥岛屿；不是对双线性高度做另一次估算。渲染水面偏置为0.025米，核心水域来自相同轮廓。原地图地面车队路线可能穿过新水域，候选会清空地面任务单位；须另行创作路线才能认证地面玩法。

3201²基础高度需要支持4096行列上限的新核心。可通过 `BVR_SIM_CPP_PATH` 指向独立构建，再传匹配的 `--runtime RUNTIME.json`，无需替换默认模块。仅支持512行列的旧核心会拒绝这类地图。

```powershell
python game/tools/populate_source_woodland.py --source SOURCE_TERRAIN_MAP.json --landclasses LOCAL_LANDCLASS_REPORT.json --large-asset REGISTERED_MATURE_GROVE --large-fraction .65 --output NEW_POPULATED_MAP_DIRECTORY
python game/tools/bake_source_macro_region.py --source POPULATED_MAP.json --class-report CLASS_REPORT.json --macro-report MACRO_REPORT.json --texture-report TEXTURE_REPORT.json --resolution 8192 --repeat-detail --output NEW_REGIONAL_MATERIAL_DIRECTORY
```

种植工具读取原始全局覆盖与局部密度位图，按源密度创建固定世界坐标树根，使用已注册的原始最高网格；大树和中树比例是显式美术参数，并未还原原游戏全部物种、灌木或随机序列。`--positions-from SAVED_POINTS.npy` 可以复用候选点池，会重新验证种植范围、水域、完整机场铺装与源掩码。运行时不按相机位置重新抽样。工具拒绝重复向已经有原树批次的地图种植。

区域材质工具将中心20公里单独烘焙为8192²颜色图，基础地表仍使用全域源宏观颜色。按原始类别权重、颜色、尺寸和UV进行线性光混合；不会从512²源纹理中恢复不存在的细节。`--repeat-detail` 额外使用已有视觉配置中的通用草地细节，是明确的材质近似，不是原游戏完整地表 shader。所有高度、任务、接触、障碍、水域与三维实例逐项保留。

## 基于源地形另行创作森林环境

原 Smolensk 数据以农田、草地为主；复制其种植掩码不能自动得到参考图中的大片森林。可保存独立策略，在真实源地形上创作森林分布：

```json
{"kind":"authored_reference_woodland","seed":189,"clearing_cell_m":700,"clearing_radius_m":[75,145]}
```

空地可选 `clearing_probability`（0–1）以及 `clearing_shape: "world_noise"`；后者使用 `clearing_edge_scale_m`、`clearing_edge_strength` 指定固定世界坐标的边缘变化，避免所有开口共享相同的三瓣/五瓣轮廓。它们同时用于离线种植与颜色覆盖，分块计算和单点编辑保持一致。`road_root_clearance_m` 仅改变已声明道路显示/接触面的树根避让，机场、其他接触面和实体仍保留原来的完整树冠半径避让；河岸仍单独使用 `shore_root_clearance_m`。这些是明确的地图美术参数，不是运行时距离裁剪。

种植工具支持显式 `--medium-asset`，可与 `--large-asset` 一起使用已注册的原始法线派生资源。更换资源前须核对每个三角形角点的位置、UV0/UV1、贴图、材质、节点和树根布局。导出器可能因法线变化重新合并顶点，不能仅凭索引缓冲区不同判定几何变化，也不能仅凭三角形数量相同判定几何未变。

```powershell
python game/tools/populate_source_woodland.py --source SOURCE_TERRAIN_MAP.json --landclasses LOCAL_LANDCLASS_REPORT.json --authored-biome BIOME_POLICY.json --grid-spacing-m 20 --jitter-m 4 --large-asset REGISTERED_MATURE_GROVE --large-fraction .85 --seed 189 --output NEW_AUTHORED_GEOMETRY_DIRECTORY
python game/tools/author_woodland_materials.py bake --source SOURCE_TERRAIN_MAP.json --policy BIOME_POLICY.json --textures TEXTURE_REPORT.json --focus-color REGIONAL_SOURCE_COLOR.png --large-asset REGISTERED_MATURE_GROVE --output NEW_GROUND_BUNDLE_DIRECTORY
python game/tools/author_woodland_materials.py compose --source NEW_AUTHORED_GEOMETRY_DIRECTORY/generated-map.json --materials NEW_GROUND_BUNDLE_DIRECTORY/materials.json --output NEW_AUTHORED_MAP_DIRECTORY
```

不规则小空地和少量宽草甸由固定世界坐标规则生成，三维种植与地表颜色共用策略。林下使用原森林源颜色与UV；水域、机场和已有实体保留保守避让。合成前核对高度、细分网格、核心环境、森林策略、范围和原树资源版本，不一致时拒绝输出。森林分布与地表类别已经经过创作，不能称为原 Smolensk 的准确复原。

种植、颜色空地与避让帮助函数的版本哈希也必须一致。未记录帮助函数版本的旧材质包须重新烘焙后用于后续合成；已有完整烘焙地图仍可独立加载，不依赖再次运行生成器。

这些流程均先保存地图再运行游戏，不在出击时生成。专用 `source_terrain_adapter` 配方须通过对应工具重放，不能交给旧通用生成器。所有候选仍需真实原生截图、GPU树根抽样与人工画面对照；离线工具成功、测试通过和无 shader 错误均不代表参考画质已经达标。正式发布继续使用上方版本库流程。

## 高空阴影与同场景对照

引擎原始太阳级联为8、80、800米；数公里高度的飞机视角需要单独验证阴影范围。视觉配置可显式指定 `sun_shadow_cascades_m: [500,4500,10000,24000]` 和 `sun_shadow_resolution: 4096`。后者要求支持 `SUN_SHADOW_PROFILE_V1` 的渲染模块，每个级联使用4096像素；四个级联的图集宽度为16384。分辨率允许128至8192的二次幂或自动值-1，级联数乘分辨率不得超过16384；距离必须严格递增且不超过50000米。

这两项随地图天气一起冻结，切回不含覆盖项的旧地图时恢复启动配置或引擎默认值。无效配置在替换天气和光源之前拒绝。它们控制实际三维几何的阴影，视觉效果仍需截图验证，不能据配置值声称树影已经正确。

```powershell
python game/tools/capture_reference_map.py --map SAVED_MAP.json --runtime MATCHING_RUNTIME.json --visual-profile AERIAL_SHADOW_PROFILE.json --views woodland_aerial reference_downlook --environment-variant CONTROL_PROFILE.json --variant-views woodland_aerial --warmup-frames 8 --render-scale 2 --output NEW_COMPARISON_DIRECTORY
```

`reference_downlook` 使用2482米高度、较大俯视角，便于和全部为地面的参考画面对照。`--environment-variant` 可重复指定，复用同一个已加载场景，保存每档实际配置和截图；变体只替换允许的天气和太阳参数，最后恢复基准配置。报告仍会确认全部抓图期间核心帧不变。版本发布仅采用基准配置，额外变体是对照记录；若选中某个变体，应以它重新生成正式抓图报告。

## 道路、原始桥梁和真实空地材质

`plan_source_roads.py` 是当前源地形候选的离线创作工具：用100米规划网格和实际高程、水域做带坡度成本的A*，保守避开水体，再保存平滑后的道路；仅中央一处预定河道由明确的桥梁连接。它不是任意地图的通用导航生成器。路径、空地、河岸根部间隙和森林道路走廊写在同一份策略中。

```powershell
python game/tools/plan_source_roads.py --source SOURCE_TERRAIN_MAP.json --road-materials game/recipes/reference_road_pbr.json --bridge-asset WT-MoskvoretskyBridge-v224 --bridge-deck ORIGINAL_NORMALIZED_DECK.json --output NEW_ROAD_BIOME_POLICY.json
python game/tools/build_source_road_map.py --source SOURCE_TERRAIN_MAP.json --policy NEW_ROAD_BIOME_POLICY.json --output NEW_ROAD_MAP_DIRECTORY
python game/tools/validate_source_roads.py --map NEW_ROAD_MAP_DIRECTORY/generated-map.json --output NEW_ROAD_CORE_REPORT_DIRECTORY
```

道路面和路肩逐个裁分实际地形三角形，避免长条网格跨过地形对角线后悬空或穿地。道路的显示面与核心接触面使用相同顶点和索引。桥梁保留原始LOD0的6375个三角形；当前放置使用显式半比例和小幅倾斜来衔接真实两岸。桥面接触来自原始道路材质对应的64个三角形，栏杆、桥墩目前只有显示几何，没有体积碰撞；不能因此宣称已认证完整地面驾驶。

河岸策略可设 `shore_root_clearance_m: 3`，允许树冠自然伸向水面，同时保留干燥的树根位置；机场与实体仍按完整轮廓避让。长曲线道路使用其实际三角形足迹，而非整条道路的凸包。森林种植和颜色合成必须使用与道路地图哈希一致的同一策略。

```powershell
python game/tools/populate_source_woodland.py --source NEW_ROAD_MAP_DIRECTORY/generated-map.json --landclasses LOCAL_LANDCLASS_REPORT.json --authored-biome NEW_ROAD_BIOME_POLICY.json --grid-spacing-m 20 --jitter-m 8.5 --large-asset WT-OakLargeGrove64-v181 --large-fraction .85 --seed 189 --output NEW_ROAD_FOREST_DIRECTORY
python game/tools/author_woodland_materials.py bake --source NEW_ROAD_MAP_DIRECTORY/generated-map.json --policy NEW_ROAD_BIOME_POLICY.json --textures TEXTURE_REPORT.json --focus-color REGIONAL_SOURCE_COLOR.png --open-ground-policy game/recipes/reference_open_ground_pbr.json --large-asset WT-OakLargeGrove64-v181 --output NEW_ROAD_GROUND_DIRECTORY
python game/tools/author_woodland_materials.py compose --source NEW_ROAD_FOREST_DIRECTORY/generated-map.json --materials NEW_ROAD_GROUND_DIRECTORY/materials.json --output NEW_ROAD_ART_DIRECTORY
```

真实草地与枯草的线性均值用于无法分辨2米微纹理的宏观像素，并加入明确的世界坐标颜色变化，避免在空地里保留没有立体建筑对应的城镇照片。近处通过材料的 `ground_detail` 加载同一版本固定的颜色、法线和粗糙度图片，优先于启动配置的通用细节。发布会冻结这三个通道以及桥面验证数据、水域轮廓；源文件后续修改不影响版本。配方中的本地资源路径及哈希需要随资源库位置更新。

已种植的地图可以在颜色烘焙时添加 `--retain-populated-layout --forest-transition-m 12 --road-shoulder-policy game/recipes/reference_road_pbr.json`：验证保存的森林策略后保留所有树木和几何，仅在颜色覆盖上柔化林缘。空地策略可以加入哈希固定的第三种 `soil` 材质及世界坐标 `variation` 参数；这些是显式美术混合，不能增加源纹理本身的分辨率。路肩将宏观地表与真实 gravel_floor_03 微细节叠加，要求提供 `SURFACE_DETAIL_UVS_V1` 的原生模块；旧模块会在修改场景前拒绝此类地图。新模块只为道路等表面补充世界坐标 UV1，保留树木的源 UV1 编码和地形 UV。

道路材料使用已有Asphalt033以及通过资源CLI下载的Poly Haven `dirt_floor`、`gravel_floor_03` 2K贴图：

```powershell
python game/tools/asset_library.py --cache D:/bvr_sim_resources/asset-cache fetch polyhaven dirt_floor --resolution 2k --max-mb 80
python game/tools/asset_library.py --cache D:/bvr_sim_resources/asset-cache fetch polyhaven gravel_floor_03 --resolution 2k --max-mb 80
```

若地图包含源桥梁，真实抓图会额外核对注册GLB的路面顶点、原生实例变换与核心桥面三角形；这项检查不等同于GPU逐顶点读回，也不覆盖桥墩或栏杆碰撞。`bridge_oblique` 为近处桥梁审阅机位。

## 地图性能与切图完整性

`profile_map_runtime.py` 在1920×1080、high、原生渲染比例1下暂停核心，分别测固定俯视和地平线视角。它输出每帧完整客户端耗时、原生CPU分段、引擎GPU时间戳、截图及可见几何统计。GPU分段使用引擎缓冲和均值，存在读回延迟，嵌套分段不可直接相加；FPS以实际墙钟样本计算。对照必须使用相同地图文件、天气、阴影范围和相机。原始地图与发布包可能有不同的冻结天气，不可把二者当作同条件对照。保留其他GPU任务并记录干扰，不结束用户进程。

```powershell
python game/tools/prepare_runtime_diagnostics.py --engine INDEPENDENT_ENGINE_FORK
cmake --build ENGINE_BUILD --config Release --target WickedEngine_ext_shaders
python game/tools/profile_map_runtime.py --map EXACT_SAVED_MAP.json --runtime MATCHING_RUNTIME.json --visual-profile MATCHING_PROFILE.json --frames 12 --warmup 8 --output D:/NEW_PERFORMANCE_REPORT
```

原生地形批次从16×16单元合并为64×64单元，保留每个采样点、三角形对角线、材质和镂空区域；地形与道路表面在所有属性就绪后只上传一次。固定完整精度树木不再逐帧做距离状态检查；贴地包围盒与补丁数组在加载时准备，组件索引改变时才更新索引。相机视锥和贴地包围盒仍在每帧使用，树木没有因此被移除或简化。

`cached_tree_heights: true` 是可选的静态源树木高度缓存，要求 `CACHED_TREE_HEIGHTS_V1` 模块和同版本 `bvrGroundHF.hlsli`。地图加载时从相同核心地形求每个源树根高度，GPU点流改用16字节的north/west/height记录，元数据明确标记格式；旧8字节点流仍可读取。使用独立着色器目录与缓存，不覆盖运行中的旧缓存。实际GPU顶点/地形读回检查仍是验收项，编译通过不证明贴地精度。

切图曾因大量网格的临时/旧SRV延迟释放耗尽50万项bindless池，随后地形和字体同时缺失，`shader_errors`仍为0。诊断API暴露累计失败数、空闲低水位和待回收数量。`validate_candidate_map_ui.py` 现在要求下视固定相机的GPU正深度覆盖率大于97%、无非法深度值、资源描述符分配失败为0；每次选择保存独立integrity报告。深度覆盖不能证明材质或字形正确，仍须逐张审阅新图、切旧图和切回新图的截图。

## 保留远树的几何 LOD

2026-10-25 已获准简化远景几何，同时保留每棵树的位置、森林覆盖与可见性。`vegetation_full_detail: false` 启用注册的距离几何，`vegetation_lod_distance_m: 1200` 带10%往返滞回。所有植被的绘制距离始终无限，不以LOD或旧的`cull_distance`删除远树；正常视锥、实际深度遮挡与亚像素采样仍存在。`vegetation_state()`报告总树数、近远几何树数和距离隐藏数量；不能把提交数量当成逐像素可见证明。

`bake_tree_distance_lod.py` 在Blender离线处理原始单树来源：高精度GLB逐字节复制，远处每棵树使用原模型烘焙的三个侧视图、一个顶视图及投影法线，共8个三角形。保留原64个槽位、姿态、树根锚点和UV1树索引。远景属于轮廓与光照近似，树冠可能比完整几何更密，仍需固定机位审阅；没有生成或猜测植物形状。当前战雷源LOD2的6个三角形依赖Dagor专用impostor重建，导出的原始方片不能直接当成树。

```powershell
& 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe' --background --python-exit-code 1 --python game/tools/bake_tree_distance_lod.py -- --parent ORIGINAL_REGISTERED_GROVE/manifest.json --id NEW_IMMUTABLE_ASSET_ID --output D:/NEW_REGISTERED_RESOURCE
python game/tools/validate_vegetation_visibility.py --map EXACT_NEW_MAP.json --runtime MATCHING_RUNTIME.json --visual-profile MATCHING_PROFILE.json --policy lod-visible --output D:/NEW_VISIBILITY_REPORT
python game/tools/compare_tree_distance_lod.py --map EXACT_NEW_MAP.json --runtime MATCHING_RUNTIME.json --visual-profile MATCHING_PROFILE.json --output D:/NEW_SAME_SCENE_COMPARISON
```

`prepare_visibility_compute.py` 从独立direct64着色器配置生成另一份目录和缓存，补齐实际材质分桶、源卡片法线、地面微细节和F-22涂装计算顺序，允许主画面复用可见像素着色。`visibility_compute_shading`必须搭配`wide_visibility_compute_v1`与对应原生模块；反射仍走原来的光栅路径。用`validate_wide_primitive_shaders.py`编译29种生产/消费变体，`compare_aircraft_visibility.py`和`compare_visibility_shading.py`执行实际材质与整图对照。

新版「连续森林·远景优化 v326」冻结在D盘资源库，保存14,498,176个原树位置，已加入正常战斗准备地图菜单，质量仍标记为candidate。实际同场景对照与CPU调整报告位于`D:/bvr_sim_resources/iteration-cache/map-quality-v275/tree-lod-fullmap-v328`和`tree-lod-cpu-v331`。renderer-v330把共同LOD参数改为每帧读取一次，避免每批树重复查询JSON。固定相机实测约15.5–18.7FPS，保留其他GPU任务，不能据此宣称稳定流畅或达到参考画质。

资源目录链接可以指向目录配置`registered_storage_roots`中明确列出的绝对资源根，目标必须严格为该根下同名资产ID。发布包的地形、材质和文件仍限制在原冻结目录，资源清单与每级GLB仍逐文件核对哈希。

## 当前画面定型与可玩配置（2026-10-25）

按用户要求暂停扩展美术，以v326离线地图为当前画面。renderer-v354在原生1080p、high下采用静态植被世界变换、每帧共享网格材质分类、不可变贴地补丁复用与并行包围盒更新；禁用历史遮挡查询和水面二次镜像渲染。正常视锥/深度、全部树位置、1200米几何LOD、地形、道路和桥梁保持，水面仍有天空照明和high预设的SSR。`render_scale`支持0.5–4，但当前保留1，不以降分辨率作为默认。

实际客户端F-16/F-22各600帧移动飞行实测均值23.45/23.39FPS，1%低帧17.37/17.29FPS。记录在`D:/bvr_sim_resources/iteration-cache/map-quality-v275/live-native-v356/report.json`，包含逐帧耗时、typed飞控输入、核心推进、飞机存活、GPU贴地读回和截图；保留其他GPU任务。这是短时数据，尚未稳定30FPS，也不保证长时间稳定。固定相机另见`material-cache-v355/report.json`（约23.6–28.1FPS）。

八/十六工作线程、降低内部比例、单级阴影和额外静态实例缓存均未显示可靠的实际飞行收益，未作为默认。缓存实验源码及失败/性能记录保留在D盘迭代目录，默认模块未使用该实验。离线美术草案v339/v340未发布，游戏仍直接加载v326烘焙文件。
