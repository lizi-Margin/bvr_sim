# Agent 资源入口

从仓库根目录运行。下载、Blender 转换和注册均为离线步骤；游戏只加载已注册且哈希匹配的资源。

```powershell
python game/tools/asset_library.py search polyhaven pine --kind model
python game/tools/asset_library.py fetch polyhaven pine_sapling_small --resolution 1k --max-mb 40
python game/tools/assets.py register pine_sapling_source --entry game/assets/cache/polyhaven/pine_sapling_small/pine_sapling_small_1k.gltf --manifest game/assets/cache/polyhaven/pine_sapling_small/manifest.json --recipe game/recipes/pine_sapling_lod.json
python game/tools/assets.py inspect pine_sapling_source
python game/tools/build_river_valley_recipe.py --bake
python -m bvr_game.mapcheck --map game/maps/river_valley_airfield/generated-map.json --output game/captures/river-valley-map-check.json
```

默认 Blender 路径为本机 Steam 安装位置；`register --blender` 可覆盖。下载器计算完整依赖大小后才下载，逐文件验证源 MD5，并在 manifest 保存 SHA256；转换时再次检查全部依赖。注册检查近景及每个 LOD 的文件哈希。地图配方声明 `asset_roles`，Baker 读取注册目录的尺寸、LOD 和来源，批量放置、分块并保存资源版本。

松树配方选择源包的 `pine_sapling_small_a`，统一缩放到明确的 7m 景观树，近景简化到 8000 三角形。远景由同一源模型烘焙三张垂直视图与一张顶视图，组合为一个共享网格、8 三角形的 alpha-test LOD。远景是形状和着色的工程近似，尚需通过运动和 LOD 切换验收；源树苗缩放不等于真实树龄或植物生长模拟。

资源来自 [Poly Haven Pine Sapling Small](https://polyhaven.com/a/pine_sapling_small)，适用其 [CC0 资产许可](https://polyhaven.com/license)。源图片、几何、转换参数、Blender 版本和衍生文件哈希保存在 `game/assets/registered/pine_sapling_source/manifest.json`。未修改飞机源几何，也未使用战争雷霆解包资产。

`game/assets/cache/`、`game/assets/registered/` 和生成地图目录不入 Git；上述命令用于重新获取和生成。构建地图先写独立暂存目录，验证完毕后发布不可变版本，最后原子更新入口 JSON。失败暂存和旧版本保留供诊断。
