# bvr_sim repository instructions

## Simulation ownership

- Physical simulation objects and their dynamics, guidance, collision, damage and lifecycle belong in `bvr_sim/src_cxx/simulator/`. A bomb should be a sibling category such as `simulator/bomb/`, alongside `missile/`, not a physical implementation inside a game session.
- `gameplay/GameSession` adapts commands, configures missions and exposes typed snapshots/events. It may request a spawn and evaluate mission objectives; it must not own a second physics, collision or weapon-damage implementation.
- `bvr_game/` and `game/native/` consume snapshots for input, HUD, rendering, effects and sound. Presentation cannot determine impacts, damage, kills or simulation time.
- Shared terrain/ballistic services needed by objects must live in a simulator/core layer. Do not introduce `simulator/` dependencies on `gameplay/`, the renderer, window APIs or telemetry. CCIP and released bombs must use the same core ballistics and terrain data.
- Core physics must work without constructing `GameSession` or enabling a renderer. Official integration uses typed APIs; debug-register JSON and TelemetryBridge are optional diagnostics.

## Simulation-object workflow

When adding or refactoring a bomb, missile, vehicle, sensor or other simulated object, read and apply `.agents/skills/bvr-add-sim-object/SKILL.md` before implementation. This also applies when a task starts from a game feature but adds physical behavior.

Known debt: `GameBomb` and `ballistic_step()` currently remain in `bvr_sim/src_cxx/gameplay/game_session.cxx`, and shared `GameTerrain` is declared in `game_session.hxx`. This is a migration target, not an approved template. A Mk-82 migration should move shared dependencies as necessary and prove direct core use; relocating a class while importing `GameSession` headers into `simulator/` does not fix the boundary. Do not claim this migration is already complete.

## Verification and review

- For physical-object changes, verify observable headless behavior, lifecycle/reset, deterministic inputs and relevant collision/damage cases. A source-location check or a successful GPU screenshot alone is insufficient.
- Keep core-only builds available with `BVR_SIM_BUILD_NATIVE_VIEWERS=OFF`. Run relevant native/Python regression tests; use rendered/headless parity when game integration changes. Build native modules before importing them in tests, not concurrently with those tests.
- During review, flag new physical-object classes, integration loops or damage rules in session/presentation code. Distinguish core weapon outcomes from session mission scoring.
- Preserve existing worktree changes. Do not commit or push unless requested.
