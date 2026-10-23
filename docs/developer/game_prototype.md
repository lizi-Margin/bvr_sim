# Single-player air-combat game implementation

The content-rich Alpha supersedes the first map and presentation below. See
[the current recipe, Agent CLI and validation workflow](../../game/README.md).
The v2 map is baked offline; runtime consumes hashed multi-resolution terrain
and shared scenery resources. Historical prototype evidence remains documented
below and must not be confused with the current 50 km mission validation.

The requested end state is a playable sortie loop: aircraft/loadout selection,
mouse flight control, sensor-based air combat, basic bombing, mission result,
and another sortie. Simulation must also run without rendering. This document
tracks implementation evidence; passing an intermediate gate is not completion.

## Validated first prototype

See [build, controls, resources and agent commands](../../game/README.md).
Run `python game/tools/validate_game.py --render` from the checkout root.
Validation was completed on 2026-10-23 with the local Release modules, not an
installed older native extension. Evidence is under `game/captures/validation`.

- [x] C++ radar/missile engagement, bomb strike, reset, seeded IDs and precise stepping: 8 tests.
- [x] Core builds with native viewers disabled. PE dependency inspection has no D3D/DXGI/OpenGL DLLs.
- [x] Wicked Engine DX12 fixed scene and direct backbuffer capture; zero shader errors.
- [x] Hangar, aircraft/loadout selection, sortie, pause, debrief and re-sortie; input/UI acceptance.
- [x] Mouse input changes actual aircraft flight; following camera, free look and zoom.
- [x] Sensor contacts and typed events drive HUD, lock, ammunition, warnings and mission feedback.
- [x] Air, strike and combined missions succeed on the same saved map.
- [x] F16 uses its own converted geometry and completes an input-driven interception.
- [x] Resource search/download/conversion/registration/placement was executed against real providers.
- [x] CLI/API supports reset, seed, stepping, camera, reload and tick-tagged GPU capture.
- [x] 1080p low/medium/high frame timings, screenshots and combat JSON are recorded.
- [x] Native 42 tests, RL adapter 3 tests, game input 2 tests, legacy viewer-disabled and HTTP/WebSocket smoke pass.
- [x] Both README languages and detailed build/config/architecture/resource instructions are updated.

All final `GameFrame` fields match exactly between headless and rendered runs for
air/strike/combined missions. The acceptance pilot uses real sensor locks and
weapon releases; it does not directly kill targets or move render objects.

## API boundary

`gameplay/GameSession` owns synchronous simulation stepping. Commands are queued
and applied before a named tick; renderers receive copied frames and do not
access mutable simulation objects. `GameFrame.entities` is world render/debug
state, while `GameFrame.contacts` contains player sensor observations for HUD
use. Telemetry is not created by the game session. Only one game session per
process is supported by the existing global simulation pools.

`GameTerrain` is available without a renderer. Bomb physics and its predicted
impact point use the same integrator. Terrain height sampling uses the exact
triangle diagonal/planes of the render mesh. The saved map has 16,384 cells and
hills surrounding a flat mission corridor. Map inspection validates depot/runway
height, asset hashes, face budgets and a registered barrier's ground placement.
FlightGear assets remain visual assets;
their external simulation/animation data are not presumed compatible.

## Deliberate first-version limits

Aircraft parts use static flight poses, with preserved XML animation inventories.
Missile/bomb meshes and effects are simple; the map has limited scenery detail.
The barrier is decorative; terrain and the depot implement gameplay collision.
There is no cockpit, audio or landing workflow. Performance is measured for this
small training scene and is not a large-map/battle performance claim. These are
documented prototype limits rather than unimplemented requirements of the first
air/ground sortie loop.
