# Missile FDM Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract physics simulation (aerodynamics, kinematics, propulsion) from MModelA into a reusable `GenericMissileFDM` class, backed by a new `ParamStore` typed parameter container, so that future MModelB/C/D can reuse the same physics engine.

**Architecture:** A new `ParamStore` class (typed key-value store with JSON serialization) replaces the `MissileParams` struct as the parameter carrier. `GenericMissileFDM` inherits `BaseFDM` and holds a `const ParamStore&` reference, implementing aerodynamics + kinematics + propulsion logic extracted from MModelA. MModelA is refactored to own both `ParamStore` and `GenericMissileFDM`, initializing params via a hardcoded JSON string. `MissileParams` struct is **not deleted** — it remains for existing `aim120c.cxx`.

**Tech Stack:** C++17, `rubbish_can/json.hpp` (SimpleJSON), `rubbish_can/interp_table.hxx`, existing `BaseFDM` interface, project `TEST()` macro (`test_main.hxx`)

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| **Modify** | `bvr_sim/src_cxx/rubbish_can/interp_table.hxx` | Add `to_json()` / `from_json()` methods |
| **Create** | `bvr_sim/src_cxx/simulator/param_store.hxx` | Typed parameter store declaration |
| **Create** | `bvr_sim/src_cxx/simulator/param_store.cxx` | `ParamStore` implementation + JSON serialization |
| **Create** | `bvr_sim/src_cxx/test_param_store.cxx` | Unit tests for `ParamStore` (alongside `test_main.cxx`) |
| **Create** | `bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.hxx` | `GenericMissileFDM` class declaration |
| **Create** | `bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.cxx` | Physics: aero + kinematics + propulsion |
| **Create** | `bvr_sim/src_cxx/test_generic_missile_fdm.cxx` | Unit tests for `GenericMissileFDM` |
| **Modify** | `bvr_sim/src_cxx/simulator/missile/mmodelA.hxx` | Own `ParamStore` + `GenericMissileFDM` |
| **Modify** | `bvr_sim/src_cxx/simulator/missile/mmodelA.cxx` | Init from JSON string; delegate physics to `fdm_` |
| **Modify** | `bvr_sim/src_cxx/CMakeLists.txt` | Add new `.cxx` files to `BVR_SIM_SOURCES` and unit test target |

---

## Task 1: Add `to_json` / `from_json` to InterpTable

**Files:**
- Modify: `bvr_sim/src_cxx/rubbish_can/interp_table.hxx`

`InterpTable` is header-only and lives in `rubbish_can/`. Its existing includes use bare names (`"check.hxx"`, `"colorful.hxx"`) because they are siblings in the same directory. Add `json.hpp` using the same convention.

- [ ] **Step 1: Add include for json.hpp**

Add to the top of `interp_table.hxx` (after existing includes):

```cpp
#include "json.hpp"
```

Note: use `"json.hpp"` (not `"rubbish_can/json.hpp"`) — `interp_table.hxx` is in `rubbish_can/`, so the sibling-relative path is correct here.

- [ ] **Step 2: Add `to_json()` and `from_json()` methods**

Add inside the `InterpTable` class body, after `getY()`:

```cpp
json::JSON to_json() const {
    json::JSON j;
    json::JSON x_arr = json::JSON::Make(json::JSON::Class::Array);
    json::JSON y_arr = json::JSON::Make(json::JSON::Class::Array);
    for (size_t i = 0; i < x_.size(); ++i) {
        x_arr.append(x_[i]);
        y_arr.append(y_[i]);
    }
    j["x"] = x_arr;
    j["y"] = y_arr;
    return j;
}

static InterpTable from_json(const json::JSON& j) {
    std::vector<double> x, y;
    // Guard: SimpleJSON parses integers as Class::Integral, not Class::Floating.
    // ToFloat() aborts on Class::Integral, so check type before calling.
    for (auto& v : j["x"].ArrayRange())
        x.push_back(v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt()));
    for (auto& v : j["y"].ArrayRange())
        y.push_back(v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt()));
    return InterpTable(x, y);
}
```

- [ ] **Step 3: Build to verify no compile errors**

```bash
cd bvr_sim && ./build_windows.bat
```

Expected: build succeeds, no new errors.

- [ ] **Step 4: Commit**

```bash
git add bvr_sim/src_cxx/rubbish_can/interp_table.hxx
git commit -m "feat: add to_json/from_json to InterpTable"
```

---

## Task 2: Create `ParamStore` — write tests first, then implement

**Files:**
- Create: `bvr_sim/src_cxx/simulator/param_store.hxx`
- Create: `bvr_sim/src_cxx/test_param_store.cxx`  ← write first
- Create: `bvr_sim/src_cxx/simulator/param_store.cxx`

**JSON convention:** All numeric values in JSON strings must have decimal points (e.g. `8.0` not `8`) to ensure SimpleJSON parses them as `Class::Floating`. The `from_string()` implementation guards against `Class::Integral` regardless.

- [ ] **Step 1: Create `param_store.hxx` stub**

