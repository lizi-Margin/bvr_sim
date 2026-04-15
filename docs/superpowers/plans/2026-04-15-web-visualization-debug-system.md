# Web Visualization And Debug System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows/Linux real-time web visualization and debugging system for the C++ `SimCore`, with strict simulation/rendering decoupling and an embedded web transport inside the same compiled extension.

**Architecture:** Add an in-process `TelemetryBridge` subsystem that samples object `Register` state into a strict `WorldSnapshot`, owns a queued command path, and serves that data through an embedded HTTP/WebSocket server. Add an in-repo `web/` Vite + TypeScript + Three.js frontend that consumes only the bridge protocol and provides debug visualization controls.

**Tech Stack:** C++17, pybind11, existing `Register`/`SimCore` infrastructure, vendored `websocketpp` + standalone `asio` for embedded HTTP/WebSocket transport, Vite, TypeScript, Three.js, Python smoke tests

---

## File Structure

### C++ runtime files

- Create: `bvr_sim/src_cxx/telemetry/telemetry_types.hxx`
  - `WorldSnapshot`, normalized object payloads, command/result payloads
- Create: `bvr_sim/src_cxx/telemetry/telemetry_types.cxx`
  - JSON serialization helpers for bridge payloads
- Create: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.hxx`
  - strict register-to-snapshot builder API
- Create: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.cxx`
  - bridge snapshot construction with `check(false, "...")` on contract violations
- Create: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.hxx`
  - queued command model and thread-safe mailbox
- Create: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.cxx`
  - queue implementation
- Create: `bvr_sim/src_cxx/telemetry/telemetry_bridge.hxx`
  - bridge lifecycle, sampling loop, latest snapshot store
- Create: `bvr_sim/src_cxx/telemetry/telemetry_bridge.cxx`
  - sampling thread, command routing, diagnostics
- Create: `bvr_sim/src_cxx/telemetry/embedded_web_server.hxx`
  - embedded HTTP/WebSocket server interface
- Create: `bvr_sim/src_cxx/telemetry/embedded_web_server.cxx`
  - server implementation backed by vendored transport library

### C++ integration files

- Modify: `bvr_sim/src_cxx/core.hxx`
  - add bridge/server lifecycle ownership
- Modify: `bvr_sim/src_cxx/core.cxx`
  - start/stop bridge and web server with `SimCore`
- Modify: `bvr_sim/src_cxx/pybind11_bindings.cxx`
  - expose configuration/control APIs for visualization runtime
- Modify: `bvr_sim/src_cxx/CMakeLists.txt`
  - compile new telemetry files and vendored transport dependency
- Modify: `bvr_sim/src_cxx/simulator/register.hxx`
  - only if needed for safer typed helpers or snapshot extraction convenience
- Modify: `bvr_sim/src_cxx/simulator/register.cxx`
  - only if needed for the same reason

### Frontend files

- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.ts`
- Create: `web/src/network/client.ts`
- Create: `web/src/network/types.ts`
- Create: `web/src/scene/worldScene.ts`
- Create: `web/src/scene/entityStore.ts`
- Create: `web/src/ui/hud.ts`
- Create: `web/src/ui/inspector.ts`
- Create: `web/src/ui/controls.ts`
- Create: `web/src/ui/diagnostics.ts`
- Create: `web/src/styles.css`

### Tests and docs

- Create: `bvr_sim/src_cxx/test_telemetry_snapshot.cxx`
- Create: `bvr_sim/src_cxx/test_telemetry_command_queue.cxx`
- Create: `tests/test_web_bridge_smoke.py`
- Modify: `tests/cpp_unit_tests.py`
  - include telemetry unit-test executable output if needed
- Modify: `README.md`
  - add Windows/Linux visualization setup and launch flow
- Modify: `docs/developer/architecture.md`
  - document bridge/server/frontend architecture

### Vendored dependency

- Create: `bvr_sim/src_cxx/extern/websocketpp/`
- Create: `bvr_sim/src_cxx/extern/asio/`

The transport choice is fixed for this plan: vendor `websocketpp` plus standalone `asio`, scoped to Windows/Linux support only.

---

### Task 1: Add The Telemetry Module Skeleton

**Files:**
- Create: `bvr_sim/src_cxx/telemetry/telemetry_types.hxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_types.cxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.hxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.cxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.hxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.cxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_bridge.hxx`
- Create: `bvr_sim/src_cxx/telemetry/telemetry_bridge.cxx`

- [ ] **Step 1: Write the failing telemetry unit tests**

Add test skeletons to `bvr_sim/src_cxx/test_telemetry_snapshot.cxx` and `bvr_sim/src_cxx/test_telemetry_command_queue.cxx`:

```cpp
TEST(TelemetrySnapshot, RequiresCoreFieldsFromRegister) {
    // Build a fake object/register payload with a missing required field
    // Expect builder to terminate via check(false, ...)
}

