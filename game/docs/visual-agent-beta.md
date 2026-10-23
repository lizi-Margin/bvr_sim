# Visual / Agent beta

Start with `game/Launch-Game.cmd` (1920×1080 High, v3 map). The hangar retains
all 152 selectable configurations: five combat configurations and 147 imported
FlightGear training aircraft. Search with `/`, choose a card, Enter to fly. Source
meshes, FDM provenance and training-only limits are unchanged.

## Controls and sortie records

W pushes the nose down; S pulls up. Both held means neutral manual elevator.
Release returns to mouse assist. `PilotCommand.pitch_input > 0` still means pull
up; this is a client key mapping, not a reversed core contract. A/D and the F22/F16
horizontal mouse curve are unchanged. YASim uses the coordinated roll-rate input;
manual A/D has priority. The A-10 source's sole `sas-elevator` input is explicitly
mapped, retaining its source square response. No substring alias matching.

F9 opens the current sortie directory in Windows Explorer. In the hangar it opens
the previous sortie, or the root if no sortie has run. It does not step or pause.
Default: `game/logs/sorties/<local-time-microseconds>-<unique-id>/`. Set
`BVR_SORTIE_LOG_ROOT` to relocate it (spaces/Chinese paths supported).

Each formal departure writes `battle.acmi`, `core.log`, `sortie.json`, incrementally
flushed `input-tape.jsonl`, and finalized `input-tape.json`. Preview/reset/aircraft
selection do not start a formal record. Return, retry, result and normal close
flush and finish the current record. One-second core flush and buffered journal
writes reduce loss; this is not power-loss-proof fsync at every tick. Errors include
the actual path and cause. A partially interrupted JSONL can retain complete lines
although its final metadata may still say running.

The exporter lives in SimCore, using actual time, UID-to-hex mapping, WGS84 positions,
orientation and lifecycle. Aircraft, missiles, Mk-82 bombs and ground objects are
covered; destroyed objects emit removal records. This does not install Tacview or
include an in-game ACMI player. Coordinate/content validation is separate from file
existence. The client journal and Explorer operation never drive physics.

`FlightGame.log_paths()` / `ResidentPlaytest.game.log_paths()` return root, current
and recent. The normal Agent CLI also supports `python -m bvr_game.agent game logs`.

## Armed patrol and observation boundary

F22/F16 can choose Intercept Patrol: three armed inbound F16s at fixed 120-second
intervals, six existing AIM-120C7 rounds, 600-second timeout, three actual missile
kills and player survival required. Later waves are not unarmed practice targets.
Quick air/strike/combined/convoy/training missions remain available. M changes
mission, L loadout (fixed for the formal patrol), R/Tab lock, Space fire, Enter retry,
Escape hangar. Radar range/azimuth and RWR/SA remain separate simultaneous panels.

The patrol enemy's `AirTacticalPilot` receives copied own/radar/RWR/MWS data and
owns search, approach, launch, support, crank, defend and reacquisition states. It
cannot query a full world pointer. The older quick-task AI remains a compatibility
path and has older omniscient steering; it is not the honest patrol evaluator.

## Resident Agent and reproduction

One resident process owns one GameSession (the core still has global pools).
Use Python typed methods directly:

```python
from bvr_game.playtest import ResidentPlaytest, LocalCombatPilot
host = ResidentPlaytest('game/captures/resident', render=False)
try:
    observation = host.reset(seed=101, model='F22')
    pilot = LocalCombatPilot(101)
    while observation.mission['result'] == 'running':
        observation = host.step(25, pilot.command(observation))
finally:
    host.close()
```

`observe()` returns copied own state, actual radar contacts, local warning bearings
(and range only when localized), ammunition and public mission progress. The
player policy receives no full entities or hidden missile energy/coordinates.
`diagnostics()` is separately privileged and returns full GameFrame and log paths.
No screen clicks, TelemetryBridge, debug-register parsing or LLM key is required.

```powershell
python -m bvr_game.playtest serve --output game/captures/resident
python -m bvr_game.playtest batch --output game/captures/evaluation --candidate trial-1
python -m bvr_game.playtest replay INPUT-TAPE --output game/captures/replay --render
python -m bvr_game.playtest replay INPUT-TAPE --output game/captures/failure --render --video --window-start 65 --window-end 90
```

`serve` is an optional JSONL boundary around the same typed host, not the official
simulation representation. Actions: reset, observe, step, pause, diagnose, logs,
camera, capture and close. Fixed core dt is .02 s; default tactical decisions are
25 ticks (.5 s). `step(..., exact=True)` advances while paused. Batch workers each
reuse a resident session, with process isolation between cores. `--worker-timeout` defaults to 600 wall seconds per owned batch worker; timeout
records retain partial journals and diagnostics;
the mission's deterministic 600-second timeout remains authoritative.

Reports retain every result, full-frame SHA at .5 s endpoints, five-second and
warning-transition full snapshots, local observations, events, input tapes, source/
core/scenario hashes and sortie log paths. Replay compares complete serialized
GameFrames at every recorded endpoint; optional video splits only the stepping
partition, then verifies the same endpoints. `--video-sample-ticks 25` gives a 5×
time-lapse at 10 fps; default 5 gives actual simulation playback speed.