```cpp
#pragma once

#include "rubbish_can/json.hpp"
#include "rubbish_can/interp_table.hxx"
#include <map>
#include <memory>
#include <optional>
#include <string>

namespace bvr_sim {

// InterpTable is defined at global scope (no namespace)
using ::InterpTable;

/// Typed key-value parameter store.
/// Keys share a single namespace across all types — setting the same key
/// with a different type throws std::runtime_error.
/// JSON round-trip via to_string() / from_string().
class ParamStore {
public:
    ParamStore() = default;

    // ===== Getters =====
    std::optional<double>                       get_double(const std::string& key) const noexcept;
    std::optional<std::string>                  get_string(const std::string& key) const noexcept;
    std::optional<std::shared_ptr<InterpTable>> get_interp_table(const std::string& key) const noexcept;

    // ===== Setters (throw if key already exists with different type) =====
    void set_double(const std::string& key, double value);
    void set_string(const std::string& key, const std::string& value);
    void set_interp_table(const std::string& key, std::shared_ptr<InterpTable> table);

    // ===== Queries =====
    bool        has_key(const std::string& key) const noexcept;
    std::string get_key_type(const std::string& key) const noexcept; // "double"|"string"|"table"|""

    // ===== Serialization (JSON internally) =====
    std::string         to_string() const;
    static ParamStore   from_string(const std::string& json_str);

private:
    std::map<std::string, double>                       doubles_;
    std::map<std::string, std::string>                  strings_;
    std::map<std::string, std::shared_ptr<InterpTable>> tables_;
    std::map<std::string, std::string>                  key_types_; // key -> "double"|"string"|"table"

    void _register_key(const std::string& key, const std::string& type);
};

} // namespace bvr_sim
```

- [ ] **Step 2: Create `test_param_store.cxx` (tests will fail until Step 4)**

Place alongside `test_main.cxx` at `bvr_sim/src_cxx/test_param_store.cxx`:

```cpp
#include "test_main.hxx"
#include "simulator/param_store.hxx"
#include "rubbish_can/interp_table.hxx"
#include <memory>
#include <cmath>

TEST(ParamStore, SetAndGetDouble) {
    bvr_sim::ParamStore ps;
    ps.set_double("mass", 161.48);
    auto v = ps.get_double("mass");
    ASSERT(v.has_value());
    ASSERT_NEAR(v.value(), 161.48, 1e-9);
}

TEST(ParamStore, SetAndGetString) {
    bvr_sim::ParamStore ps;
    ps.set_string("model", "AIM-120C");
    auto v = ps.get_string("model");
    ASSERT(v.has_value());
    ASSERT(v.value() == "AIM-120C");
}

TEST(ParamStore, MissingKeyReturnsNullopt) {
    bvr_sim::ParamStore ps;
    ASSERT(!ps.get_double("nonexistent").has_value());
    ASSERT(!ps.get_string("nonexistent").has_value());
    ASSERT(!ps.get_interp_table("nonexistent").has_value());
}

TEST(ParamStore, TypeConflictThrows) {
    bvr_sim::ParamStore ps;
    ps.set_double("key", 1.0);
    bool threw = false;
    try { ps.set_string("key", "oops"); } catch (const std::exception&) { threw = true; }
    ASSERT(threw);
}

TEST(ParamStore, HasKey) {
    bvr_sim::ParamStore ps;
    ASSERT(!ps.has_key("x"));
    ps.set_double("x", 1.0);
    ASSERT(ps.has_key("x"));
    ASSERT(ps.get_key_type("x") == "double");
}

TEST(ParamStore, JsonRoundtripDoublesAndStrings) {
    bvr_sim::ParamStore ps;
    ps.set_double("m0", 161.48);
    ps.set_double("g", 9.81);
    ps.set_string("model", "AIM-120C");

    std::string json_str = ps.to_string();
    auto ps2 = bvr_sim::ParamStore::from_string(json_str);

    ASSERT_NEAR(ps2.get_double("m0").value(), 161.48, 1e-9);
    ASSERT_NEAR(ps2.get_double("g").value(), 9.81, 1e-9);
    ASSERT(ps2.get_string("model").value() == "AIM-120C");
}

TEST(ParamStore, JsonRoundtripInterpTable) {
    bvr_sim::ParamStore ps;
    ps.set_interp_table("cx", std::make_shared<InterpTable>(
        std::vector<double>{0.5, 1.0, 2.0},
        std::vector<double>{0.3, 0.6, 0.4}
    ));

    std::string json_str = ps.to_string();
    auto ps2 = bvr_sim::ParamStore::from_string(json_str);

    auto tbl = ps2.get_interp_table("cx");
    ASSERT(tbl.has_value());
    ASSERT_NEAR((*tbl)->interpolate(1.0), 0.6, 1e-9);
}

TEST(ParamStore, JsonRoundtripIntegerValuesInJson) {
    // Integer-valued JSON numbers (no decimal point) must not abort
    std::string json_str = R"({"doubles": {"t_thrust": 8, "K": 3}, "strings": {}, "tables": {}})";
    auto ps = bvr_sim::ParamStore::from_string(json_str);
    ASSERT_NEAR(ps.get_double("t_thrust").value(), 8.0, 1e-9);
    ASSERT_NEAR(ps.get_double("K").value(), 3.0, 1e-9);
}
```

- [ ] **Step 3: Add test AND implementation files to `bvr_sim_unit_tests` target in CMakeLists.txt**

`bvr_sim_unit_tests` is a separate executable from the pybind module — it does not use `BVR_SIM_SOURCES`. Add both the implementation and test file directly to the unit test target:

