# Agent 资源入口

从仓库根目录运行。下载、Blender 转换和注册均为离线步骤；游戏只加载已注册且哈希匹配的资源。

```powershell
python game/tools/asset_library.py search polyhaven pine --kind model
python game/tools/asset_library.py fetch polyhaven pine_sapling_small --resolution 1k --max-mb 40
python game/tools/assets.py register pine_sapling_source --entry game/assets/cache/polyhaven/pine_sapling_small/pine_sapling_small_1k.gltf --manifest game/assets/cache/polyhaven/pine_sapling_small/manifest.json --recipe game/recipes/pine_sapling_lod.json
python game/tools/assets.py inspect pine_sapling_source
python game/tools/assets.py register pine_grove_a --entry game/assets/cache/polyhaven/pine_sapling_small/pine_sapling_small_1k.gltf --manifest game/assets/cache/polyhaven/pine_sapling_small/manifest.json --recipe game/recipes/pine_cluster_lod.json
python game/tools/assets.py inspect pine_grove_a
python game/tools/asset_library.py fetch polyhaven fir_tree_01 --resolution 1k --max-mb 500
python game/tools/assets.py register fir_grove_c --entry game/assets/cache/polyhaven/fir_tree_01/fir_tree_01_1k.gltf --manifest game/assets/cache/polyhaven/fir_tree_01/manifest.json --recipe game/recipes/fir_cluster_lod.json
python game/tools/assets.py inspect fir_grove_c
python game/tools/assets.py register fir_grove_cards_c --entry game/assets/cache/polyhaven/fir_tree_01/fir_tree_01_1k.gltf --manifest game/assets/cache/polyhaven/fir_tree_01/manifest.json --recipe game/recipes/fir_cluster_cards_lod.json
python game/tools/assets.py inspect fir_grove_cards_c
python game/tools/build_river_valley_recipe.py --bake
python -m bvr_game.mapcheck --map game/maps/river_valley_airfield/generated-map.json --output game/captures/river-valley-map-check.json
```

默认 Blender 路径为本机 Steam 安装位置；`register --blender` 可覆盖。下载器计算完整依赖大小后才下载，逐文件验证源 MD5，并在 manifest 保存 SHA256；转换时再次检查全部依赖。注册检查近景及每个 LOD 的文件哈希。地图配方声明 `asset_roles`，Baker 读取注册目录的尺寸、LOD 和来源，批量放置、分块并保存资源版本。

松树配方选择源包的 `pine_sapling_small_a`，统一缩放到明确的 7m 景观树，近景简化到 8000 三角形。远景由同一源模型烘焙三张垂直视图与一张顶视图，组合为一个共享网格、8 三角形的 alpha-test LOD。远景是形状和着色的工程近似，尚需通过运动和 LOD 切换验收；源树苗缩放不等于真实树龄或植物生长模拟。

