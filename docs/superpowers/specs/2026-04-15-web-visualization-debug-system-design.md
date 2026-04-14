# Web Visualization And Debug System Design

> **Goal:** Build the future primary rendering path for `bvr_sim` as a real-time web visualization and debugging system for the C++ `SimCore`, with rendering and simulation explicitly decoupled.

> **Status:** Validated in interactive design review on 2026-04-15. This design targets Windows and Linux only. macOS is out of scope.

---

## 1. Scope

This design covers only the real-time visualization and debugging system for the C++ simulation core:

- Real-time 3D rendering of the current `SimCore` world state
- Real-time telemetry and debugging HUD
- A low-coupling command path for limited debug interaction
- Agent-friendly local development and debugging workflow

Out of scope for this project:

- Replay rendering
- Tacview replacement
- High-end rendering quality goals such as PBR, SSR, or ray tracing
- macOS support
- Direct browser access to internal simulation objects

The first phase is debug-visualization-first, not cinematic rendering.

## 2. Core Design Constraints

The following constraints are mandatory:

1. Rendering and simulation must stay decoupled.
2. State exposure must be based on low-coupling state extraction, primarily through object `Register` data rather than ad hoc direct field reads spread across the web layer.
3. Debug interaction must also stay decoupled. Browser-originated commands must flow through a bridge protocol and then into register-backed or mailbox-style command handling, not direct object mutation from the web layer.
4. The visualization stack must ship in the same compiled Python extension (`pyd`/shared object) as `SimCore`, but operate on separate threads with clear responsibilities.
5. The system must fail loudly on schema or state-contract violations. It must not silently drop malformed objects or invent fallback values.
6. Logging and warnings must use existing project patterns such as `colorful::print`, `colorful::printHUANG`, `colorful::printHONG`, `SL::get().print`, and `SL::get().printf`.

## 3. High-Level Architecture

The runtime will be a same-process, multi-threaded system with clear ownership boundaries:

- `SimCore` thread
  - Advances the simulation
  - Owns physics and object stepping
  - Continues writing object state into each object's `Register`
- `TelemetryBridge` thread
  - Periodically samples simulation state
  - Reads object registers and builds a normalized world snapshot
  - Owns command intake and routing
- Embedded `WebServer`
  - Lives inside the same compiled extension
  - Exposes HTTP and WebSocket endpoints for the frontend
  - Reads only bridge-owned snapshots, never simulation objects directly
- `web/` frontend project
  - Uses TypeScript + Vite + Three.js
  - Consumes bridge protocol only
  - Does not depend on simulation internals

This is intentionally not a separate external adapter process. The bridge and web server ship with the C++ extension, but remain logically independent from simulation logic.

## 4. State Model

The bridge exposes two layers of state:

### 4.1 Raw Register View

Purpose:

- Debug inspection
- Future extensibility
- Low-coupling state sourcing from existing simulator objects

The raw register view is not the primary rendering protocol. It is an inspection layer.

### 4.2 Normalized WorldSnapshot

Purpose:

- Stable frontend rendering contract
- Stable telemetry contract
- Isolation of frontend code from internal register naming drift

Each `WorldSnapshot` should include at minimum:

- `sim`
  - `sim_time`
  - `dt`
  - `running`
  - `paused`
- `objects`
  - `uid`
  - `type`
  - `team`
  - `alive`
  - `position`
  - `velocity`
  - `orientation`
  - `display_label`
  - `debug_register`
- optional derived HUD/debug fields
  - altitude
  - speed
  - heading
  - weapon counts
  - lock counts

The normalized snapshot is the rendering contract. The frontend renders from it and not from arbitrary register keys.

## 5. Command Path

The debug command path is intentionally limited in phase 1 and explicitly decoupled.

Supported phase-1 commands:

- `pause`
- `resume`
- `step`
- `set_focus_uid`
- `set_subscription_filter`

Future object-level commands are supported through the same bridge path, but not by directly invoking simulation object methods from the browser.

Recommended model:

- Web client sends structured command
- Embedded web server forwards command to bridge
- Bridge validates and routes command
- Global commands call explicit safe `SimCore` controls
- Object commands are written into reserved register namespace or object command mailboxes

Reserved debug command namespace should be distinct from RL/action-space keys. It must not overload keys such as `delta_heading`.

## 6. Threading And Consistency Model

Three concurrent responsibilities are required:

1. `SimCore` thread for simulation
2. `TelemetryBridge` thread for snapshot generation and command processing
3. Embedded web server thread or event loop for transport

Consistency requirements:

- The bridge must build a complete snapshot and publish it atomically as the current world state.
- The web server must only read already-built snapshots.
- The web server must never assemble snapshots directly from live objects.
- Commands from the web server must first enter a bridge-owned queue.

Recommended cadence:

- Simulation keeps its own timing.
- Bridge sampling starts around `20-30 Hz`.
- WebSocket broadcasting uses the latest bridge snapshot and can later be rate-limited per consumer if needed.

## 7. Error Handling

The bridge is not allowed to hide data-contract errors.

If an object needed for rendering fails the snapshot contract, for example:

- missing required keys
- wrong register value type
- invalid normalized transform state

the bridge should fail immediately via `check(false, "...")` or equivalent hard failure, with project-standard logging before failure where useful.

This project treats snapshot generation as a strict contract, not best-effort telemetry.

## 8. Platform Support

Supported platforms:

- Windows
- Linux

Not supported:

- macOS

Build and runtime choices for the embedded web transport must therefore be selected for Windows/Linux compatibility only. Any cross-platform abstraction added in CMake should make this scope explicit rather than pretending macOS support exists.

## 9. Frontend Design

The frontend lives in-repo as a proper long-term project, not as an ad hoc static page.

Recommended stack:

- Vite
- TypeScript
- Three.js

Phase-1 frontend modules:

- `network`
  - WebSocket connection
  - command submission
- `scene`
  - object entity lifecycle
  - transform updates
- `hud`
  - simulation and object telemetry
- `inspector`
  - raw register and normalized state inspection
- `controls`
  - pause/resume/step
  - focus/filter controls
- `diagnostics`
  - connection health
  - snapshot rate
  - command results

Rendering strategy for phase 1:

- debug visualization first
- simplified geometry or lightweight assets
- no attempt at high-end realism

## 10. Agent And Debugging Workflow

This system should support agent-driven iteration rather than make it difficult.

Required development characteristics:

- stable local startup path
- health endpoint
- predictable dev URLs
- deterministic frontend dev mode defaults where possible
- bridge diagnostics available through HTTP and/or logs

This is specifically intended to support future closed-loop iteration with tools such as PinchTab or similar local browser automation.

## 11. Proposed File/Module Shape

Expected C++ additions around the core:

- `bvr_sim/src_cxx/telemetry/`
  - bridge state and schema
  - snapshot builder
  - command queue and router
  - embedded HTTP/WebSocket server
- `bvr_sim/src_cxx/core.hxx/.cxx`
  - lifecycle hooks for bridge/server startup and shutdown
- `bvr_sim/src_cxx/pybind11_bindings.cxx`
  - bindings to configure or control visualization runtime from Python
- `bvr_sim/src_cxx/CMakeLists.txt`
  - transport library integration
  - Windows/Linux conditional support

Embedded transport choice for phase 1:

- vendor `websocketpp`
- vendor standalone `asio`
- keep all transport integration scoped to Windows/Linux support only

Expected frontend additions:

- `web/`
  - Vite/TypeScript project
  - Three.js scene
  - HUD/inspector/debug controls

## 12. Phase-1 Acceptance Criteria

Phase 1 is complete when all of the following are true:

- `SimCore`, bridge, and embedded web transport run from the same compiled extension
- rendering state is sourced through bridge-owned register-based extraction
- the frontend can connect and render aircraft, missiles, and ground units in real time
- the frontend can display key telemetry and inspect raw register state
- the frontend can issue `pause`, `resume`, and `step`
- the system fails loudly on snapshot contract violations
- the build and smoke workflow works on Windows and Linux