```cmake
add_executable(bvr_sim_unit_tests
    test_main.cxx
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/param_store.cxx"   # <-- add
    "${CMAKE_CURRENT_SOURCE_DIR}/test_param_store.cxx"        # <-- add
)
```

(`param_store.cxx` also goes into `BVR_SIM_SOURCES` in Step 6 for the pybind module.)

- [ ] **Step 4: Build (tests compile but will fail — `param_store.cxx` not yet written)**

```bash
cd bvr_sim && ./build_windows.bat
cd tests && python cpp_unit_tests.py
```

Expected: build succeeds, ParamStore tests FAIL (symbols unresolved or functions not implemented).

- [ ] **Step 5: Create `param_store.cxx`**

```cpp
#include "param_store.hxx"
#include <stdexcept>

namespace bvr_sim {

void ParamStore::_register_key(const std::string& key, const std::string& type) {
    auto it = key_types_.find(key);
    if (it != key_types_.end() && it->second != type) {
        throw std::runtime_error(
            "ParamStore: key '" + key + "' already registered as '" +
            it->second + "', cannot re-register as '" + type + "'"
        );
    }
    key_types_[key] = type;
}

std::optional<double> ParamStore::get_double(const std::string& key) const noexcept {
    auto it = doubles_.find(key);
    if (it == doubles_.end()) return std::nullopt;
    return it->second;
}

std::optional<std::string> ParamStore::get_string(const std::string& key) const noexcept {
    auto it = strings_.find(key);
    if (it == strings_.end()) return std::nullopt;
    return it->second;
}

std::optional<std::shared_ptr<InterpTable>> ParamStore::get_interp_table(const std::string& key) const noexcept {
    auto it = tables_.find(key);
    if (it == tables_.end()) return std::nullopt;
    return it->second;
}

void ParamStore::set_double(const std::string& key, double value) {
    _register_key(key, "double");
    doubles_[key] = value;
}

void ParamStore::set_string(const std::string& key, const std::string& value) {
    _register_key(key, "string");
    strings_[key] = value;
}

void ParamStore::set_interp_table(const std::string& key, std::shared_ptr<InterpTable> table) {
    _register_key(key, "table");
    tables_[key] = std::move(table);
}

bool ParamStore::has_key(const std::string& key) const noexcept {
    return key_types_.find(key) != key_types_.end();
}

std::string ParamStore::get_key_type(const std::string& key) const noexcept {
    auto it = key_types_.find(key);
    if (it == key_types_.end()) return "";
    return it->second;
}

std::string ParamStore::to_string() const {
    json::JSON root;
    json::JSON doubles_j, strings_j, tables_j;

    for (const auto& [k, v] : doubles_)
        doubles_j[k] = v;
    for (const auto& [k, v] : strings_)
        strings_j[k] = v;
    for (const auto& [k, v] : tables_)
        tables_j[k] = v->to_json();

    root["doubles"] = doubles_j;
    root["strings"] = strings_j;
    root["tables"]  = tables_j;
    return root.dump();
}

ParamStore ParamStore::from_string(const std::string& json_str) {
    auto root = json::JSON::Load(json_str);
    ParamStore store;

    if (root.hasKey("doubles")) {
        for (auto& [k, v] : root["doubles"].ObjectRange()) {
            // Guard against integer-valued JSON numbers (Class::Integral vs Class::Floating)
            double val = v.IsFloating() ? v.ToFloat() : static_cast<double>(v.ToInt());
            store.set_double(k, val);
        }
    }
    if (root.hasKey("strings")) {
        for (auto& [k, v] : root["strings"].ObjectRange())
            store.set_string(k, v.ToString());
    }
    if (root.hasKey("tables")) {
        for (auto& [k, v] : root["tables"].ObjectRange())
            store.set_interp_table(k, std::make_shared<InterpTable>(InterpTable::from_json(v)));
    }
    return store;
}

} // namespace bvr_sim
```

- [ ] **Step 6: Add `param_store.cxx` to `BVR_SIM_SOURCES` in CMakeLists.txt**

```cmake
"${CMAKE_CURRENT_SOURCE_DIR}/simulator/param_store.cxx"
```

- [ ] **Step 7: Build and run tests — all ParamStore tests should pass**

```bash
cd bvr_sim && ./build_windows.bat
cd tests && python cpp_unit_tests.py
```

Expected: `ParamStore::*` tests all PASS.

- [ ] **Step 8: Commit**

```bash
git add bvr_sim/src_cxx/simulator/param_store.hxx \
        bvr_sim/src_cxx/simulator/param_store.cxx \
        bvr_sim/src_cxx/test_param_store.cxx \
        bvr_sim/src_cxx/CMakeLists.txt
git commit -m "feat: add ParamStore typed parameter container with JSON serialization + tests"
```

---

## Task 3: Create `GenericMissileFDM` — write tests first, then implement

**Files:**
- Create: `bvr_sim/src_cxx/test_generic_missile_fdm.cxx`  ← write first
- Create: `bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.hxx`
- Create: `bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.cxx`

**`nz` gravity convention:** `nz` is the *aerodynamic* normal load factor (does not include gravity). Gravity is applied separately as a world-frame term `[0, 0, -g]`. This is the unambiguous approach: aerodynamic forces (thrust, drag, lift from `ny`/`nz`) + gravity as a separate constant body force.

