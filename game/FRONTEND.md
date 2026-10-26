# Native frontend

The ordinary `play` command opens a separate cancellable loading window before starting the game process. It closes after the first game frame is ready; direct module tools such as `run` remain headless or render-on-demand.

Run from the nested repository:

```powershell
python -m bvr_game play
# Explicitly select the UI build:
python -m bvr_game play --runtime game/runtime-ui.json
```

普通入口已包含地图画质候选。进入机库后点击战斗按钮，在“战斗准备 → 地图版本”选择“连续森林·远景优化 v326 [候选]”，再确认出击。当前画面按用户要求定型，优先保留可玩的帧率；该版本不支持车队任务，未宣称逐项达到参考画质。首次加载大地图需要等待。已经运行的客户端需要退出后重新启动，才会加载更新的原生模块。

游戏客户端在首次导入仿真绑定之前，按 `game/native-runtime.json` 的 SHA256 选择支持大地图的独立核心；两个普通 runtime 配方均选用配套渲染器。显式 `BVR_SIM_CPP_PATH` 覆盖和已嵌入的仿真模块保持原选择；直接导入 `bvr_sim` 的训练流程不读取此游戏配置。正在运行的 PYD/DLL 不被覆盖。旧的 `Launch-Map-Candidate.cmd` 现在也是普通入口的别名，选择新地图无需它。

完整森林使用直接64位像素图元标识的索引光栅和配套 compute visibility shading，避免原25位 meshlet 编号及全局查找表容量溢出。它与 `player_daylight.json` 声明的独立 shader 源码/缓存成对使用；模块与配置不匹配会拒绝启动。14,498,176个原树位置保留，近处使用源几何，远处使用源模型离线烘焙的简化几何，树木绘制距离无限。Mesh shader 与 path tracing 未启用。

All graphical `.cmd` entry points delegate to `Launch-Frontend.cmd`, which opens the cancellable loading window and selects `runtime-ui.json`; each profile keeps its own map, aircraft, and mission arguments. `Launch-Game.cmd` starts the F-22 training map, while `Launch-Regional-Horizon.cmd` starts the frozen F-16 regional map. Restart an existing client to load a new native module. Both default runtime recipes must reference a renderer built against the current core `GAME_API_ABI`; old renderer binaries are retained for their matching old cores, not mixed with new weapon snapshots. Tools constructing `FlightGame` directly use `runtime.json` unless given an explicit runtime.

The frozen 2026-10-26 profile is recorded in [releases/regional-horizon-v327-2026-10-26.json](releases/regional-horizon-v327-2026-10-26.json). Its native core and renderer binaries live under `D:/bvr_sim_resources/releases/regional-horizon-v327-20261026/` and are SHA256-pinned in the runtime/release records. Launch it with `game/Launch-Regional-Horizon.cmd`; map selection and mission preparation remain available in the hangar UI. The map is still catalogued as a candidate and does not support convoy missions.

The UI renderer loads the installed Windows font `%WINDIR%/Fonts/msyh.ttc` (Microsoft YaHei) before measuring or drawing text. The font is not redistributed. Chinese squares in an old process require a restart with the new renderer; changing the console encoding does not update its glyphs.

## Pages and controls

- Hangar: live registered aircraft, actual catalog specifications, orange battle button and country tabs. Click a country to expand its chronological aircraft tree; same-decade aircraft share rows in fighter, bomber/attack, trainer/experimental, civil/business and transport/support columns. Mouse wheel, arrow/Page keys and Home/End scroll the tree; Escape closes it. Click a family card to expand its distinct source variants, then click an aircraft to select its actual hangar model. `/` focuses search; if no match exists in the current country it moves to a matching country. The lower card strip follows the selected country and uses the same decade order. All 152 registered aircraft are reachable; imported aircraft keep their training-only restrictions.
- Settings: `F2`, or the top settings button. Quality, font scale, HUD visibility, mouse sensitivity, assisted/manual control and master volume affect the actual client. Apply validates and atomically persists settings in `%APPDATA%/bvr_sim/client-settings.json`. Cancel/Escape discards the draft. Controls lists the current bindings; rebinding is not implemented.
- Battle preparation: battle button or Enter opens a draft. Click a station on the aircraft schematic, choose compatible ammunition, optionally mirror it, or select a developer-authored preset. Select a supported mission, map version, enemy weapons and seed, then confirm (or Enter) to start the actual core session. Cancel preserves the prior configuration and complete paused core frame. Weapon/backend parameters and station definitions are not player-editable. See [WEAPON_LOADOUTS.md](WEAPON_LOADOUTS.md) for the typed core API and physical scope.