TEST(TelemetryCommandQueue, PreservesQueuedCommandOrder) {
    // Push three commands and verify pop order is FIFO
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python tests/cpp_unit_tests.py`

Expected: telemetry tests are not compiled yet or fail because telemetry files are missing.

- [ ] **Step 3: Write the minimal telemetry type and queue skeletons**

Define minimal types:

```cpp
struct TelemetryObjectState {
    std::string uid;
    std::string type;
    std::string team;
    bool alive;
    std::array<double, 3> position;
    std::array<double, 3> velocity;
    std::array<double, 3> orientation;
    json::JSON debug_register;
};

struct WorldSnapshot {
    double sim_time;
    double dt;
    bool running;
    bool paused;
    std::vector<TelemetryObjectState> objects;
};
```

- [ ] **Step 4: Update CMake so the new telemetry files and tests compile**

Modify `bvr_sim/src_cxx/CMakeLists.txt` to add the telemetry source files and the two new test files to the unit-test target.

- [ ] **Step 5: Run tests to verify the module now builds**

Run: `python tests/cpp_unit_tests.py`

Expected: build succeeds, telemetry tests still fail because logic is stubbed.

- [ ] **Step 6: Commit**

```bash
git add bvr_sim/src_cxx/CMakeLists.txt bvr_sim/src_cxx/telemetry bvr_sim/src_cxx/test_telemetry_snapshot.cxx bvr_sim/src_cxx/test_telemetry_command_queue.cxx
git commit -m "feat: add telemetry bridge module skeleton"
```

### Task 2: Implement Strict Register-To-Snapshot Building

**Files:**
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.hxx`
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.cxx`
- Modify: `bvr_sim/src_cxx/test_telemetry_snapshot.cxx`
- Modify: `bvr_sim/src_cxx/simulator/register.hxx` if typed helpers are required
- Modify: `bvr_sim/src_cxx/simulator/register.cxx` if typed helpers are required

- [ ] **Step 1: Expand the failing tests for required snapshot fields**

Add explicit tests for:

```cpp
TEST(TelemetrySnapshot, BuildsNormalizedStateFromRegister) {}
TEST(TelemetrySnapshot, FailsWhenPositionMissing) {}
TEST(TelemetrySnapshot, FailsWhenOrientationHasWrongType) {}
```

- [ ] **Step 2: Run the telemetry test file to verify failure**

Run: `python tests/cpp_unit_tests.py`

Expected: the new telemetry snapshot tests fail because builder logic is incomplete.

- [ ] **Step 3: Implement the builder with strict validation**

Implement functions that:

- read required keys from `Register`
- normalize `Type`, `color/team`, transform, and debug payload
- call `check(false, "...")` on missing or invalid required fields
- use `colorful::print*` or `SL::get().print*` for debug context before failing where useful

Required key checks should cover at least:

- `uid`
- `Type`
- `color`
- `is_alive`
- `position`
- `velocity`

- [ ] **Step 4: Add orientation derivation in the builder**

Use object-specific register data where present:

- prefer `rpy` for aircraft
- otherwise derive a fallback orientation from normalized velocity only if that fallback is explicitly part of the spec
- if the chosen contract requires `rpy` and it is absent for a renderable object type, fail loudly

- [ ] **Step 5: Run tests to verify they pass**

Run: `python tests/cpp_unit_tests.py`

Expected: telemetry snapshot tests pass and no schema-error test is silently ignored.

- [ ] **Step 6: Commit**

```bash
git add bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.hxx bvr_sim/src_cxx/telemetry/telemetry_snapshot_builder.cxx bvr_sim/src_cxx/test_telemetry_snapshot.cxx bvr_sim/src_cxx/simulator/register.hxx bvr_sim/src_cxx/simulator/register.cxx
git commit -m "feat: implement strict register to world snapshot builder"
```

### Task 3: Implement The Thread-Safe Command Queue And Command Model

**Files:**
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.hxx`
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_command_queue.cxx`
- Modify: `bvr_sim/src_cxx/test_telemetry_command_queue.cxx`

- [ ] **Step 1: Write the failing queue and command tests**

Cover:

```cpp
TEST(TelemetryCommandQueue, PushAndPopSingleCommand) {}
TEST(TelemetryCommandQueue, PreservesQueuedCommandOrder) {}
TEST(TelemetryCommandQueue, RejectsUnknownCommandKind) {}
```

- [ ] **Step 2: Run tests to verify failure**

Run: `python tests/cpp_unit_tests.py`

Expected: queue tests fail because parsing/validation is not implemented.

- [ ] **Step 3: Implement the queued command types**

Define a command enum and payload shape for:

- `pause`
- `resume`
- `step`
- `set_focus_uid`
- `set_subscription_filter`
- reserved future object debug command

- [ ] **Step 4: Implement the thread-safe queue**

Provide:

- `push`
- non-blocking `try_pop`
- optional `drain`
- structured command result payloads for the web diagnostics layer

- [ ] **Step 5: Run tests to verify pass**

Run: `python tests/cpp_unit_tests.py`

Expected: queue tests pass.

- [ ] **Step 6: Commit**

```bash
git add bvr_sim/src_cxx/telemetry/telemetry_command_queue.hxx bvr_sim/src_cxx/telemetry/telemetry_command_queue.cxx bvr_sim/src_cxx/test_telemetry_command_queue.cxx
git commit -m "feat: add telemetry bridge command queue"
```

### Task 4: Implement The Bridge Sampling Thread And Atomic Latest Snapshot

**Files:**
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_bridge.hxx`
- Modify: `bvr_sim/src_cxx/telemetry/telemetry_bridge.cxx`
- Modify: `bvr_sim/src_cxx/core.hxx`
- Modify: `bvr_sim/src_cxx/core.cxx`

- [ ] **Step 1: Write the failing integration tests for bridge lifecycle**

Add tests that expect:

- bridge starts and stops cleanly
- bridge publishes at least one snapshot when objects exist
- bridge consumes commands from the queue

If unit-test target cannot host this safely, add a Python smoke test placeholder in `tests/test_web_bridge_smoke.py`.

- [ ] **Step 2: Run targeted tests to verify failure**

Run: `python tests/test_web_bridge_smoke.py`

Expected: fails because bridge lifecycle is not integrated yet.

- [ ] **Step 3: Implement `TelemetryBridge`**

The bridge should:

- own a worker thread
- periodically collect active objects from `SOPool`
- build a complete `WorldSnapshot`
- atomically publish the latest snapshot
- process queued commands each cycle

Recommended minimal API:

```cpp
void start();
void stop();
std::shared_ptr<const WorldSnapshot> get_latest_snapshot() const;
void submit_command(const TelemetryCommand& cmd);
```

- [ ] **Step 4: Integrate bridge ownership into `SimCore`**

Update `SimCore` so bridge lifecycle is tied to simulation lifecycle but remains logically independent:

- start bridge when simulation starts or when visualization runtime is explicitly enabled
- stop bridge before shutdown completes
- keep `SimCore` stepping logic separate from bridge sampling

- [ ] **Step 5: Run the smoke test to verify pass**

Run: `python tests/test_web_bridge_smoke.py`

Expected: the process starts, bridge initializes, and at least one snapshot is produced.

- [ ] **Step 6: Commit**

```bash
git add bvr_sim/src_cxx/telemetry/telemetry_bridge.hxx bvr_sim/src_cxx/telemetry/telemetry_bridge.cxx bvr_sim/src_cxx/core.hxx bvr_sim/src_cxx/core.cxx tests/test_web_bridge_smoke.py
git commit -m "feat: add telemetry bridge sampling thread"
```

### Task 5: Vendor And Integrate The Embedded HTTP/WebSocket Transport

**Files:**
- Create: `bvr_sim/src_cxx/extern/websocketpp/`
- Create: `bvr_sim/src_cxx/extern/asio/`
- Modify: `bvr_sim/src_cxx/CMakeLists.txt`
- Modify: `bvr_sim/src_cxx/telemetry/embedded_web_server.hxx`
- Modify: `bvr_sim/src_cxx/telemetry/embedded_web_server.cxx`

- [ ] **Step 1: Add a failing smoke test for the web endpoints**

In `tests/test_web_bridge_smoke.py`, add expectations for:

- HTTP health endpoint responds
- WebSocket endpoint accepts a client
- first snapshot message arrives

- [ ] **Step 2: Run the smoke test to verify failure**

Run: `python tests/test_web_bridge_smoke.py`

Expected: endpoint connection fails because server transport is not implemented.

- [ ] **Step 3: Vendor `websocketpp` and standalone `asio` under `src_cxx/extern/`**

Keep the dependency scoped to Windows/Linux and avoid macOS work.

- [ ] **Step 4: Wire the transport into CMake**

Add include directories, compile definitions, and any platform-specific linkage required for Windows/Linux only.

- [ ] **Step 5: Implement the embedded server**

Expose at minimum:

- `GET /health`
- `GET /diagnostics`
- WebSocket `/ws`

The server must:

- serialize the latest `WorldSnapshot`
- broadcast snapshots to connected clients
- accept structured JSON commands and enqueue them into the bridge

- [ ] **Step 6: Run the smoke test to verify pass**

Run: `python tests/test_web_bridge_smoke.py`

Expected: health endpoint returns success, WebSocket connects, and a snapshot payload arrives.

- [ ] **Step 7: Commit**

```bash
git add bvr_sim/src_cxx/CMakeLists.txt bvr_sim/src_cxx/extern bvr_sim/src_cxx/telemetry/embedded_web_server.hxx bvr_sim/src_cxx/telemetry/embedded_web_server.cxx tests/test_web_bridge_smoke.py
git commit -m "feat: add embedded telemetry web server"
```

### Task 6: Expose Visualization Runtime Control Through Pybind

**Files:**
- Modify: `bvr_sim/src_cxx/pybind11_bindings.cxx`
- Modify: `bvr_sim/src_cxx/core.hxx`
- Modify: `bvr_sim/src_cxx/core.cxx`

- [ ] **Step 1: Write the failing Python smoke assertions**

In `tests/test_web_bridge_smoke.py`, add expectations that Python can:

- enable visualization runtime
- query server URL/port
- stop the visualization runtime cleanly

- [ ] **Step 2: Run the smoke test to verify failure**

Run: `python tests/test_web_bridge_smoke.py`

Expected: missing Python binding methods.

- [ ] **Step 3: Add minimal bindings**

Expose methods such as:

```cpp
def("start_visualization_server", ...)
def("stop_visualization_server", ...)
def("get_visualization_status", ...)
```

Keep bindings focused on bridge/server lifecycle and diagnostics, not direct frontend behavior.

- [ ] **Step 4: Run the smoke test to verify pass**

Run: `python tests/test_web_bridge_smoke.py`

Expected: Python can configure and inspect the visualization runtime.

- [ ] **Step 5: Commit**

```bash
git add bvr_sim/src_cxx/pybind11_bindings.cxx bvr_sim/src_cxx/core.hxx bvr_sim/src_cxx/core.cxx tests/test_web_bridge_smoke.py
git commit -m "feat: expose visualization runtime controls to python"
```

### Task 7: Scaffold The In-Repo Frontend Project

**Files:**
- Create: `web/package.json`
- Create: `web/tsconfig.json`
- Create: `web/vite.config.ts`
- Create: `web/index.html`
- Create: `web/src/main.ts`
- Create: `web/src/network/client.ts`
- Create: `web/src/network/types.ts`
- Create: `web/src/styles.css`

- [ ] **Step 1: Write the failing frontend bootstrap check**

Add a smoke command to `tests/test_web_bridge_smoke.py` that runs:

```bash
npm --prefix web install
npm --prefix web run build
```

Expected outcome now: fail because the frontend project does not exist yet.

- [ ] **Step 2: Scaffold the Vite + TypeScript frontend**

Create a minimal app with:

- a network client that connects to `/ws`
- TypeScript definitions matching `WorldSnapshot`
- a visible status panel showing connection state and object count

- [ ] **Step 3: Run the frontend build to verify pass**

Run: `npm --prefix web install`

Run: `npm --prefix web run build`

Expected: production build succeeds on Windows/Linux development machines with Node installed.

- [ ] **Step 4: Commit**

```bash
git add web tests/test_web_bridge_smoke.py
git commit -m "feat: scaffold web visualization frontend"
```

### Task 8: Implement The Three.js Scene, HUD, And Debug Controls

**Files:**
- Modify: `web/src/main.ts`
- Create: `web/src/scene/worldScene.ts`
- Create: `web/src/scene/entityStore.ts`
- Create: `web/src/ui/hud.ts`
- Create: `web/src/ui/inspector.ts`
- Create: `web/src/ui/controls.ts`
- Create: `web/src/ui/diagnostics.ts`
- Modify: `web/src/styles.css`

- [ ] **Step 1: Write the failing UI smoke assertions**

Extend `tests/test_web_bridge_smoke.py` to verify the built frontend assets load and that the app can render after the first snapshot. If browser automation is not yet practical, add a deterministic DOM-level smoke assertion in frontend unit tests or a manual launch check documented in the test file.

- [ ] **Step 2: Implement the scene and entity update flow**

Build:

- aircraft/missile/ground placeholders in Three.js
- transform updates from `WorldSnapshot`
- focus handling for a selected object

- [ ] **Step 3: Implement the HUD and diagnostics panels**

Display:

- sim time
- pause/running state
- selected object speed/altitude/heading when available
- connection state
- snapshot rate
- last command result

- [ ] **Step 4: Implement limited debug controls**

Support:

- pause
- resume
- step
- focus selection
- basic object filtering

- [ ] **Step 5: Run the frontend build and smoke workflow**

Run: `npm --prefix web run build`

Run: `python tests/test_web_bridge_smoke.py`

Expected: frontend builds, connects, and the debug UI operates against the embedded server.

- [ ] **Step 6: Commit**

```bash
git add web tests/test_web_bridge_smoke.py
git commit -m "feat: implement realtime threejs debug visualization"
```

### Task 9: Add Documentation And Cross-Platform Launch Flow

**Files:**
- Modify: `README.md`
- Modify: `docs/developer/architecture.md`
- Modify: `docs/installation.md` if setup steps are needed

- [ ] **Step 1: Write the failing documentation checklist**

Add a local checklist section in the plan execution notes to verify docs cover:

- Windows build and launch
- Linux build and launch
- Node requirement for `web/`
- visualization server startup flow
- frontend startup flow

- [ ] **Step 2: Update architecture docs**

Document:

- `SimCore` / bridge / server / frontend boundaries
- strict snapshot contract behavior
- command queue model
- Windows/Linux support scope

- [ ] **Step 3: Update user-facing setup docs**

Document exact commands for:

- building the extension
- starting the simulation with visualization enabled
- running the frontend dev server
- opening the browser and expected URL

- [ ] **Step 4: Verify docs against a clean local run**

Run the documented commands on the current machine and ensure they match reality. Do not leave guessed commands in the docs.

- [ ] **Step 5: Commit**

```bash
git add README.md docs/developer/architecture.md docs/installation.md
git commit -m "docs: add visualization system architecture and setup guide"
```

### Task 10: Run Full Verification

**Files:**
- Verify only

- [ ] **Step 1: Run C++ unit tests**

Run: `python tests/cpp_unit_tests.py`

Expected: telemetry and existing unit tests pass.

- [ ] **Step 2: Run Python/C++ smoke tests**

Run: `python tests/test_cpp.py`

Run: `python tests/test_web_bridge_smoke.py`

Expected: simulation still starts and the visualization smoke test passes.

- [ ] **Step 3: Run frontend production build**

Run: `npm --prefix web run build`

Expected: build succeeds.

- [ ] **Step 4: Run the broad verification suite**

Run: `python run_tests.py`

Expected: existing integration coverage still passes after telemetry/web changes.

- [ ] **Step 5: Validate phase-1 acceptance criteria**

Check all of the following:

- [ ] same-extension runtime contains `SimCore`, bridge, and embedded web server
- [ ] rendering state comes from bridge-owned register extraction
- [ ] frontend renders aircraft, missiles, and ground units
- [ ] frontend exposes HUD, inspector, and limited debug controls
- [ ] snapshot contract violations fail loudly
- [ ] Windows and Linux build paths are documented and supported

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: complete web visualization and debug system phase 1"
```
