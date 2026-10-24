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