**Parameter keys expected in ParamStore:**

| Key | Type | Description |
|-----|------|-------------|
| `m0` | double | Initial mass (kg) |
| `dm` | double | Mass flow rate (kg/s) |
| `thrust` | double | Thrust force (N) |
| `t_thrust` | double | Thrust duration (s) |
| `S_ref` | double | Reference area (m²) |
| `mach_min` | double | Minimum Mach number |
| `nyz_max` | double | Max lateral acceleration (g) |
| `g` | double | Gravity (m/s²) |
| `cx_total_table` | table | Mach → Cx_total (drag coefficient) |

- [ ] **Step 1: Create directory `bvr_sim/src_cxx/simulator/missile/fdm/`**

(Just create the directory; files go in Steps 2–5.)

- [ ] **Step 2: Create `test_generic_missile_fdm.cxx`**

Place at `bvr_sim/src_cxx/test_generic_missile_fdm.cxx`:

```cpp
#include "test_main.hxx"
#include "simulator/missile/fdm/generic_missile_fdm.hxx"
#include "simulator/param_store.hxx"

static bvr_sim::ParamStore make_test_params() {
    std::string json_str = R"({
        "doubles": {
            "m0": 161.48, "dm": 6.41, "thrust": 16325.0,
            "t_thrust": 8.0, "S_ref": 0.0248719, "mach_min": 0.8,
            "nyz_max": 100.0, "g": 9.81
        },
        "tables": {
            "cx_total_table": {
                "x": [0.5, 1.0, 2.0, 3.0],
                "y": [0.47, 0.75, 0.72, 0.55]
            }
        }
    })";
    return bvr_sim::ParamStore::from_string(json_str);
}

TEST(GenericMissileFDM, ResetSetsInitialState) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    auto pos = fdm.get_position();
    ASSERT_NEAR(pos[2], 5000.0, 1e-6);
    ASSERT(fdm.get_speed() > 0.0);
}

TEST(GenericMissileFDM, StepAdvancesPosition) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    auto pos_before = fdm.get_position();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    auto pos_after = fdm.get_position();

    ASSERT(pos_after[0] > pos_before[0]);
}

TEST(GenericMissileFDM, PropulsionBurnsMass) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    ASSERT(fdm.is_thrusting());
    double mass_before = fdm.get_current_mass();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    ASSERT(fdm.get_current_mass() < mass_before);
}

TEST(GenericMissileFDM, MassConstantAfterBurnout) {
    auto params = make_test_params();
    bvr_sim::GenericMissileFDM fdm(params, 0.1);

    std::map<std::string, std::any> init;
    init["position"] = std::array<double,3>{0.0, 0.0, 5000.0};
    init["velocity"] = std::array<double,3>{300.0, 0.0, 0.0};
    init["pitch"] = double(0.0);
    init["yaw"]   = double(0.0);
    init["roll"]  = double(0.0);
    fdm.reset(init);

    // Step past t_thrust (8.0s at dt=0.1 = 80 steps)
    for (int i = 0; i < 85; ++i)
        fdm.step({{"ny", 0.0}, {"nz", 0.0}});

    ASSERT(!fdm.is_thrusting());
    double mass1 = fdm.get_current_mass();
    fdm.step({{"ny", 0.0}, {"nz", 0.0}});
    ASSERT_NEAR(fdm.get_current_mass(), mass1, 1e-9);
}
```

- [ ] **Step 3: Add test AND implementation files to `bvr_sim_unit_tests` target in CMakeLists.txt**

Add both the implementation and test file to the unit test target (note: `param_store.cxx` must also be present as a transitive dependency):

```cmake
add_executable(bvr_sim_unit_tests
    test_main.cxx
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/param_store.cxx"          # already added in Task 2
    "${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm/generic_missile_fdm.cxx"   # <-- add
    "${CMAKE_CURRENT_SOURCE_DIR}/test_generic_missile_fdm.cxx"        # <-- add
)
```

- [ ] **Step 4: Create `generic_missile_fdm.hxx`**

```cpp
#pragma once

#include "simulator/aircraft/fdm/base.hxx"
#include "simulator/param_store.hxx"
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

// ParamStore already brings in ::InterpTable via using ::InterpTable

/// Generic missile flight dynamics model.
/// Handles aerodynamics (Mach-indexed drag), kinematics (Euler integration),
/// and propulsion (thrust + mass burn).
/// Receives ny/nz acceleration commands via step() — applied directly.
///
/// Gravity convention: nz is the aerodynamic normal load factor (g-units).
/// Gravity (-g in NWU Z) is applied separately as a world-frame constant.
///
/// Lifetime contract: the ParamStore reference must outlive this object.
/// Satisfied when both are owned by the same Missile class.
class GenericMissileFDM : public BaseFDM {
public:
    explicit GenericMissileFDM(const ParamStore& params, double dt = 0.1) noexcept;

    void reset(const std::map<std::string, std::any>& initial_state) override;

    /// action keys:
    ///   "ny" (double) — lateral acceleration command (g-units)
    ///   "nz" (double) — longitudinal/normal acceleration command (g-units)
    void step(const std::map<std::string, double>& action) override;

    double get_current_mass()  const noexcept { return m_; }
    double get_elapsed_time()  const noexcept { return t_; }
    bool   is_thrusting()      const noexcept { return t_ < t_thrust_cached_; }

private:
    const ParamStore& params_;

    // Propulsion state
    double t_;               // elapsed time (s) — incremented at end of step()
    double m_;               // current mass (kg)
    double t_thrust_cached_; // cached from params (hot path)

    // Cached params (extracted once in _cache_params for hot path)
    double m0_, dm_, thrust_, S_ref_, mach_min_, nyz_max_, g_;

    void   _cache_params() noexcept;
    void   _update_propulsion(double dt_step) noexcept;
    double _compute_drag_accel() const noexcept;
    void   _integrate(double ny, double nz) noexcept;
};

} // namespace bvr_sim
```

