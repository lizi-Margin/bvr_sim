# Weapons and per-station loadouts

Weapon and station definitions are developer-owned. The battle preparation page
only selects existing ammunition at compatible stations; it does not expose
simulation backends, parameter files or parameter editing.

- `bvr_sim/resources/weapon_catalog.json`: the shared weapon registry, including
  existing internal/legacy aliases and the player-selectable weapon IDs.
- `bvr_sim/resources/aircraft_stations.json`: station IDs, schematic coordinates,
  compatible single stores, mirrored stations and presets. Definitions are loaded
  by the simulator; Python and the preparation page consume its typed API.
- F-22: six main-bay missile positions and two Sidewinder side-bay positions.
  F-15: four fuselage AMRAAM positions and four wing missile rail positions.
  F-16: simplified stations 1–9, restricted by ammunition type in the catalog.
  F-18/F4N retain explicitly labelled experimental Alpha slots. Other imported
  aircraft remain unarmed. Diagram coordinates are not physical launch offsets.

Public layout references: [USAF F-22](https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104506/f-22-raptor/),
[USAF F-15](https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104501/f-15-eagle/),
[USAF F-16](https://www.af.mil/About-Us/Fact-Sheets/Display/Article/104505/f-16-fighting-falcon/).
The catalog is an initial simulation subset, not full real-world carriage certification.

## Agent use without the client or GameSession

```python
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as sim

catalog = sim.weapon_catalog()           # public weapon metadata, no backend/file fields
layout = sim.aircraft_stations('F16')
mounts = {'1': 'AIM-9M', '2': 'AIM-120C7', '3': 'Mk-82'}
assert sim.validate_loadout('F16', mounts) == []

core = sim.SimCore(.02, 'core-weapons.log', '', False)
core.reset_world(7)
own = sim.AircraftSpawnSpec()
own.uid = 'own'
own.model = 'F16'
own.loadout = mounts
core.spawn_aircraft(own)
target = sim.AircraftSpawnSpec()
target.uid = 'target'
target.team = 'red'
target.position = [3500, 0, 3000]
target.velocity = [-250, 0, 0]
core.spawn_aircraft(target)
core.step(10)
ready = core.check_launch('own', 'AIM-9M', 'target', '1')
if ready.allowed:
    assert core.launch_weapon('own', 'AIM-9M', 'target', '1')
core.step(200)
states = core.objects()                  # typed positions, pylons, missile outcomes
core.reset_world(7)
core.close()                            # stop, clear world and close recording/logs
```

Typed world access requires synchronous stepping. The existing simulator uses a
process-global object pool: use one world/session per process, with separate
processes for parallel evaluations. `reset_world` clears objects and resets seeds.

For game integration, set `GameConfig.use_station_loadout=True` and `loadout` to
the station map. An explicit empty map means unarmed. The old count-based fields
remain a compatibility path for existing scenarios; new UI sorties use stations.
`PilotCommand`/`PlayerFlightIntent` select `weapon` and optionally `station`.
`GameFrame` exposes per-type `weapon_counts`, `selected_weapon`, `launch_ready`
and `launch_reason`; entity pylons report actual remaining stores.

Mk-82 now enters through the same weapon registry and `WeaponFactory::create_bomb`.
Both the game and typed core use `release_bomb` for exact station consumption;
the game no longer constructs released bombs or removes their stores itself.
Agents can call `core.release_weapon('own', 'Mk-82', '3')`,
`core.predict_bomb_impact('own')`, `core.set_environment(terrain)` and
`core.spawn_ground(spec)` without a game session. Prediction and actual release
share the simulator-owned Mk-82 parameters, trajectory and terrain contact code.
The pre-existing Alpha drag, gravity and ground blast approximation are preserved.

## Current physical scope

Both missile backends retain their existing dynamics and damage parameters.
AIM-9 acquisition uses the existing model's geometric cone/range approximation,
without a radar-lock prerequisite. This does not model thermal signatures or
flare discrimination. AIM-120 retains the existing radar and approximate launch
zone behavior. Store mass, aerodynamic drag, station launch offsets, bay doors,
fuel tanks, multi-store adapters and rack geometry are not simulated in this phase.
Weapon construction precedes exact station consumption, so rejected/unknown
launches cannot remove ammunition. Legacy AI prefix queries resolve to an exact
mounted store before entering the same launch implementation.

Run `scripts/tests/test_weapon_loadouts.py`, `test_loadout_frontend.py` and
`game/tools/validate_weapon_loadouts.py` against a rebuilt native core.
The rendered validator drives the real client input handlers, records the exact
typed player intents they produce, and replays those intents into a headless run
before comparing complete core snapshots. Identical pointer coordinates alone
are insufficient for this comparison because camera transforms affect intent.

On Windows, configure `BVR_SIM_BUILD_NATIVE_VIEWERS=OFF` for a core-only build.
`BVR_SIM_ARTIFACT_DIRECTORY` optionally selects a new Release output directory
without rewriting a module already loaded by another agent. Point
`BVR_SIM_CPP_PATH` at that build's `bvr_sim_cpp*.pyd` for isolated validation.
Always rebuild/choose a renderer with matching `GAME_API_ABI` for DX12 tests.
