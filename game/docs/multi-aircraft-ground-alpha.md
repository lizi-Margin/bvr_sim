# Multi-aircraft and ground Alpha

The ordinary hangar reads `bvr_sim/resources/aircraft_catalog.json`. It contains
F22, F16, F15, F18 and F4N. Click cards, scroll or use 1–5; L cycles legal loadouts,
M cycles supported missions, Enter starts a sortie and Escape returns to the hangar.
Each switch/reset reuses shared GPU meshes and materials. The same menu now also
includes all 147 entries from `imported_aircraft_catalog.json`, for 152 selectable
configurations. Imported aircraft use their source JSBSim/YASim backend with host
assist and unarmed training missions. They are not certified combat integrations.
Click the search field or press `/`, type an ID/name, Enter to finish searching,
then select a card and Enter to fly. Page Up/Down and Home/End support long lists.
The CLI and Agent can select imported IDs such as `FG-737-800` in the same flow.

Mouse pitch maps the actual aiming rectangle to ±45° climb-angle commands; W pushes down, S pulls up. W/S
override the elevator through `PilotCommand.manual_pitch` and `pitch_input`
(positive pull/up). Release returns to mouse assist. A/D and horizontal mouse
sensitivity are unchanged. Pure pitch input suppresses the heading assistant's
inverted-roll maneuver. Aircraft NWU pitch is negative nose-up; renderer rotation
uses that sign directly, while terrain/vehicle slope pitch retains its convention.
`Renderer.entity_forward(uid)` exposes the actual rendered forward direction for
Agent visual-state checks. The independent forward RADAR range/azimuth panel is
visible alongside the RWR/SA ring; it draws only onboard sensor contacts.
Imported JSBSim models also receive their declared external normalized
FlightGear stick/throttle inputs (including `controls/flight/elevator-sum`).
Only exact standard input aliases are mapped; trims, fault flags and internal
system outputs are not overwritten. This host adapter does not run source Nasal
or replace each aircraft's electrical/hydraulic/system simulation.

F15 uses a FlightGear F-15C exterior and has an air-to-air configuration. F18 uses
a Canadian Hornet exterior and the repository's existing JSBSim Hornet data,
which retains F-16-derived references. F4N uses its existing JSBSim model and the
F-16 controller; its exterior is a generic FlightGear F-4, **not verified F-4N
geometry**. It supports Mk-82 rather than an invented AIM-120 capability.
The heading pilot oscillates on the existing F18 strike controller. Its bomb
qualification uses neutral manual aileron on the declared straight approach.
The common radar and weapon station capacities are game approximations recorded
in the catalog. These are response-tested controllers, not independent real-aircraft calibrations.

## Build and start

Build the simulator before importing its native module. The renderer must be built
against the same snapshot headers. Close loading Python/game processes first.
Keep `BVR_SIM_BUILD_NATIVE_VIEWERS=OFF` for the core-only configuration; it does
not require Wicked Engine, a window or a GPU.

```powershell
cmake --build bvr_sim/build --config Release --target bvr_sim_cpp --parallel 4
cmake --build game/build --config Release --parallel 4
python -m bvr_game.worldgen --recipe game/recipes/training_range_v3.json --output game/maps/training_range_v3
python -m bvr_game play --map game/maps/training_range_v3/generated-map.json --aircraft F18 --loadout mixed --quality high
```

Blender is used offline at
`C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe`.
No Blender, network request, source-folder scan or conversion happens in a flight frame.

## Agent commands

Typed `GameSession`, `GameConfig`, `PilotCommand`, `GameFrame`, `GroundUnitSpec`
and `VehicleRoute` are the formal in-process interface. The CLI records commands
in an input tape and reconstructs the same session; it does not use screen clicks.

```powershell
python -m bvr_game.agent aircraft list
python -m bvr_game.agent aircraft inspect F4N
python -m bvr_game.agent game run --aircraft F22 --loadout mixed --mission convoy --state sortie.json --map game/maps/training_range_v3/generated-map.json
python -m bvr_game.agent game pause --state sortie.json
python -m bvr_game.agent game step --state sortie.json --exact --ticks 50 --command '{"heading":0,"throttle":0.85}'
python -m bvr_game.agent ground list --state sortie.json
python -m bvr_game.agent ground park convoy_1 --state sortie.json
python -m bvr_game.agent ground park convoy_1 --no-parked --state sortie.json
python -m bvr_game.agent ground spawn --state sortie.json --spec vehicle.json
python -m bvr_game.agent ground route convoy_1 --state sortie.json --route route.json
python -m bvr_game.agent game camera --state sortie.json --eye -4400 200 3980 --target -4480 182 4000
python -m bvr_game.agent game capture --state sortie.json --output game/captures/agent
python -m bvr_game.agent map inspect --map game/maps/training_range_v3/generated-map.json --point 2850 970 --render-height
```