- [ ] **Step 5: Create `generic_missile_fdm.cxx`**

```cpp
#include "generic_missile_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using c3utils::get_mps;
using c3utils::linalg_norm;

GenericMissileFDM::GenericMissileFDM(const ParamStore& params, double dt) noexcept
    : BaseFDM(dt), params_(params),
      t_(0.0), m_(0.0), t_thrust_cached_(0.0),
      m0_(0.0), dm_(0.0), thrust_(0.0), S_ref_(0.0),
      mach_min_(0.0), nyz_max_(0.0), g_(9.81)
{
    _cache_params();
    m_ = m0_;
}

void GenericMissileFDM::_cache_params() noexcept {
    m0_             = params_.get_double("m0").value_or(161.48);
    dm_             = params_.get_double("dm").value_or(6.41);
    thrust_         = params_.get_double("thrust").value_or(16325.0);
    t_thrust_cached_= params_.get_double("t_thrust").value_or(8.0);
    S_ref_          = params_.get_double("S_ref").value_or(0.0248719);
    mach_min_       = params_.get_double("mach_min").value_or(0.8);
    nyz_max_        = params_.get_double("nyz_max").value_or(100.0);
    g_              = params_.get_double("g").value_or(9.81);
}

void GenericMissileFDM::reset(const std::map<std::string, std::any>& initial_state) {
    if (initial_state.count("position"))
        position = std::any_cast<std::array<double,3>>(initial_state.at("position"));
    if (initial_state.count("velocity"))
        velocity = std::any_cast<std::array<double,3>>(initial_state.at("velocity"));
    if (initial_state.count("pitch"))
        pitch = std::any_cast<double>(initial_state.at("pitch"));
    if (initial_state.count("yaw"))
        yaw = std::any_cast<double>(initial_state.at("yaw"));
    if (initial_state.count("roll"))
        roll = std::any_cast<double>(initial_state.at("roll"));

    t_ = 0.0;
    m_ = m0_;
    terminate = false;
}

void GenericMissileFDM::step(const std::map<std::string, double>& action) {
    double ny = 0.0, nz = 0.0;
    if (action.count("ny")) ny = action.at("ny");
    if (action.count("nz")) nz = action.at("nz");

    ny = std::clamp(ny, -nyz_max_, nyz_max_);
    nz = std::clamp(nz, -nyz_max_, nyz_max_);

    _update_propulsion(dt);
    _integrate(ny, nz);

    t_ += dt;  // increment AFTER physics (consistent with original MModelA _t += dt at step start)
}

void GenericMissileFDM::_update_propulsion(double dt_step) noexcept {
    if (t_ < t_thrust_cached_) {
        m_ = std::max(m_ - dm_ * dt_step, m0_ - dm_ * t_thrust_cached_);
    }
}

double GenericMissileFDM::_compute_drag_accel() const noexcept {
    double speed = get_speed();
    if (speed < 1e-6) return 0.0;

    double alt = position[2];
    double sound_speed = get_mps(1.0, alt);
    double mach = speed / sound_speed;
    mach = std::max(mach, mach_min_);

    auto cx_opt = params_.get_interp_table("cx_total_table");
    double cx = cx_opt ? (*cx_opt)->interpolate(mach) : 0.3;

    double rho = 1.225 * std::exp(-alt / 9300.0);
    double drag_force = 0.5 * rho * speed * speed * cx * S_ref_;
    return drag_force / m_;
}

void GenericMissileFDM::_integrate(double ny, double nz) noexcept {
    double speed = get_speed();
    if (speed < 1e-6) return;

    double cos_pitch = std::cos(pitch);
    double sin_pitch = std::sin(pitch);
    double cos_yaw   = std::cos(yaw);
    double sin_yaw   = std::sin(yaw);

    // Body-axis unit vectors (NWU frame)
    // Forward (longitudinal)
    std::array<double,3> fwd = {cos_pitch * cos_yaw, cos_pitch * sin_yaw, -sin_pitch};
    // Lateral (y-body, 90° from fwd in horizontal plane)
    std::array<double,3> lat = {-sin_yaw, cos_yaw, 0.0};
    // Normal (z-body = cross(fwd, lat))
    std::array<double,3> nrm = {sin_pitch * cos_yaw, sin_pitch * sin_yaw, cos_pitch};

    double thrust_acc = (t_ < t_thrust_cached_) ? thrust_ / m_ : 0.0;
    double drag_acc   = _compute_drag_accel();

    // Aerodynamic acceleration (body frame contributions → world frame)
    // ny/nz are aerodynamic load factors (g-units); gravity added separately below
    std::array<double,3> aero_accel = {
        fwd[0] * (thrust_acc - drag_acc) + lat[0] * (ny * g_) + nrm[0] * (nz * g_),
        fwd[1] * (thrust_acc - drag_acc) + lat[1] * (ny * g_) + nrm[1] * (nz * g_),
        fwd[2] * (thrust_acc - drag_acc) + lat[2] * (ny * g_) + nrm[2] * (nz * g_)
    };

    // Gravity: constant world-frame force (NWU: -Z is down)
    velocity[0] += (aero_accel[0])       * dt;
    velocity[1] += (aero_accel[1])       * dt;
    velocity[2] += (aero_accel[2] - g_)  * dt;  // gravity acts in -Z (NWU)

    position[0] += velocity[0] * dt;
    position[1] += velocity[1] * dt;
    position[2] += velocity[2] * dt;

    // Update attitude from velocity direction
    double vspeed = linalg_norm(velocity);
    if (vspeed > 1e-6) {
        yaw   = std::atan2(velocity[1], velocity[0]);
        pitch = std::asin(-velocity[2] / vspeed);
    }
}

} // namespace bvr_sim
```