Settings and preparation dim and defocus the same 3D hangar. UI navigation does not advance physics. Aircraft data and weapon outcomes come from the current catalog and simulation; no fictional economy, research tree or aircraft performance is presented.

In flight, `V` cycles the actual remaining mounted weapon types. `Space` fires
the selected missile or releases the selected bomb; `B` releases a bomb directly.
HUD counts and missile labels follow the real weapon types. Both the client and
native renderer check `GAME_API_ABI` before combining a core and renderer module.

## Independent renderer rebuild

Use a **new output directory** so a running client or the parallel map task cannot load a file being replaced. The checkout already has the pinned Wicked source and Release static libraries. Example from the repository:

```powershell
$frontendBuild = '../work/ui_frontend/renderer-next'
& 'C:/Program Files/CMake/bin/cmake.exe' -S game/native -B $frontendBuild -A x64 '-DWICKED_SOURCE=C:/Users/hulc/Desktop/paper/bvr_sim/work/WickedEngine' '-DWICKED_BUILD=C:/Users/hulc/Desktop/paper/bvr_sim/work/wicked_build' '-DPython3_EXECUTABLE=C:/Users/hulc/AppData/Local/Programs/Python/Python314/python.exe'
& 'C:/Program Files/CMake/bin/cmake.exe' --build $frontendBuild --config Release --target bvr_game_render --parallel 4
# Only after a successful build, copy runtime-ui.json to a new runtime file and
# point renderer_module to the new build's absolute Release directory.
```

Inspect `renderer_module` in the selected runtime recipe for the current independent build. `cloud_profile.hxx` is shared with the map task; its optional profile fields leave existing weather defaults unchanged when absent. Hangar geometry is presentation-only and does not add simulation contacts.

## Thumbnails and verification

Every tree and carousel icon uses the pre-rendered PNG under `game/assets/ui/aircraft/`; cards do not render separate aircraft scenes. The native resource cache reuses textures. Only the selected aircraft is shown in the live hangar.

Historical metadata lives in `bvr_game/data/aircraft_history.json`, with per-entry source references and explicit policies. Country means design origin, not operator/livery. USSR and Russia remain separate; multinational programmes and fictional aircraft have explicit tabs. The Czech tab includes former Czechoslovakia. Decades approximate reference-family first flight, not a claim about every variant's development date; non-flying projects use documented design/exhibition decades and fictional designs have no historical date. Connections show role/time ordering, not unlock requirements or proven historical derivation. New unclassified resources appear under a fallback tab rather than being dropped; review metadata and run completeness checks when extending the catalog.

Export `aircraft_catalog(include_library=True)['aircraft']` from `bvr_game.aircraft` as UTF-8 JSON, then render the registered meshes with the installed Blender:

```powershell
python -c "import json; from pathlib import Path; from bvr_game.aircraft import aircraft_catalog; Path('../work/ui_frontend/aircraft-sources.json').write_text(json.dumps(aircraft_catalog(include_library=True)['aircraft']),encoding='utf8')"
& 'C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe' --background --python game/tools/render_menu_thumbnails.py -- ../work/ui_frontend/aircraft-sources.json game/assets/ui/aircraft
python -m unittest scripts.tests.test_aircraft_tree scripts.tests.test_frontend scripts.tests.test_flight_game scripts.tests.test_player_replay scripts.tests.test_map_library
python game/tools/validate_frontend.py --runtime game/runtime-ui.json --output ../work/ui_frontend/validation-new
python game/tools/validate_frontend_entry.py --output ../work/ui_frontend/entry-new
```

Validation output directories must be new. The thumbnail script records source and PNG hashes and reuses unchanged assets. Visual validation captures the actual DX12 backbuffer and invokes the client's input handlers with typed events. It does not inject OS hardware input or certify performance. The suite covers settings transactions, catalog restrictions, preparation, an actual lock/launch/hit/result and return to hangar. `validate_frontend_entry.py` separately checks the ordinary play CLI default and Chinese font rendering.

Verified captures and review: `C:/Users/hulc/Documents/Codex/2026-10-25/bvr-ui-reference/`. The hangar building and apron are a procedural approximation. Aircraft materials remain the registered FlightGear sources; this frontend work does not claim map-quality or aircraft-material parity with the reference game.
