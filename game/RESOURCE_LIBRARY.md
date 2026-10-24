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