- [ ] **Step 6: Add new files to CMakeLists.txt**

In `BVR_SIM_SOURCES`:
```cmake
"${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm/generic_missile_fdm.cxx"
```

In `BVR_SIM_INCLUDE_DIRS`:
```cmake
"${CMAKE_CURRENT_SOURCE_DIR}/simulator/missile/fdm"
```

- [ ] **Step 7: Build and run tests — all GenericMissileFDM tests should pass**

```bash
cd bvr_sim && ./build_windows.bat
cd tests && python cpp_unit_tests.py
```

Expected: `GenericMissileFDM::*` tests all PASS.

- [ ] **Step 8: Commit**

```bash
git add bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.hxx \
        bvr_sim/src_cxx/simulator/missile/fdm/generic_missile_fdm.cxx \
        bvr_sim/src_cxx/test_generic_missile_fdm.cxx \
        bvr_sim/src_cxx/CMakeLists.txt
git commit -m "feat: add GenericMissileFDM physics engine + tests"
```

---

## Task 4: Refactor MModelA to use ParamStore + GenericMissileFDM

**Files:**
- Modify: `bvr_sim/src_cxx/simulator/missile/mmodelA.hxx`
- Modify: `bvr_sim/src_cxx/simulator/missile/mmodelA.cxx`

**Key design notes:**
- `params_` is owned by MModelA; `fdm_` holds a `const ParamStore&` to `params_`. Order in member initializer list: `params_` must be initialized before `fdm_`.
- FDM state (position, velocity) is synced into `SimulatedObject` base **after** `fdm_.step()`, not before.
- `speed` and `posture` fields from old MModelA are removed — use `fdm_.get_speed()`, `fdm_.get_rpy()`.
- **Pitch/yaw sign convention:** The FDM stores pitch/yaw as the missile's own body angles (positive pitch = nose up in NWU). The constructor negates `init_pitch` and `init_yaw` when calling `fdm_.reset()` because `aircraft->get_pitch()` returns the parent aircraft's angle in the aircraft body convention (positive = nose up), while the FDM's `_integrate()` derives attitude from velocity via `pitch = asin(-velocity[2]/speed)` — which gives positive pitch for upward motion. The negation converts between conventions. Attitude is not synced back to `SimulatedObject` (only position and velocity are).

- [ ] **Step 1: Update `mmodelA.hxx`**

```cpp
#pragma once

#include "base.hxx"
#include "simulator/param_store.hxx"
#include "simulator/missile/fdm/generic_missile_fdm.hxx"
#include <array>
#include <optional>
#include <deque>

namespace bvr_sim {

class MModelA : public Missile {
public:
    MModelA(
        const std::string& uid,
        const std::string& missile_model,
        TeamColor color,
        const std::shared_ptr<SimulatedObject>& parent,
        const std::shared_ptr<SimulatedObject>& friend_obj,
        const std::shared_ptr<SimulatedObject>& target,
        double dt
    ) noexcept;

    void step() noexcept override;

    const ParamStore& get_params() const noexcept { return params_; }

public:
    // ===== Seeker state =====
    double radar_pitch, radar_yaw;
    bool guide_cmd_valid;

    // ===== Signal loss handling =====
    double losstime;
    bool loss;
    std::array<double, 3> _before_loss_real_last_known_target_pos;

    // ===== Guidance commands (outputs from update_guidance) =====
    std::optional<double> L_beta;
    std::optional<double> L_eps;
    std::optional<double> _dbeta_filtered;

private:
    // params_ MUST be declared before fdm_ — initializer list order matters
    ParamStore         params_;   // owned by MModelA
    GenericMissileFDM  fdm_;      // holds const ref to params_

    // ===== Mission state =====
    bool              _search_started;
    double            _distance_pre;
    std::deque<bool>  _distance_increment;
    int               _left_t;

    std::pair<double, double> update_guidance() noexcept;

    static ParamStore _make_params(const std::string& missile_model) noexcept;
};

} // namespace bvr_sim
```

- [ ] **Step 2: Update `mmodelA.cxx`**

