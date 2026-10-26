# Flight Operations content-rich Alpha

2026-10-26: eight published maps now average above30 FPS on the measured High
1080p F16 routes, with remaining short stalls in dense woodland. The optional
`Launch-Regional-Horizon.cmd` opens the new2048km shared-terrain candidate.
See [map performance, exact conditions and limitations](MAP_PERFORMANCE.md).
The regional launcher displays a cancellable loading window before importing
native code. Large-map startup currently takes about one minute on this machine.
Confirming a sortie on the resident map reuses it without re-reading the package.

The current default is `game/maps/training_range_v2/generated-map.json`: a seeded
20 x 20 km focus region with 50 m height samples, a 512 km coarse surround,
airport, two villages, industry, river, irregular fields and clustered forests.
It contains 8,171 instances in 363 one-kilometre chunks. Shared mesh/material
entities and two scenery LODs replace repeated model imports. Chunks are resident;
asynchronous streaming is not implemented. This is a stylized procedural range,
not a surveyed real location. Generic scenery dimensions are engineering estimates.
Land-use edges fade into the coarse regional palette over a roughly 3.3–5.7 km
feather. Per-cell color tints are interpolated across mesh vertices, and the
renderer adds distance haze beyond 40 km so distant ridges meet the sky softly.
The latest inspected horizon views are in the game-map-improvement-validation
output's `after/horizon-refinement` folder.

Default air combat starts at 50 km with live enemy weapons and basic evasions.
The launch envelope uses the missile's motor/drag model; Rtr is an estimate, not
a guaranteed no-escape zone. `GameSession`, the renderer and CCIP use the same
versioned height arrays and triangle interpolation. Coordinates are metres in
north/west/up; Wicked receives `(-west, up, north)`.

## Recipe and Agent workflow

Install the optional offline tools with `python -m pip install -e ".[game]"`.
`setup_game.py` now also prepares the four Kenney packs, five ambientCG surfaces,
the curated scenery catalog/LODs, authored audio and the baked map. The explicit
Blender default is `C:/Program Files (x86)/Steam/steamapps/common/Blender/blender.exe`.
Use `--legacy-only` for the first prototype's setup. Components were validated
individually; a clean machine bootstrap has not been tested.

```powershell
python -m bvr_game.agent asset search kenney tree
python -m bvr_game.agent asset fetch kenney nature-kit
python -m bvr_game.agent asset fetch ambientcg Ground072 --resolution 1k
python -m bvr_game.agent asset fetch polyhaven concrete_road_barrier_02 --resolution 1k
python -m bvr_game.agent asset register
python -m bvr_game.agent asset inspect tree_oak
python -m bvr_game.agent map recipe create --seed 7 --name my_range --output game/recipes/my_range.json
python -m bvr_game.agent map build --recipe game/recipes/my_range.json --output game/maps/my_range
python -m bvr_game.agent map validate --map game/maps/my_range/generated-map.json --output game/maps/my_range/check.json
python -m bvr_game.agent map inspect --point -2500 -3500
python -m bvr_game.agent map inspect --point -2500 -3500 --render-height
python -m bvr_game.agent map capture --output game/captures/map
python -m bvr_game.agent map benchmark --frames 600 --output game/captures/benchmark
```

Edit declarations in the recipe rather than placing individual trees. Baking
uses cached resources and fails on hash drift. Runtime neither downloads nor
converts assets. Add an independently reviewed scenery GLB with
`asset register --spec path/to/spec.json`; the spec declares `id`, `source`,
`provider_manifest`, `height_m`, tags/use/density/collision, and optional width/depth.
Provider evidence and input hashes are required. Current generic registration
accepts CC0 only, verifies Kenney source against its archive, creates two LODs,
and refuses existing IDs. Use a new version ID when changing an asset. Aircraft
retain their dedicated conversion path and source geometry. `traffic_sign` was
actually registered through this extension path without changing the generator.