资源来自 [Poly Haven Pine Sapling Small](https://polyhaven.com/a/pine_sapling_small)，适用其 [CC0 资产许可](https://polyhaven.com/license)。源图片、几何、转换参数、Blender 版本和衍生文件哈希保存在 `game/assets/registered/pine_sapling_source/manifest.json`。未修改飞机源几何，也未使用战争雷霆解包资产。

`pine_grove_a` 将 16 棵同一源松树以固定 seed、明确缩放和间距组合为共享的 64000/8 三角形近远景资源。地图逐组拟合局部地形平面，拒绝超过 0.2rad 倾角或 0.25m 源复制基准点误差的放置，最后再对最终共享高度数据复核；不压平地形。源复制基准点是归一化包围盒的底部参考点，尚不等于每个树皮顶点，不能据此宣称精确的植物碰撞。

林地宏观材质还可声明 `canopy_proxy`：将同一源树丛的顶视反照率与透明度在直线光空间中按地图像素足迹过滤，再以固定旋转层混入林地底色。配方冻结顶视文件哈希，材质报告记录来源及覆盖率。这是没有冠层高度、立体阴影或逐树对应关系的远景地面代理；不计入三维树木数量，也不能代替近景和运动验收。新图仍处于候选验证阶段。

当前河谷配方默认使用 `fir_grove_cards_c`；`--forest-asset pine_grove_a` 或 `--forest-asset fir_grove_c` 可复现早期候选。冷杉选择真实源包的 `fir_tree_01_c_LOD0`，保留原米制尺寸，再按配方复制成 16 棵一组。直接整体减面版本的近景丢失大量细叶，已保留为失败候选。卡片版本保留简化的三维源木质几何，每棵树的叶冠使用从原始叶材质单独烘焙的透明视图；近远景为 92480/8 三角形。远景视图先从完整源几何以 CPU Cycles 烘焙反照率和透明度，再制作近景近似。源底部 0.03m 内几何顶点测得的锚点保存在注册元数据中，用于坡地拟合。叶片卡片没有完整叶片体积，阴影和转动效果仍需运动验收。取回的完整 1k 源依赖约 487MB，不能只按入口 glTF 的大小估计下载量。

`game/assets/cache/`、`game/assets/registered/` 和生成地图目录不入 Git；上述命令用于重新获取和生成。构建地图先写独立暂存目录，验证完毕后发布不可变版本，最后原子更新入口 JSON。失败暂存和旧版本保留供诊断。

## 飞机源部件与材质

F-16 的原始外形导入不含独立 XML 引用的座舱和飞行员。当前转换配方在保留原有外形的同时，加入同一源包的 `Models/pilot_externalview.ac` 和 `Models/Cockpit/Main/cockpit.ac`。转换器核对 `Models/F-16.xml` 中唯一对应的模型声明，只接受本例的零偏移；存在非零子模型变换时会报错，需使用完整 XML 导入流程，不能猜测摆放位置。它没有递归实现内部仪表系统。GPL 原始通知继续保留，manifest 保存每个新增源文件、源 XML、声明 XML 与转换器哈希。

本机复现已注册配方：

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --python-exit-code 1 --python game/tools/convert_aircraft.py -- game/assets/registered/F16/recipe.json
python game/tools/enrich_inventory.py
python game/tools/audit_aircraft_surface.py --output NEW_AIRCRAFT_AUDIT
python game/tools/prepare_player_visuals.py
python game/tools/capture_aircraft_surfaces.py --output NEW_AIRCRAFT_VIEWS
```

原有 F-16 的 102 个绘制部分，其位置、索引、法线、UV、节点变换和源贴图已与新增部件前逐项核对；新增后为 184 个绘制部分、95122 个三角形，原版本为 15869 个三角形。新增部件有实际渲染开销，最终性能测试必须包含。显式 runtime 配方中的已注册飞机变体通过 manifest/文件哈希验证后优先保留，目录展开只补充未指定的飞机。

日光配置的 `canopy_color` 是线性 RGB 色调，`canopy_alpha` 为薄层 alpha 混合不透明度；当前不使用屏幕空间透射模糊。源 F-16 透明度为 0 的内层不参与深度、高光或阴影，避免两层玻璃产生噪点。F-22 外部贴图可用 `f22_paint_knee`、`f22_paint_shoulder`、`f22_paint_floor` 调整局部线性反照率映射，保留原 UV 和源图像。这些是工程外观近似，不是实测玻璃/隐身涂层 BRDF，也不能把旧漫反射贴图称为完整 PBR。旧源图的粗面板线仍是可见限制。

## 逐树法线与河面反射候选

`fir_grove_normal_a` 选择原始 `fir_tree_01_a_LOD0`，以固定 seed 保留 64 棵树的位置，近远景为 32512/512 三角形，各只有一个共享网格。源颜色/透明度与 `fir_grove_individual_a` 的八张逐树颜色图像素一致，网格位置、索引、法线与 UV 也一致。新增法线由真实源几何投影到各卡片的切线坐标系，用 Raw 线性 RGB 烘焙；它不把固定方向的光照烘进颜色图。注册 manifest 明确启用 `view_facing_alpha` 后，渲染器仅对 `source_impostor_*` 材质应用视角透明度衰减，深度和颜色通道使用同一条件。法线仍不能补回完整叶冠体积。

```powershell
python game/tools/assets.py register fir_grove_normal_a --entry game/assets/cache/polyhaven/fir_tree_01/fir_tree_01_1k.gltf --manifest game/assets/cache/polyhaven/fir_tree_01/manifest.json --recipe game/recipes/fir_grove_normal_a.json
python game/tools/prepare_player_visuals.py
python game/tools/build_river_valley_recipe.py --forest-asset fir_grove_normal_a --recipe-output NEW_RECIPE.json --bake --output NEW_MAP_DIRECTORY
python game/tools/validate_grove_render.py --map NEW_MAP_DIRECTORY/generated-map.json --output NEW_RENDER_DIRECTORY --orbit-frames 180
```

渲染源码改变后先结束自己启动的验证进程并重建 `bvr_game_render`，再运行验证。环绕录像是暂停场景的 18 秒相机检查，不是实际飞行或性能测试。

配方的 `landscape.water_render_chunk_m=500` 将长河面的原有三角形分批，保持全部位置、索引展开顺序及共享地形不变。固定版本对比为 1→338 个水面批次，实际最大批次长约 475.07m。引擎按最近水面对象的包围盒中心取反射平面，当前低空测试点由错误的 169.43m 改为 120.094m；可通过只读 `renderer.reflection_plane()` 取得真实渲染读数，无可见反射面时返回 `None`。

这仍是未通过自然画面验收的候选：树林存在卡片感、重复团块与平面地表代理；河面高视角出现条纹。独立 shader 诊断中，关闭反射后条纹仍在，关闭折射后消失，后续需继续定位折射采样和实际河床表达。诊断配置不作为正式质量配置；默认地图未切换。

后续同机位诊断已定位并修正条纹：直接显示折射采样的颜色没有条纹，显示计算水深则复现条纹。原着色器将 mip2 邻域深度搜索的结果继续取最大值用于最终衰减，但这些粗深度来自邻近屏幕射线；现在粗搜索仍用于折射 UV 选择，最终衰减仅使用选定 UV 的完整分辨率深度。修复由 `prepare_player_visuals.py` 生成到本地 shader 缓存，未改第三方源码。反射、折射都保留；实际高视角条纹已消失。同一裁剪区的行亮度二阶差分降至原来的约 6.34%，仅作为该条纹的局部诊断，不能代表整体画质。地图仍是贴地约 0.025m 的浅层水面，俯视过于透明，河床、岸线和自然树林仍未验收。

## 连续外围地表与材质候选

现有 Baker 可生成覆盖完整 512km 外围的世界坐标宏观地表，并把 20km 细节区的边缘混合到同一外围纹理。材质来自已注册 CC0 草地、土壤、岩石和树冠反照率；新覆盖是固定 seed 的编写场景，不是卫星、GIS 或实测农田数据。当前 4096 纹理对应外围约 125m/像素，近景细节仍由原来的米级源贴图提供，远处地块清晰度仍有限。

```powershell
python game/tools/build_river_valley_recipe.py --retexture-map game/maps/river_valley_airfield/generated-map.json --outer-cover --output game/maps/river_valley_outer_cover
```

`--retexture-map` 使用原不可变版本的配方，只重新烘焙材质，校验高度 NPZ、全部实例、路面、碰撞环境、任务与注册模型版本完全一致。它接受根指针或具体版本路径；默认把候选配方写入候选目录，避免覆盖原配方。完整新场景也可用原来的 `--bake --outer-cover`，继续走同一个 Baker。`landscape.outer_surface` 记录分辨率、地块和林地尺度；该字段缺省时保留旧流程。

原生渲染器支持可选外围材质；旧地图保持原来的材质接口。外围材质元数据不会传进核心高度结构。新版本发布前验证全部依赖，重复烘焙得到同一版本时不重写已有版本文件，只原子发布根指针。首次使用需重建 `bvr_game_render`，缺少接口的旧模块会给出明确错误。

外围覆盖消除了旧焦点区域的明显矩形颜色中断，但不能因此宣布自然地景完成：近景树林仍稀疏、树冠代理平面化，农田边界规整，河面与岸线缺少可信深度。当前候选保留原地图作为默认，完整画面与性能验收尚未完成。

## 共享河床与独立水面候选

```powershell
python game/tools/build_river_valley_recipe.py --bake --outer-cover --river-channel --recipe-output NEW_DIRECTORY/scene-recipe.json --output NEW_DIRECTORY
python game/tools/validate_player_ccip.py --river-case --map NEW_DIRECTORY/generated-map.json --output NEW_CCIP_DIRECTORY
```

`--river-channel` 必须完整烘焙，不能与只改材质的 `--retexture-map` 合用。它把设计深度 4m、岸宽 22m、岸脊 0.8m 的横截面写入同一份高度 NPZ；全部高度分辨率调用相同规则，区域边界仍接回原有 BVR 地形。水面在重点河段使用配方的河流水位，外围平滑接回原有粗地形水面。核心、显示与 CCIP 继续读取烘焙后的共享三角网格，不在渲染端临时挖沟。

河床和裸露岸边使用已注册土壤源材质，水色与吸收采用明确记录的工程参数，不代表实测水质或测深。`--river-case` 增加一次真实河道投弹，并要求实际落点位于河道、低于水面至少 1m，且 CCIP 与核心接触误差均不超过 0.1m。现有核心仍将航弹积分到共享河床；本轮不增加流体阻力、浮力或触水引爆。

当前实际网格横截面中心深度约 3.994–4.000m，25m 区域网格的插值解释了与设计值的微小差异。完整新场景会按相同 seed 重新执行地形约束的摆放规则，因此不能声称所有实例坐标、环境或核心帧与旧地图相同；用新地图自己的输入带验证 headless/render 重放。均匀河宽、岸线细节、稀疏树林与大田块仍是画质限制，默认地图暂不切换。

## 逐树远景与林下地面候选

```powershell
python game/tools/build_river_valley_recipe.py --bake --outer-cover --river-channel --forest-asset fir_grove_normal_a --forest-floor-only --recipe-output NEW_DIRECTORY/scene-recipe.json --output NEW_DIRECTORY
```

`fir_grove_normal_a` 是已注册真实源树的副本，远景保留每棵树的三维位置、源反照率、透明度与法线卡片；每簇 64 棵，远景 512 三角形。它仍是可见性与轮廓近似，不能称为完整枝叶几何。`--forest-floor-only` 让已注册林下地面材质直接留在树下，不再把顶视树冠预览投到地上；它要求逐树远景资源与完整烘焙，不能搭配只改材质的 `--retexture-map`。旧地图和旧资源保持原来的流程。

林簇接地支持批量查询同一套三角网格插值，避免对每棵源树反复执行 Python 标量采样。旧标量入口保留用于比较；真实源林簇的完整倾斜、接受/拒绝、接地误差和全部根部坐标须一致。批量化只加速离线摆放，不改变地形、实时核心或 GPU 的物理判定，也不能用离线耗时作为游戏帧率证据。

地图检查对明确声明 `inter_grove_stem_spacing_m` 的源林簇，允许树冠包围圆相交，并改查实际缩放、偏航、地形倾斜后的源树干间距；普通资源仍检查包围圆。水面、道路、禁建区和资源哈希检查继续生效。检测覆盖全部源树干，保留实际冲突距离；合成用例同时验证合法的树冠相交和错误的树干过近。独立 GPU 根部变换检查用于核对离线矩阵，不能只凭生成器自己的拟合结果宣布接地正确。当前装饰林簇仍允许约 0.25m 的根部拟合误差，它与物理接触面的 0.1m 验收是不同检查。

## 导入飞机的源排气资料

```powershell
python -m bvr_game.exhaust_profiles build
python -m bvr_game.exhaust_profiles validate
python -m bvr_game.exhaust_profiles show FG-A-10
python -m bvr_game.exhaust_profiles show FG-F22
```

生成器读取已导入的 FDM、引用的发动机文件及其哈希，生成 `game/config/aircraft_exhaust_profiles.json`，供 `player_daylight.json` 相对路径引用。`prepare_player_visuals.py` 也会重建这份资料并保存其哈希。它不改 FDM、发动机参数、源模型或原有机库目录。当前覆盖 147 项导入外观：源 YASim 明确声明加力推力且提供归一化 `REHEAT` 输出时使用 `property`；未声明加力的发动机为 `disabled`；缺少源定义或当前快照状态的情况为 `unavailable`，不会推断成真实发动机没有加力。

运行时只消费已有 `GameEntity.animation_properties`。例如 FG-F22 的 `engines/engine[0]/afterburner` 与第二台发动机的对应输出包含源模型自身的过渡时间；效果不再仅按油门超过 35% 开启。A-10 的两台源发动机未声明加力，因而不会生成这种发光几何。缺少或非有限的输出不会启用效果。普通 F22/F16 仍保留单独的旧油门效果，它不属于此次导入外观策略，也不能称为真实加力遥测。

Agent 可调用 `renderer.aircraft_exhaust_state()` 获取 typed 状态，包含机体 UID、发动机索引、模式、属性、属性是否可用、显示强度及可见性；`aircraft_statistics()` 另区分附件数、实际效果几何数与活动效果数。这些是表现层诊断，不决定推力、温度或燃油消耗。附件位置仍沿用原注册资料的几何测量或投影近似；缺少显式发动机索引时按附件顺序关联，并在状态中标记近似。发光形状、颜色与强度不是测量所得的排气光谱或热场，仍需逐机型画面复核。旧视觉配置未引用这份资料时保留原排气路径。

## 道路方向田块与均匀林区候选

```powershell
python game/tools/build_river_valley_recipe.py --bake --outer-cover --river-channel --forest-asset fir_grove_normal_a --forest-floor-only --rural-layout --recipe-output NEW_DIRECTORY/scene-recipe.json --output NEW_DIRECTORY
```

`--rural-layout` 使用完整烘焙，并要求 `--forest-floor-only`；它改变田块与装饰植物摆放，不能用于仅重烘焙材质的 `--retexture-map`。田块在现有道路、河流、林区、机场和乡镇排除区域内递归切分，参考附近道路方向，坡地倾向于较小地块。地块共享边界和 T 形连接，耕作纹理跟随各自长轴，边界保留 4m 的源草地过渡。固定私有 RNG 保证布局复现，同时不消耗建筑等其他生成器的随机序列。`rural_parcels.area_range_m2` 是递归停止阈值的采样范围，切分、坡度和排除区可产生小于其下界的地块，不能把它解释为每块田的严格面积范围。

林簇继续使用原源树、数量预算、尺度、LOD 和视距，中心改为按林区面积均匀采样；实际接地拒绝仍可能使最终簇数略有差别。林下宏观颜色使用真实源材质的线性均值，独立的 3m 运行时地面细节保留，避免把米级源林下斑块放大到 160m。布局与农作物覆盖均为工程创作，不是 GIS、实测农业或树种密度资料。

当前候选有 5,123 块田、10,078 个源林簇，比旧候选多 9 簇。所有高度数组、道路/接触面和障碍物均与旧图相同；土地覆盖、颜色与装饰实例数据变化，因此高度 NPZ 整体哈希不同，必须固定新的不可变版本进行重放。均匀分布减少了大空洞，但源簇的重复圆团轮廓仍明显，森林尚未通过自然画面验收；默认地图与主启动入口暂不切换。

## 源树卡片的双面法线

`prepare_player_visuals.py` 在项目自己的 shader 缓存中修正已注册 `source_impostor_*` 树卡片的背面切线基，不修改 Wicked 上游。源法线描述的是投影到卡片上的树体；从卡片背后观察时，镜像其深度分量，保留纹理横向和纵向分量，避免把向上的枝叶法线翻成向下。普通材质继续使用引擎原双面处理，源图片、源几何、透明度、深度与物理数据保持。它仍是镜像已烘焙视图的近似，不能恢复真实树的背面几何。

日间配方的 `source_card_full_rgb_normals` 为明确声明源法线烘焙视图的卡片保留原 PNG 的三个线性通道。渲染器用独立共享的 RGBA8 资源加载这些图片，避免 BC5 丢弃蓝通道；shader 读取完整 RGB 向量，其他材质保留原 RG 路径。源图中一个像素可能平均了多个表面法线，向量长度不是 1，因此不能仅从 RG 推算 `sqrt(1-x*x-y*y)`。旧资源未声明源法线视图时保留原路径，声明了却缺失图片时明确报错。`renderer.source_card_materials()` 返回实际资源格式、尺寸、mipmap 数量和 `rgb_preserved`，可直接核对 GPU 资源。当前源林簇 8 张共享 RGBA 法线图的 texel/mipmap 大小约 42.7MiB，另有 GPU 分配和缓存开销；不能用这个大小冒充显存总量或性能验收。

```powershell
python game/tools/prepare_player_visuals.py
python game/tools/validate_vegetation_lighting.py --map PATH_TO_IMMUTABLE_MAP.json --visual-profile game/recipes/player_daylight.json --output NEW_INSPECTION_DIRECTORY
```

检查工具把一簇未修改的真实源树放在空中，暂停物理时间，以相同光照、相机和强制近/远 LOD 检查树卡片，隔离地形接触和地面阴影的影响；这不是地图或性能验收。`--classify-normals` 只用于显式输出红/绿法线诊断色的独立 shader，`--expect-up` 只用于已知向上向量的专用探针。真实源法线包含向下的枝叶，不能要求它们全部向上。正常光照下的改变主要是局部受光方向，平均明暗变化很小；森林过暗、重复圆团与最终自然画面仍需要独立处理。

`--normal-error-probe --split-rgb-probe --expect-rgb-match` 仅用于专用 GPU 对照：左半实际执行旧 RG 解码，右半执行 RGB 解码，两者共用同一原始 RGBA 纹理、真实模型和相机，再与完整源向量比较，绿色为误差不超过 1°。这些诊断 shader 保存在验证目录，不写入正常配方。`capture_player_visuals.py --visual-profile PATH_TO_CANDIDATE.json` 也可直接检查独立视觉候选。曾隔离关闭树卡片接收阴影，亮度仅增加约 8%，不能解释或解决全部远景过暗；正常配置继续保留阴影。

## 源树逐树接地候选

`game/recipes/fir_grove_conform_a.json` 复用同一株真实源杉树和已注册的原始烘焙图片，将 64 株树的工程布局摊到 50m 半径。转换前检查源文件、原注册 GLB、外部 PNG 与 GLB 内嵌 PNG 的哈希。UV0 继续用于源贴图，UV1 存放每株树的源底部锚点；近远 LOD 使用一致的锚点。布局不是实测林区数据，卡片不是完整树冠几何。

带 `ground_conform` 的资源要求地图声明 `terrain.ground_atlas`，包括原高度归档版本、R32 文件哈希、网格原点/间距/行列数。`BakedScene` 检查版本与文件后，通过 `renderer.configure_ground_atlas()` 上传连续 float32 数组。Atlas 按核心地形的相同三角形对角线插值，不能用双线性过滤替代。它只供装饰树读取；核心高度、道路接触面、水域、碰撞和 CCIP 继续使用原环境。原地图不声明 atlas 时保持原路径。

项目拥有的 `game/shaders/bvrGroundHF.hlsli` 同时服务颜色、预深度、阴影顶点和 GPU 回读；`surfaceHF` 的静态三角形预载也采用相同位移，供深度重建及运动矢量使用。该候选只支持直立、静态、无骨骼/风动的源树与 indexed raster 路径，不支持未变形的 meshlet 或光追几何。每帧在引擎场景更新后修正 CPU 包围盒；独立 GPU 实例副本再批量更新实例包围球，避免写入引擎已提交的上传内存。新增 atlas 和实例副本的显存与复制开销需要单独计入完整地图性能，不能把小场景验证当作性能达标。

```powershell
python game/tools/prepare_player_visuals.py
python game/tools/build_grounded_grove_probe.py --map PATH_TO_IMMUTABLE_MAP.json --output NEW_PROBE_DIRECTORY
python game/tools/validate_grounded_vegetation.py --map NEW_PROBE_DIRECTORY/generated-map.json --output NEW_GPU_INSPECTION_DIRECTORY --orbit-frames 180
```

`renderer.gpu_ground_heights()` 直接回读 GPU atlas 采样。`renderer.scenery_ground_vertices(id, all_vertices=True)` 使用实际 draw instance/geometry/material/packed-position/UV 缓冲区，回读变形顶点、源底部、深度重建位置、静态上一帧位置和 GPU 实例包围球；它是共用顶点例程的 compute 检查，不是光栅后 stream-output 捕获，也不是物理碰撞验证。

隔离探针检查了 12,222 个 GPU 高度点，以及三种朝向/尺度、近远 LOD 的 83,904 个顶点。早期固定 64 树簇摊宽后，整簇拒绝采样在局部林区只接受 160/200 簇；该失败 staging 与日志保留。

后续 `fir_grove_stream_a.json` 使用 UV1 源树索引和 `ScenePlacement.ground_stems` 绝对北/西坐标流，先独立采样树位，再按空间分批复用同一网格。每批最多 64 树、轴向跨度不超过 250m；不足 64 树的槽位在各光栅路径收缩为零面积三角形，GPU 检查同时回读活动标记。v50c 候选包含 652,800 株实际源树、10,290 批，保留原配方目标；相对 v46 实际 644,992 株增加约 1.21%。全部树位通过空间校验，另检查 8 批的近远 LOD GPU 顶点；这不代表逐株完成全部 GPU 验证。`build_river_valley_recipe.py --rebuild-forest-map PATH` 可复用已有地图的地形、材质、接触面、任务和普通摆件，仅重建森林；旧地图缺少 atlas 时从共享高度数据生成。

继承的 shader 二进制曾记录上游 include 路径，导致计算探针通过但实际阴影仍使用旧树位。`prepare_player_visuals.py` 改用空起点的 `shaders-owned-source-v1` 缓存，仅从项目拥有的源码编译；旧缓存保留为失败证据。此前依据源码和计算回读作出的完整阴影路径判断已被此发现取代，新缓存另有实际单树画面及依赖来源检查。

候选已有约 195 秒实际渲染重放，390 个核心边界状态与原路线逐项一致。森林硬边、远景自然程度和完整地图性能仍未验收，默认地图和启动入口尚未切换。

独立树位重建可加 `--forest-edge-width-m 160`：在原林区边界内，以共享平滑噪声调制约 160m 的密度过渡，保留少量稀疏边缘树；总树量、道路/建筑避让和树干间距继续完整校验。v51 仍有 652,800 株树，地形数组、接触面、任务、普通摆件和实际地表贴图均保留。此参数改变工程生成的树位，不是实测生态分布；原棕色林地底色和远景色块仍需处理。

山坡上的 GPU 检查工具会读取共享核心高度，令诊断相机离地至少 45m，并在到检查目标的 65 个视线样点上保留至少 3m 净空。旧版绕行镜头按树簇根点高度飞行，可能钻入地表；其计算顶点结果仍有效，穿地录像不能用于画面验收。净空采样也不等于连续遮挡证明，实际近远 LOD 画面仍须复核。

已有渐变树位的地图可单独重烘焙地表，让森林边缘的草地与源森林地表共用同一密度场：

```powershell
python game/tools/build_river_valley_recipe.py --retexture-map SOURCE_IMMUTABLE_MAP.json --forest-floor-transition --output NEW_CANDIDATE_DIRECTORY --recipe-output CANDIDATE_RECIPE.json
```

源配方的每条 canopy 规则须已声明 `edge_density`，并采用没有 `canopy_proxy` 的源地表。该操作冻结全部树位、普通摆件、地形数组、接触面、任务和资源版本；颜色在线性光下混合，法线和粗糙度采用相同互补权重及现有模糊核。道路、工业区和河床标签继续优先，模糊仍作用于相邻材质边界。密度场按64行分块计算，不在运行时增加纹理或着色步骤。

v52 对照重烘焙逐字节复现 v51 的实际贴图；开启过渡只改变区域地表贴图内森林及有限高斯核覆盖范围。实际近景中，稀疏林缘下的棕色带已与草地衔接；这仍是工程地表近似，远处树冠色块、树卡片和整张地图的自然程度尚未验收。对照版本与早期过小的局部变化审计范围失败样本均保留。

## 源树卡片的面积 mip 候选

原 PNG 导入路径会在下一层 mip 取四个子像素的最大 alpha；当前压缩 albedo 实际有9级，末级为4×4。杉树源图平均 alpha 约6%–10%，最大值链到4×4时已扩为约25%–50%；完整11级的最大值诊断链到1×1则为100%。这会放大远景卡片的不透明覆盖，不能将其当作真实冠幅。源树稀疏透明分支在线性光下生成颜色 mip、按面积平均 alpha，更适合当前开启TAA的软覆盖路径。

```powershell
python game/tools/assets.py mip-variant fir_grove_stream_area_a --source fir_grove_stream_a
python game/tools/assets.py inspect fir_grove_stream_area_a
python game/tools/build_river_valley_recipe.py --replace-forest-map SOURCE_IMMUTABLE_MAP.json --forest-asset fir_grove_stream_area_a --output NEW_CANDIDATE_DIRECTORY --recipe-output CANDIDATE_RECIPE.json
```

新变体保留全部 GLB 字节和 mip0 RGBA 字节，附带带哈希的完整 DDS 链。颜色使用线性光、alpha加权平均，法线保持线性编码向量平均；alpha为面积平均。`BakedScene` 在载入前校验 sidecar 路径与SHA，原生端验证尺寸/级数/颜色空间，并通过只读材质状态报告实际资源与格式。旧资源保持原路径；新变体要求已重建的renderer和完整RGB源法线配置。替换工具仅接受 GLB、源锚点与包围盒完全相同的资源，保存新地图版本并冻结全部树位与物理环境。

`--maximum-alpha-control` 只用于负对照：与面积版本每级RGB、法线DDS、mip0、纹理格式和级数相同，仅albedo低级alpha不同。另有保留alpha/法线、仅改为编码RGB过滤的私有诊断，不能当作正常资源。完整地图实际对照保留652,800株树、相同视距及输入三角形量；面积版本减弱了远处实心色块。原引擎基线还与DDS对照存在压缩、级数和法线过滤差别，不能把全部改善只归因于一个alpha开关。

该候选采用未压缩RGBA8 DDS，按唯一纹理估算比原压缩albedo增加约32MiB GPU纹理数据，实际预算与性能仍需最终地图测量。硬alpha-test、关闭TAA、跨视角卡片及完整动态自然度尚未验收；面积平均也不等于多张交叉卡片光学厚度的准确积分。默认地图和启动入口未切换。

卡片与真实源树的视角误差可用现有注册资源直接审计：

```powershell
& 'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe' --background --python-exit-code 1 --python game/tools/audit_vegetation_views.py -- --asset fir_grove_stream_a --output NEW_AUDIT_DIRECTORY
```

工具先验证源文件依赖及注册GLB内嵌图像，再复用同一组源烘焙图，不重画树形。固定正交相机分别渲染真实源几何、交叉卡片及采用当前朝向alpha权重的卡片，共6组仰角/方位、18张无光照RGBA图。输出包含相机、来源、工具哈希和渐进报告；不会修改注册库、地图或默认入口。它使用Cycles的独立透明路径，不是Wicked/TAA、远距mip、阴影、运行性能或最终森林画面的验收。

v54实际对照确认现有资产已有顶视图。30°–70°斜俯视同时存在漏失和多出轮廓，70°朝向加权卡片的alpha积分约为真实源树的80%，垂直顶视则接近100%。因此面积mip与逐树噪声相位只能处理采样问题，不能恢复缺失的斜向形状；后续视角表示应对照真实源几何改进，不能用增加树量或统一增大alpha代替。逐树相位仍为隔离的诊断候选，未写入默认shader。

## 透明边框裁切与资源版本

```powershell
python game/tools/assets.py mip-variant fir_grove_stream_crop_area_a --source fir_grove_stream_a --crop-transparent
python game/tools/build_river_valley_recipe.py --replace-forest-map ORIGINAL_RESOURCE_IMMUTABLE_MAP.json --forest-asset fir_grove_stream_crop_area_a --output NEW_CANDIDATE_DIRECTORY --recipe-output NEW_CANDIDATE_RECIPE.json
```

该派生用颜色/法线alpha并集和8px边框，选择包含全部非零alpha的最小二次幂矩形。保留原始RGBA子矩形，不重采样、不提高alpha、不重画树形；调整卡片顶点，使对应源像素仍处于原有空间位置。当前侧视图为512×1024、顶视图512×512，完整矩形mip链由现有DDS工具生成。材质法线、UV0、UV1树索引、索引、木质几何、树位/姿态及原保守边界保留。只改变透明支撑面的范围和纹理采样网格，原斜向形状限制仍在。

替换工具会从原始注册GLB独立重算裁切，不能只靠新manifest中的SHA通过验证。现有杉树DDS文件数据从89,480,832降到39,149,216字节，源卡片支撑面总面积为原来的43.75%；这些是文件/几何数据，不能直接称为实测显存或FPS收益。5cm顶点修改即使同步更新manifest里的GLB哈希，仍会被独立派生校验拒绝。

新烘焙、森林重建及替换配方会把外置mip资源的manifest SHA写进resource_versions，运行时同时校验manifest及其DDS哈希。此前不可变替换候选已有source_card_resource_swap.registered_manifest_sha256，加载器继续使用其冻结值；移除mip声明也不能绕过它。没有冻结manifest版本的早期外置mip诊断地图需生成新版本，普通GLB地图的读取保持原有行为。

离线源树转换现在允许配方声明impostor_aerial_views（方位/仰角，度）。它生成真实源几何的额外无光照颜色和RGB法线，原四张验证过的图可以逐字节复用；尚无方向采样器时，额外视图只能离线审计，不能把所有平面直接叠入游戏。v55的45°/70°两圈、每圈8个方位仅存于独立work原型，未注册为运行资源。实际六组对照显示：简单最近视图在70°明显改善，但部分低角度更差；沿源twig面积重心调整深度也不足以解决，尚未通过连续视角验收。