`game/recipes/intercept_patrol.json` freezes the scoring, resources and seed sets.
The initial evaluation alternates odd F22/even F16 across 20 seeds; independent
holdouts use the same model assignment. It is not a 20-per-model benchmark.
This session's Codex examines evidence, edits the policy and reruns candidates.
The executable policy is a reusable local tactical policy, not a background LLM
that rewrites itself. No hidden-state access, weapon retuning, enemy nerfs, forced
kills, score changes or failed-sample deletion are used for improvement.

## Rendering profile and reproducible resources

`python game/tools/prepare_visual_beta.py` prepares `game/recipes/visual_beta.json`
from the pinned Wicked revision and existing registered ambientCG Ground072 CC0
maps. It copies shader sources into an isolated cache, keeps upstream untouched,
and invalidates modified binaries. Runtime never downloads assets or runs Blender.
The main client consumes the recipe, existing asset registry and baked v3 map.

The actual forward raster path uses physical sky, aerial perspective, coherent sun,
ambient, exposure and ACES. A distant shared height-haze approximation begins at
100 km; it does not change culling or active terrain geometry. The sky LUT includes
its existing Lambertian planet-albedo term. Downward sky-only rays use the same
far aerial-perspective volume as opaque terrain, with an equilibrium haze
approximation to join the flat finite NWU world to the curved sky planet. This
changes only background radiance and never masks real geometry. Planet albedo and paint/glass/metal parameters are engineering
approximations, not measured BRDFs. HQ per-pixel sky is optional, default off.
Volumetric clouds are evaluated separately before choosing the budget profile.

The 2 km macro bake remains, with a separate repeating 3 m color/normal/roughness
layer through UV1. Detail color is mean-normalized in linear sRGB, limiting changes
to macro brightness. Color slots use sRGB views; normal and roughness remain linear.
Terrain normals sample the same shared height field across chunk boundaries;
positions/indices and collision heights are unchanged. The material userdata flag
selects the detail shader hook only for the registered detail surface. The emissive
storage slot has zero emission; it stores detail color, not glowing terrain.

F22/F16 source geometry and images are unchanged. Material roles receive conservative
paint roughness, nonmetal dielectric reflectance, transparent canopy/clearcoat and
named-engine metal parameters. This does not turn old diffuse art into measured
PBR or repair low-poly geometry. Other aircraft retain source materials.

Effects use deterministic analytic alpha masks, measured missile snapshots and real
impact events. While running they use core simulation time. After a terminal result,
only visual dissipation uses the caller-supplied presentation dt (default1/60s);
core tick, trajectories, damage and scoring remain frozen. Paused live debugging
retains frozen effects. No new trail samples are created after the result. They cannot create hits or damage. Normal cruise has no detached
orange engine balls; afterburner display is a throttle-based presentation approximation.
`Renderer.visual_settings()`, `memory_usage()`, `statistics()` and
`entity_forward(uid)` expose actual render configuration and diagnostic measurements.

## Validation scope

`game/tools/validate_visual_beta.py` captures fixed before/after views, W/S rendered
responses, input matrices and final three-scene performance (at least 1800 frames).
`game/tools/validate_beta_workflow.py` checks actual Explorer folders, multi-speed
pitch, bounded five-minute control, pause/exact/reset and resident observation fields.
An aggressive earlier F22 combined-turn crash is retained as a known handling limit;
passing bounded stability does not erase that failure.

Full evaluation, screenshots/films, failed candidates, parity, actual logs and raw
performance data are in the dated validation delivery. Inspect visual-review.md,
agent-improvement-log.md and review.md there for measured outcomes and limitations;
a successful build alone is not visual or gameplay acceptance. Keep
BVR_SIM_BUILD_NATIVE_VIEWERS=OFF supported. Build native modules before tests,
never replace loaded PYDs, and do not commit/push unrelated worktree changes.

## Recorded iteration outcome (2026-10-24)

The frozen 20-seed evaluation improved from 0/20 to 10/20 successes after a
measured local-policy first-shot change. The separately held-out ten seeds
produced 5/10 successes. All fifteen F16 cases won; all fifteen F22 cases were
shot down. These are policy results, not a claim that every aircraft is tuned.
An aggressive F22 combined-control terrain crash is retained alongside passing
bounded 300-second handling cases. No weapon or scoring compensation was used.

The final 1080p High run measured 1800 frames per scene with normal logs and HUD:
normal 145.93 FPS / P95 9.37 ms; low sample 195.67 / 7.32 ms; combat effects
127.23 / 13.85 ms, shader errors zero. The 120 FPS / P95 <= 8.33 ms target was
not passed in every scene. Other GPU workloads remain running at the user's
request; raw results are diagnostic and do not certify isolated GPU performance.
Earlier contended runs remain in the delivery. LOD bookkeeping was optimized
without changing thresholds or visible content; its timing gain is unproven
under varying external load.

The final review records low-poly scenery, old diffuse art, horizon haze,
approximate materials and clouds-off limitations. This remains a playable
prototype, not a production-art-quality War Thunder replacement. The legacy
six-argument Renderer constructor and three-argument render calls remain
compatible; the final A10 preview and independent 100-tick flight were exercised.