```powershell
python -m bvr_game.agent game run --state game/captures/sortie.json --mission air
python -m bvr_game.agent game step --state game/captures/sortie.json --ticks 10 --command '{"lock":true,"target_uid":"bandit"}'
python -m bvr_game.agent game query --state game/captures/sortie.json
python -m bvr_game.agent game pause --state game/captures/sortie.json
python -m bvr_game.agent game step --state game/captures/sortie.json --ticks 1 --exact
python -m bvr_game.agent game camera --state game/captures/sortie.json --eye 0 8508 -20033 --target 0 8502 -19976 --fov 1
python -m bvr_game.agent game capture --state game/captures/sortie.json --output game/captures/agent
```

Saved CLI sorties replay a typed input tape; they are not persistent servers.
Queries and captures do not advance simulation. For high-frequency control,
use `FlightGame`/native `GameSession` directly. Use `game pause --no-paused` to
resume. State files pin the map hash. Camera coordinates are Wicked coordinates.

`bvr_game/geography.py` defines the offline WGS84/local projection and verified
elevation/vector import contract. Real DEM/imagery downloads, GeoTIFF reprojection
and WorldCover/imagery rendering are future adapters; none are claimed in this map.

## Alpha validation

```powershell
python -m unittest discover -s scripts/tests -p test_world_content.py -v
python game/tools/validate_game.py --render
python game/tools/validate_alpha.py after --output PATH_TO_EVIDENCE
python game/tools/validate_alpha.py headless --output PATH_TO_EVIDENCE
python game/tools/validate_scene_gpu.py PATH_TO_EVIDENCE
python game/tools/validate_alpha.py performance --output PATH_TO_EVIDENCE
python game/tools/validate_alpha.py miss --output PATH_TO_EVIDENCE
```

`validate_alpha.py before` additionally requires the archived first renderer,
baseline map and explicit presentation adapter prepared for this local run.
The controlled pairs share current simulation/input/camera; they compare old/new
presentation. Historical unadapted captures are separate. Do not describe them
as identical historical gameplay runs. Review every final image visually.

F-22 is available for local use from the existing package, but separate mesh and
texture redistribution coverage remains unconfirmed (`distribution_allowed=false`).
F-16 requires retaining its GPL/source/notices. Do not bulk-distribute FlightGear
packages based on the simulator's license alone. Scenery is CC0 with per-file
evidence; generated placeholder audio is GPL-3.0-or-later. Audio playback was
exercised through real air/strike events; subjective mix quality is unreviewed.

The sections below retain the original client's controls/build details. The
older placement examples target the v1 map; use recipes for v2 content.

Run all commands from the repository root (the folder containing `pyproject.toml`).
The game is an optional Windows DX12 client. The simulation and training package
remain usable without it. Tested here with Windows, Python 3.14.4, VS 2022,
Blender 5.2.3 LTS, Ryzen 5950X and RTX 2080 Ti. The optional tools require Python
3.10 or newer and the existing bvr_sim Python dependencies. CMake and a Windows
SDK/MSVC installation are needed to build native modules.

## Launch and controls

After setup:

```powershell
python -m bvr_game play
python -m bvr_game play --aircraft F16 --mission strike --quality high
```

The hangar supports aircraft (`1` F-22, `2` F-16), mission (`M`), loadout (`L`),
AI weapons (`G`) and quality (`Q`). Enter or the sortie button starts the flight.

| Input | Action |
|---|---|
| Mouse | Command heading and climb through the real bvr_sim flight controller |
| Mouse wheel | Increase / decrease throttle (5 percentage points per notch) |
| W / S | Push down / pull up elevator override; release restores mouse aim |
| A / D | Manual aileron assistance |
| Hold C | Free observation; stop changing the pilot's aim while held |
| Hold right mouse | Zoom |
| R / Tab | Select a detected radar contact and request lock |
| V | Select AIM-120C7 or Mk-82 |
| Space / left mouse | Launch the selected missile (Space also releases the selected bomb) |
| B | Release Mk-82 |
| P / period | Pause / advance one exact simulation tick |
| F12 | Direct GPU capture with state/camera/asset metadata |
| Esc | Return to hangar; Esc again exits |
| Enter at debrief | Reset and fly another sortie |