```cpp
#include "mmodelA.hxx"
#include "../aircraft/base.hxx"
#include "../ground/base.hxx"
#include "../ground/aa.hxx"
#include "../simulator.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>
#include <limits>

namespace bvr_sim {

using c3utils::linalg_norm;
using c3utils::get_mps;
// Note: velocity_to_euler is in bvr_sim namespace (from simulator.hxx), not c3utils

// ─── Parameter factory ────────────────────────────────────────────────────────

ParamStore MModelA::_make_params(const std::string& missile_model) noexcept {
    if (missile_model == "AIM-120C7" || missile_model == "AIM-120C" ||
        missile_model == "AIM-120C5" || missile_model == "AIM-120") {

        const std::string json_str = R"({
            "doubles": {
                "m0":                    161.48,
                "dm":                    6.41,
                "thrust":                16325.0,
                "t_thrust":              8.0,
                "t_max":                 300.0,
                "S_ref":                 0.0248719,
                "mach_min":              0.8,
                "nyz_max":               100.0,
                "g":                     9.81,
                "Rc":                    152.4,
                "K":                     3.0,
                "search_fov":            0.349066,
                "search_range":          27780.0,
                "search_start_range":    18520.0,
                "track_gimbal_limit":    1.5708,
                "loss_time_threshold":   1.0
            },
            "strings": {
                "enable_search": "true",
                "enable_track":  "true",
                "enable_loft":   "false"
            },
            "tables": {
                "cx_total_table": {
                    "x": [0.0,  0.2,   0.4,   0.6,   0.8,   1.0,   1.2,   1.4,
                          1.6,  1.8,   2.0,   2.2,   2.4,   2.6,   2.8,   3.0,
                          3.2,  3.4,   3.6,   3.8,   4.0,   4.2,   4.4,   4.6,
                          4.8,  5.0],
                    "y": [0.468, 0.468, 0.468, 0.468, 0.479, 0.751, 0.88,  0.8572,
                          0.8132,0.7645,0.7205,0.6808,0.6447,0.6119,0.582, 0.5545,
                          0.5292,0.5057,0.4838,0.4633,0.4439,0.4256,0.4083,0.3921,
                          0.377, 0.364]
                }
            }
        })";
        return ParamStore::from_string(json_str);
    }
    colorful::printHONG("[MModelA] Unknown missile model: " + missile_model + ", returning empty ParamStore");
    return ParamStore{};
}

// ─── Constructor ──────────────────────────────────────────────────────────────

MModelA::MModelA(
    const std::string& uid,
    const std::string& missile_model,
    TeamColor color,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& friend_obj,
    const std::shared_ptr<SimulatedObject>& target,
    double dt
) noexcept
    : Missile(uid, missile_model, color, parent, friend_obj, target, dt),
      params_(_make_params(missile_model)),   // params_ first
      fdm_(params_, dt),                      // fdm_ second (holds ref to params_)
      radar_pitch(0.0),
      radar_yaw(0.0),
      guide_cmd_valid(true),
      losstime(0.0),
      loss(false),
      _search_started(false),
      _distance_pre(std::numeric_limits<double>::infinity()),
      _left_t(static_cast<int>(1.0 / dt)),
      _before_loss_real_last_known_target_pos{0.0, 0.0, 0.0}
{
    for (int i = 0; i < 20; ++i) _distance_increment.push_back(false);

    double init_pitch = 0.0, init_yaw = 0.0;

    if (parent->Type == SOT::Aircraft) {
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(parent);
        check(aircraft, "dynamic cast failed");
        init_pitch = aircraft->get_pitch();
        init_yaw   = aircraft->get_heading();
    } else if (parent->Type == SOT::AA) {
        auto aa = std::dynamic_pointer_cast<AA>(parent);
        check(aa, "dynamic cast failed");
        check(target->Type == SOT::Aircraft, "MModelA target must be Aircraft when fired from AA");
        auto target_aircraft = std::dynamic_pointer_cast<Aircraft>(target);
        check(target_aircraft, "dynamic cast failed");
        auto vel = aa->get_launch_velocity(target_aircraft);
        auto [roll_v, pitch_v, heading_v] = velocity_to_euler(vel);
        init_pitch = pitch_v;
        init_yaw   = heading_v;
        velocity   = vel;
    } else {
        check(false, "MModelA must be parented by an Aircraft or AA");
    }

    std::map<std::string, std::any> init_state;
    init_state["position"] = std::array<double,3>{position[0], position[1], position[2]};
    init_state["velocity"] = std::array<double,3>{velocity[0], velocity[1], velocity[2]};
    init_state["pitch"]    = double(-init_pitch);
    init_state["yaw"]      = double(-init_yaw);
    init_state["roll"]     = double(0.0);
    fdm_.reset(init_state);
}

// ─── Step ─────────────────────────────────────────────────────────────────────

void MModelA::step() noexcept {
    if (!is_alive) return;
    if (!target)   return;

    update_target_info();

    // Use current (pre-step) position for termination checks
    double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    _distance_increment.push_back(distance > _distance_pre);
    _distance_pre = distance;

    double elapsed  = fdm_.get_elapsed_time();
    double speed    = fdm_.get_speed();
    double t_max    = params_.get_double("t_max").value_or(300.0);
    double t_thrust = params_.get_double("t_thrust").value_or(8.0);
    double v_min    = get_mps(params_.get_double("mach_min").value_or(0.8), position[2]);
    double Rc       = params_.get_double("Rc").value_or(152.4);

    bool timeout             = elapsed > t_max;
    bool crash               = position[2] < 0.0;
    bool too_slow            = (elapsed > t_thrust && speed < v_min);
    bool farther_and_farther = (_distance_increment.size() == _distance_increment.max_size() &&
                                std::count(_distance_increment.begin(), _distance_increment.end(), true) >=
                                static_cast<int>(_distance_increment.max_size()));
    bool target_down         = !(target && target->is_alive);

    if (distance < Rc && target && target->is_alive) {
        if (target->Type == SOT::Aircraft) {
            auto aircraft = std::dynamic_pointer_cast<Aircraft>(target);
            check(aircraft, "[MModelA] dynamic cast failed");
            aircraft->hit();
        } else if (target->Type == SOT::GroundUnit) {
            auto ground = std::dynamic_pointer_cast<GroundUnit>(target);
            check(ground, "[MModelA] dynamic cast failed");
            if (ground->check_collision(position)) ground->hit();
            else ground->hit(10.0);
        }
        is_success = true;
        is_done    = true;
        log_done_reason = "hit";
    } else if (timeout || crash || too_slow || farther_and_farther || target_down) {
        is_success = false;
        is_done    = true;
        if (timeout)              log_done_reason = "timeout";
        else if (crash)           log_done_reason = "crash";
        else if (too_slow)        log_done_reason = "too_slow " + std::to_string(speed) + " < " + std::to_string(v_min);
        else if (farther_and_farther) log_done_reason = "farther_and_farther_away";
        else if (target_down)     log_done_reason = "target_down";
    } else {
        auto [cmd_beta, cmd_eps] = update_guidance();
        fdm_.step({{"ny", cmd_beta}, {"nz", cmd_eps}});

        // Sync FDM state into SimulatedObject base AFTER physics step
        auto fdm_pos = fdm_.get_position();
        auto fdm_vel = fdm_.get_velocity();
        position[0] = fdm_pos[0]; position[1] = fdm_pos[1]; position[2] = fdm_pos[2];
        velocity[0] = fdm_vel[0]; velocity[1] = fdm_vel[1]; velocity[2] = fdm_vel[2];
    }

    if (is_done) is_alive = false;
}

std::pair<double, double> MModelA::update_guidance() noexcept {
    // TODO: Implement proportional navigation guidance
    return {0.0, 0.0};
}

} // namespace bvr_sim
```