`--reference-height` selects a reachable lower or upper contact layer. Queries
distinguish raw terrain, drivable contact triangles and collision roof approximations.
Rendering interpolates its actual uploaded mesh vertices independently for parity checks.

A vehicle spec uses metres in north/west/up coordinates:

```json
{"uid":"car","model":"WillysJeep","kind":"vehicle","team":"blue",
 "position":[4000,4300,180],"mission_target":false,
 "route":{"points":[[4000,4300],[4000,4650],[4310,4650]],"speed":7,"loop":false}}
```

## Resource and map recipes

Use `asset search/fetch/inspect/register` through `python -m bvr_game.agent`.
Kenney, ambientCG and Poly Haven provider data retain source URLs, license evidence
and hashes. Generic scenery registration accepts reviewed GLB/glTF recipes with a
size calibration and generates two shared LODs. Register another model and name it
in `asset_roles`; a replacement does not require scene-generator changes.
The Jeep converter is `game/tools/convert_vehicle.py`, with its source graph and
license evidence in `game/assets/cache/ground-jeep/recipe.json`.
Aircraft use the separate FlightGear graph converter and keep local-only distribution
status when source permissions/dependencies have not been cleared.

`training_range_v3.json` adds a 2×2 km, 5 m industrial sample inside the original
20 km focus and 512 km outer terrain. It evaluates analytic height rules and adds
independent ridges/gullies; only the boundary band blends to the old grid. The
industrial pad remains graded while surrounding hills keep relief. An offline
2048² PBR blend smooths land-use boundaries and retains source normal/roughness detail.
Internal service roads, clear entrances, resource-role replacements and clustered
woodland are declarations. The bridge has a separate deck, ramps, piers and guard
rails above the unchanged riverbed.

Important buildings and fences use source-derived oriented collision boxes;
drivable surfaces use the same triangles as rendering. Vegetation and most small
props are explicitly decorative. Box roofs do not claim exact architectural
mesh collision. Roads outside the sample retain 50 m terrain limitations.

## Core ownership and approximations

`simulator/environment.*` owns terrain, triangle contact surfaces, water, oriented
obstacles and LOS. `simulator/bomb/mk82.*` owns Mk-82 integration, prediction,
collision and damage. `simulator/ground/vehicle.*` owns route motion, acceleration,
braking, yaw limits, slope/contact attitude, obstacle/water blocking and reset.
GameSession only adapts commands, declares spawns and scores real core outcomes.

Vehicles use a kinematic follower and a conservative 2.1 m footprint, without tire,
suspension or armor simulation. The Jeep mesh is Detlef Faber's FlightGear model.
SLAMRAAM has a core range/LOS sensor, original firing gates/magazine and real
AIM-120 objects; its displayed launcher is an explicitly schematic proxy.
Aircraft ground strikes and bombs consume the shared core environment. Existing
missile speed/damage and Mk-82 constants remain unchanged.

## Reproduce acceptance

```powershell
cmake --build bvr_sim/build --config Release --target bvr_sim_unit_tests --parallel 4
bvr_sim/build/Release/bvr_sim_unit_tests.exe
python -m pytest scripts/tests/test_bvr_sim_rl.py scripts/tests/test_game_session.py scripts/tests/test_flight_game.py scripts/tests/test_ground_game.py scripts/tests/test_world_content.py -q
python game/tools/validate_multi_aircraft.py --output OUTPUT
python game/tools/validate_ground_routes.py --output OUTPUT
python game/tools/validate_ground_alpha.py scenery --output OUTPUT
python game/tools/validate_ground_alpha.py matrix --output OUTPUT
python game/tools/validate_ground_alpha.py replay --output OUTPUT
python game/tools/validate_ground_alpha.py performance --output OUTPUT
```

Copy the fixed camera declarations into `OUTPUT/maps/fixed-cameras.json` first.
Run GPU validations sequentially; Wicked owns one global device/scene per process.
Use a separate process for each renderer lifetime. Run performance with Blender,
conversion, FDM batches and other GPU tests stopped. Keep concurrent measurements
as evidence rather than mixing them into isolated results.
The final review reports actual per-profile results, visual limitations and any
remaining acceptance failures; successful builds alone do not establish visual quality.