Air missions finish when the opponent is destroyed; strike missions require the
depot, combined missions require both. The depot is a known mission objective.
Red aircraft labels and radar marks come from sensor observations. The bombing
cross uses the same ballistics and terrain sampler as the bomb. Controls do not
teleport render objects. AI weapons are live by default; turn them off with G
for unopposed practice. HUD speed is total simulated velocity, not calibrated IAS.

## Build and acquire assets

Wicked Engine is pinned to `fb6aaa4e79fd6861697f1e52d604d1e23404d594`.
The AC3D importer used in this validation is
[NikolaiVChr/Blender-AC3D](https://github.com/NikolaiVChr/Blender-AC3D), commit
`cf7fc194c547bc96486dc1c5147371e642143037`.
Provide its checkout/archive root (containing `io_scene_ac3d`). No global
Blender preferences or add-on installation are needed.

```powershell
python game/tools/setup_game.py `
  --engine-root ../work/WickedEngine `
  --engine-build ../work/wicked_build `
  --aircraft-root ../work/flightgear_samples `
  --addon-root "C:/Users/hulc/Documents/Codex/2026-10-23/https-www-bilibili-com-video-bv1uunv6zevb/outputs/asset-library-prototype/third_party/Blender-AC3D"
```

The setup script checks the engine revision, builds it, builds a simulation-only
core and the optional renderer module, converts the two reviewed aircraft,
downloads/converts a Poly Haven barrier and downloads ambientCG runway/grass
materials. Missing aircraft packages are fetched over the configured passwordless
SSH mirror. The F-16 archive is about 509 MiB; allow corresponding download/disk
space. `--skip-build` repeats asset preparation against existing binaries.
`--blender` and `--cmake` override executable locations. The first renderer
startup compiles/caches shaders and takes longer than later launches.

The equivalent simulation-only build, with no D3D/OpenGL/X11 linkage, is:

```powershell
cmake -S bvr_sim -B bvr_sim/build -A x64 `
  -DBVR_SIM_BUILD_NATIVE_VIEWERS=OFF `
  -DBVR_SIM_BUILD_TESTS=ON -DBVR_SIM_ENABLE_NATIVE_OPTIMIZATIONS=OFF `
  -DPYBIND11_FINDPYTHON=ON "-DPython3_EXECUTABLE=$((Get-Command python).Source)"
cmake --build bvr_sim/build --config Release --target bvr_sim_cpp bvr_sim_unit_tests --parallel 4
```

The old native viewers remain available with the build option ON (its compatibility
default). Wicked is built separately and never linked into the simulation module.
`game/runtime.json` stores local paths; assets and binaries are ignored by Git.
The game currently runs from the source checkout. When importing its package
elsewhere, set `BVR_GAME_ROOT` to this checkout's `game` directory.

## Agent resource pipeline

```powershell
python game/tools/asset_library.py search aircraft f16
python game/tools/asset_library.py search polyhaven "road barrier" --kind model
python game/tools/asset_library.py fetch polyhaven concrete_road_barrier_02 --resolution 1k
python game/tools/assets.py register road_barrier `
  --entry game/assets/cache/polyhaven/concrete_road_barrier_02/concrete_road_barrier_02_1k.gltf `
  --manifest game/assets/cache/polyhaven/concrete_road_barrier_02/manifest.json
python game/tools/assets.py inspect road_barrier
python game/tools/inspect_map.py
python game/tools/assets.py place road_barrier --name another_barrier --position 6040 25 0
python game/tools/asset_library.py fetch ambientcg Asphalt033 --resolution 1k
```

Provider manifests retain URLs, licenses and SHA-256. Registered geometry adds
dimensions in meters, reviewed axes, node names, face counts, Blender version and
conversion recipes. Aircraft conversion also preserves XML animation definitions
in an inventory. Geometry is static in the flight pose; dynamic gear/control
surface/XML animation playback is not implemented. Each new aircraft needs a
reviewed recipe; the library does not pretend all 664 archive packages work.
Missing, changed or unregistered models produce explicit errors. F16 always uses
its own geometry. There is no automatic aircraft substitution.

The map is `game/maps/training.json`; `--map` selects another saved configuration.
Its height field and object positions feed simulation and rendering. Seeded
surface fields provide motion cues. `python game/tools/build_training_map.py`
rebuilds the 129x129 saved height field (16,384 cells, surrounding hills up to
1,048 m, with a flat mission corridor). Terrain and the depot participate in gameplay
collision/damage; the barrier and surface scenery are decorative. The first map
is a fixed training range, not a terrain streaming/world generation system.

Powered by [Poly Haven](https://polyhaven.com/our-api). Barrier geometry is CC0;
[ambientCG](https://ambientcg.com/view?id=Asphalt033) runway material and
[Grass001](https://ambientcg.com/view?id=Grass001) terrain material are CC0. Aircraft
retain their FlightGear package/model notices (GPL-2.0 notices in these packages).
See each generated manifest and original package for asset-specific provenance.
FlightGear geometry is used for presentation; flight and weapons use bvr_sim's
existing models, not automatically imported FlightGear aerodynamic/XML logic.

## Agent simulation and GPU capture

Watch the local Agent fly a complete armed three-wave patrol:

```powershell
python -m bvr_game.autoplay --aircraft F16 --seed 101 --speed 4
python -m bvr_game.autoplay --aircraft F16 --seed 101 --speed 10 --video
python -m bvr_game.autoplay --headless --aircraft F22 --seed 101
python -m bvr_game.autoplay --map-version river-valley-v56@a12eae9e6ca6eff76e7eed27 --aircraft F16
```

Space pauses/resumes the Agent; Escape or closing the window stops the run.
The Agent uses copied own state, radar contacts, weapon inventory and cockpit
warnings. It makes tactical decisions every 0.5 simulation seconds. The default
55-second interval between confirmed launches avoids spending a second radar
missile just before the first one arrives. This remains a local scripted pilot;
F-22 survival and general success are not guaranteed.

Each attempt creates a fresh `game/captures/autoplay-...` directory with its
result, decisions, captures and links to the normal ACMI/core/input journals.
`--video` records the actual GPU backbuffer at 10 fps in simulation time; requested
live speed depends on GPU/encoding performance. `--seconds N` limits a run and
reports an unfinished mission honestly. `--output PATH` requires a new directory
so earlier failed attempts cannot be overwritten. Replay a journal with:

```powershell
python -m bvr_game.playtest replay SORTIE_DIRECTORY/input-tape.json --output game/captures/autoplay-replay
```

`--map FILE` selects an explicit baked map; `--map-version ID` validates and loads
a published version from the map catalog. The patrol still uses its 8500 m combat
altitude. For map performance at lower altitudes, run the serial moving-flight check:

```powershell
python game/tools/benchmark_map_flights.py --seconds 20 --output work/my-map-flight-check
```

This flies F-16 at 850 m and 2400 m MSL on every published map at 1080p High,
using the normal client's real-time simulation accumulator, HUD and logs. Each
phase has a 20-second measurement window after warmup. Raw frame times, 1% low,
P95/P99, captures, map weather and hardware context are saved per map. Loading,
warmup, screenshots and video encoding are excluded from FPS. Saved map weather
is retained, so cloud/shadow differences contribute to the observed comparison.

```powershell
python -m bvr_game run --mission air
python -m bvr_game run --mission strike --render --hidden --output game/captures/strike
python -m bvr_game run --mission combined --render --hidden
python -m bvr_game benchmark --hidden --frames 300 --quality medium
python game/tools/capture_scene.py
```

The acceptance pilot discovers a real sensor contact, requests lock/fire, or flies
until the ballistic prediction reaches the depot and releases a bomb. These are
repeatable verification missions, separate from the interactive player loop.
Outputs include mission JSON, events, screenshots and capture metadata. Capture
retains the backbuffer rendered before Present advances the swapchain index.
There is no desktop screenshot or screen-click requirement.

```python
from bvr_game.app import FlightGame
game = FlightGame(render=True, visible=False)
try:
    game.config.seed = 7
    game.start()
    game.sim.set_paused(True)
    game.command(heading=0.2, pitch=0.05, throttle=0.9)
    game.sim.step_exact(50)
    frame = game.sim.frame()   # typed entities, contacts, pylons, events, tick
    game.set_camera([20,3010,-30], [0,3000,20], fov=1.05)
    game.draw()
    game.capture("inspection")
    game.renderer.reload()    # reload dynamic model instances
finally:
    game.close()
```

One process owns one game simulation because the existing core uses global pools.
One renderer lifetime per process is supported. A mutex serializes stepping,
command submission and snapshot queries; commands apply at a numbered tick
boundary. Frames are value copies. No game operation needs TelemetryBridge,
debug-register commands, a web server or a renderer; telemetry remains available
to existing SimCore clients as an optional external channel.

## Validation

```powershell
npm.cmd --prefix bvr_sim/web ci --no-audit --no-fund
python game/tools/validate_game.py --render
```

This covers native tests, Python RL adapters, legacy viewer-disabled behavior,
HTTP/WebSocket telemetry, real A/A and A/G integration, mouse/menu input, repeat
sorties, and exact final-state comparison for render-enabled vs headless runs of
all three missions. UI acceptance drives the same input handler as the window
and captures the F16 flight/debrief/hangar flow.

Performance JSON records 1920x1080 low/medium/high results on this machine.
The benchmark includes one simulation tick and rendering per measured frame,
after warm-up; it excludes asset conversion, shader compilation and capture.
It is a small training scene with two aircraft and simple scenery, not a claim about
large battle/map performance. See `game/captures/validation/checks.json` and each
`benchmark_*/benchmark.json` for the current measured evidence.

This is a playable first prototype. Remaining visual limitations include the
limited map detail, old source aircraft art, static aircraft parts, simple missile/bomb
meshes, simple engine/impact effects and no cockpit/audio/landing workflow.


## Multi-aircraft and ground Alpha

The ordinary hangar now uses one catalog for F22/F16/F15/F18/F4N, clickable and scrollable selection, legal loadouts, real preview meshes and repeat sorties. The v3 recipe adds a 5 m industrial sample, shared physical bridge/contact data, core-driven Jeep routes and a real SLAMRAAM convoy mission. See [build, Agent commands, recipes and approximations](docs/multi-aircraft-ground-alpha.md) for the current workflow and verification commands. Run game/Launch-Game.cmd for the v3 map.

The same hangar also includes all 147 imported FlightGear aircraft as unarmed
training flights (152 entries including the five combat configurations). Use the
mouse wheel/arrows or Page Up/Down to browse; click the search field or press `/`,
type an aircraft name/ID, then Enter to finish searching. Click a card and Enter
to fly. Source FDM backend and host-assist limitations remain visible. Aircraft
without validated combat integration do not receive invented weapons or radar.

Mouse pitch uses the full aiming rectangle for ±45° climb-angle assist. W pushes
down and S pulls up through a direct normalized elevator override; releasing
them returns to mouse assist. Pure pitch input does not invoke automatic inverted
roll. A/D and horizontal mouse sensitivity are unchanged. The dedicated radar
range/azimuth panel and RWR/SA ring are displayed simultaneously.

## Visual / Agent beta

The current main client adds an armed three-wave Intercept Patrol, resident typed
Agent host, reproducible input tapes, physical sky/aerial perspective, repeating
terrain detail and F22/F16 material approximations. Every formal departure records
real core ACMI/logs; F9 opens the current/previous sortie folder in Explorer.
See [controls, logging, evaluation, replay and visual recipes](docs/visual-agent-beta.md)
for commands, observation boundaries and known approximations. Existing tasks and
all 147 imported training entries remain in the same 152-entry searchable hangar.