- [ ] **Step 3: Build**

```bash
cd bvr_sim && ./build_windows.bat
```

Expected: build succeeds.

- [ ] **Step 4: Smoke test**

```bash
python -c "
from example.env_wrapper import make_env, ScenarioConfig
cfg = ScenarioConfig(render=False)
env = make_env(cfg)
obs, info = env.reset()
for _ in range(100):
    obs, reward, done, truncated, info = env.step(env.action_space.sample())
    if done or truncated:
        break
print('Smoke test passed')
"
```

Expected: `Smoke test passed` without exception.

- [ ] **Step 5: Run full test suite**

```bash
cd tests && python test_everything.py
```

Expected: all tests pass.

- [ ] **Step 6: Verify MissileParams still intact**

```bash
grep -rn "MissileParams" bvr_sim/src_cxx/simulator/ --include="*.cxx" --include="*.hxx"
```

Expected: `aim120c.hxx/.cxx` and `missile_params.hxx/.cxx` still reference it. `mmodelA.hxx/.cxx` should NOT appear.

- [ ] **Step 7: Commit**

```bash
git add bvr_sim/src_cxx/simulator/missile/mmodelA.hxx \
        bvr_sim/src_cxx/simulator/missile/mmodelA.cxx
git commit -m "refactor: replace MissileParams with ParamStore+GenericMissileFDM in MModelA"
```

---

## Summary of New Files

| File | Purpose |
|------|---------|
| `rubbish_can/interp_table.hxx` | Added `to_json()` / `from_json()` |
| `simulator/param_store.hxx` | New typed parameter store |
| `simulator/param_store.cxx` | ParamStore implementation + JSON serialization |
| `test_param_store.cxx` | Unit tests for ParamStore (uses project `TEST()` macro) |
| `simulator/missile/fdm/generic_missile_fdm.hxx` | Generic missile FDM interface |
| `simulator/missile/fdm/generic_missile_fdm.cxx` | Aero + kinematics + propulsion physics |
| `test_generic_missile_fdm.cxx` | Unit tests for GenericMissileFDM |
| `simulator/missile/mmodelA.hxx` | Refactored: owns `ParamStore` + `GenericMissileFDM` |
| `simulator/missile/mmodelA.cxx` | Init from JSON string; delegates physics to `fdm_` |

## Usage Pattern for MModelB

When implementing `MModelB`, the pattern is:

```cpp
// In mmodelB.cxx — only _make_params() changes
ParamStore MModelB::_make_params(const std::string& model) noexcept {
    const std::string json_str = R"({
        "doubles": { "m0": 120.0, "thrust": 12000.0, ... },
        "tables":  { "cx_total_table": { "x": [...], "y": [...] } }
    })";
    return ParamStore::from_string(json_str);
}
// fdm_(params_, dt) in CTOR initializer list — identical to MModelA
```

`GenericMissileFDM` is reused unchanged.
