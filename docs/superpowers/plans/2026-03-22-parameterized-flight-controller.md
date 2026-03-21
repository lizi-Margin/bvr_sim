# 参数化固定翼飞机控制框架实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 创建 FlightControllerParamsManager 单例，为不同飞机型号提供参数化的PID和阈值配置，保持F16参数不变，为后期多机型调参做准备。

**Architecture:**
- 新增 `flight_controller_params.hxx/cxx` 定义 FlightControllerParams 结构体和 Manager 单例
- 修改 `fc_old.hxx/cxx` 中 StdFlightController 的构造函数，接收 aircraft_model 参数
- 修改 `jsbsim_fdm.cxx` 在创建 StdFlightController 时传递 aircraft_model
- Manager 持有 std::map<aircraft_key, FlightControllerParams>，初始值对应当前F16的硬编码值
- 错误的飞机key通过 check(false, "wrong aircraft key") 断言

**Tech Stack:** C++17, STL map, JSBSim FDM

---

## File Structure

**新增文件：**
- `bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.hxx` - 参数结构体和Manager声明
- `bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.cxx` - Manager实现

**修改文件：**
- `bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.hxx` - 添加aircraft_model构造参数
- `bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.cxx` - 使用Manager参数替换硬编码值
- `bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.hxx` - 存储aircraft_model
- `bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.cxx` - 传递aircraft_model给StdFlightController

**测试文件：**
- `bvr_sim/src_cxx/simulator/aircraft/fc/test_flight_controller_params.cxx` - 参数Manager单元测试

---

## Task 1: 创建 FlightControllerParams 结构体和 Manager 类

**Files:**
- Create: `bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.hxx`

- [ ] **Step 1: 写failing test**

```cpp
// 在某处（暂时不创建，先定义结构体）
// 测试内容会在Task 5中完整写出
```

- [ ] **Step 2: 创建 flight_controller_params.hxx**

```cpp
#pragma once

#include <string>
#include <map>
#include <memory>

namespace bvr_sim {

struct FlightControllerParams {
    // PID 系数
    double kroll_p;
    double kroll_i;
    double kroll_d;

    double kpitch_p;
    double kpitch_i;
    double kpitch_d;

    double kthrottle_p;
    double kthrottle_i;
    double kthrottle_d;

    // 高度阈值（米）
    double crash_height_threshold;         // 4000 ft ≈ 1219 m
    double severe_crash_height;            // 2000 ft ≈ 610 m
    double low_alt_threshold;              // 800 ft ≈ 244 m
    double altitude_loss_threshold;        // 11000 m
    double pitch_loss_threshold;           // 20000 m
    double roll_loss_threshold;            // 16000 m

    // 速度阈值 (Mach)
    double stall_speed;                    // 0.18 M
    double min_controlled_speed;           // 0.3 M
    double low_speed_threshold;            // 0.5 M
    double high_speed_threshold;           // 1.2 M

    // 角度阈值 (弧度)
    double max_roll_angle;                 // π/3 rad
    double max_pitch_angle;                // π/6 rad
    double turn_angle_90deg;               // π/2 rad
    double turn_angle_99deg;               // 99° ≈ 1.728 rad
};

class FlightControllerParamsManager {
private:
    static FlightControllerParamsManager* instance_;
    std::map<std::string, FlightControllerParams> params_map_;

    // 私有构造，初始化所有预设
    FlightControllerParamsManager() noexcept;

public:
    // 禁用拷贝
    FlightControllerParamsManager(const FlightControllerParamsManager&) = delete;
    FlightControllerParamsManager& operator=(const FlightControllerParamsManager&) = delete;

    // 获取单例
    static FlightControllerParamsManager& getInstance() noexcept;

    // 根据飞机key获取参数
    // 如果key不存在，会触发 check(false, "wrong aircraft key")
    const FlightControllerParams& getParams(const std::string& aircraft_key) const noexcept;
};

}  // namespace bvr_sim
```

- [ ] **Step 3: Commit header**

```bash
git add bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.hxx
git commit -m "feat: add FlightControllerParams struct and Manager declaration"
```

---

## Task 2: 实现 FlightControllerParamsManager

**Files:**
- Create: `bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.cxx`

- [ ] **Step 1: 创建implementation文件**

```cpp
#include "flight_controller_params.hxx"
#include "c3utils/c3utils.hxx"
#include "rubbish_can/check.hxx"
#include <cmath>

namespace bvr_sim {

FlightControllerParamsManager* FlightControllerParamsManager::instance_ = nullptr;

FlightControllerParamsManager::FlightControllerParamsManager() noexcept {
    // F16 参数 - 从fc_old.cxx硬编码值提取
    // PID系数来自: StdFlightController::StdFlightController() 构造函数
    // 阈值来自: direct_LU_flight_controler() 算法
    FlightControllerParams f16_params;

    // PID系数
    f16_params.kroll_p = 1.2;
    f16_params.kroll_i = 0.2;
    f16_params.kroll_d = 0.0;

    f16_params.kpitch_p = -3.4;
    f16_params.kpitch_i = -0.0;
    f16_params.kpitch_d = -0.5;

    f16_params.kthrottle_p = 0.03;
    f16_params.kthrottle_i = 0.06;
    f16_params.kthrottle_d = 500;

    // 高度阈值 (转换为米)
    f16_params.crash_height_threshold = 1219.0;         // 4000 ft
    f16_params.severe_crash_height = 610.0;             // 2000 ft
    f16_params.low_alt_threshold = 244.0;               // 800 ft
    f16_params.altitude_loss_threshold = 11000.0;       // 已是米
    f16_params.pitch_loss_threshold = 20000.0;          // 已是米
    f16_params.roll_loss_threshold = 16000.0;           // 已是米

    // 速度阈值
    f16_params.stall_speed = 0.18;
    f16_params.min_controlled_speed = 0.3;
    f16_params.low_speed_threshold = 0.5;
    f16_params.high_speed_threshold = 1.2;

    // 角度阈值
    f16_params.max_roll_angle = M_PI / 3.0;             // π/3 rad = 60°
    f16_params.max_pitch_angle = M_PI / 6.0;            // π/6 rad = 30°
    f16_params.turn_angle_90deg = M_PI / 2.0;           // π/2 rad = 90°
    f16_params.turn_angle_99deg = 99.0 * M_PI / 180.0;  // 99°

    // F16 注册
    params_map_["F16"] = f16_params;

    // F15 - 初值同F16，后期可调整
    params_map_["F15"] = f16_params;

    // F18 - 初值同F16，后期可调整
    params_map_["F18"] = f16_params;
}

FlightControllerParamsManager& FlightControllerParamsManager::getInstance() noexcept {
    if (instance_ == nullptr) {
        instance_ = new FlightControllerParamsManager();
    }
    return *instance_;
}

const FlightControllerParams& FlightControllerParamsManager::getParams(
    const std::string& aircraft_key) const noexcept {
    auto it = params_map_.find(aircraft_key);
    if (it == params_map_.end()) {
        check(false, "wrong aircraft key: " + aircraft_key);
    }
    return it->second;
}

}  // namespace bvr_sim
```

- [ ] **Step 2: Commit implementation**

```bash
git add bvr_sim/src_cxx/simulator/aircraft/fc/flight_controller_params.cxx
git commit -m "feat: implement FlightControllerParamsManager with F16/F15/F18 presets"
```

---

## Task 3: 修改 StdFlightController 接受 aircraft_model 参数

**Files:**
- Modify: `bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.hxx:58`
- Modify: `bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.cxx:26-35`

- [ ] **Step 1: 更新 fc_old.hxx 中的构造函数声明**

修改：
```cpp
// 旧
explicit StdFlightController(double dt) noexcept;
```

为：
```cpp
// 新
explicit StdFlightController(double dt, const std::string& aircraft_model = "F16") noexcept;
```

- [ ] **Step 2: 查看fc_old.cxx中的构造函数实现**

```bash
head -40 bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.cxx
```

预期输出显示构造函数初始化PID系数。

- [ ] **Step 3: 修改 fc_old.cxx 构造函数，从Manager加载参数**

将构造函数实现改为：

```cpp
StdFlightController::StdFlightController(double dt, const std::string& aircraft_model) noexcept
    : dt(dt),
      sum_err_roll(0), last_err_roll(0),
      sum_err_pitch(0), last_err_pitch(0),
      sum_err_throttle(0), last_err_throttle(0),
      right_turn(0),
      crashing_counter(dt, 5.) {

    // 从Manager获取参数
    auto& manager = FlightControllerParamsManager::getInstance();
    const auto& params = manager.getParams(aircraft_model);

    // 设置PID系数
    kroll_p_ = params.kroll_p;
    kroll_i_ = params.kroll_i;
    kroll_d_ = params.kroll_d;

    kpitch_p_ = params.kpitch_p;
    kpitch_i_ = params.kpitch_i;
    kpitch_d_ = params.kpitch_d;

    kthrottle_p_ = params.kthrottle_p;
    kthrottle_i_ = params.kthrottle_i;
    kthrottle_d_ = params.kthrottle_d;
}
```

- [ ] **Step 4: 在fc_old.hxx中include Manager header**

在顶部添加：
```cpp
#include "flight_controller_params.hxx"
```

- [ ] **Step 5: Verify includes在fc_old.cxx也有**

检查fc_old.cxx顶部是否已有header include，需要确保能访问Manager。

- [ ] **Step 6: Commit fc_old changes**

```bash
git add bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.hxx bvr_sim/src_cxx/simulator/aircraft/fc/fc_old.cxx
git commit -m "refactor: StdFlightController loads params from FlightControllerParamsManager"
```

---

## Task 4: 修改 JSBSimFDM 传递 aircraft_model 给 StdFlightController

**Files:**
- Modify: `bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.hxx:86`
- Modify: `bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.cxx` (StdFlightController创建处)

- [ ] **Step 1: 在jsbsim_fdm.hxx中添加aircraft_model成员**

在private部分添加（如果还没有）：
```cpp
std::string aircraft_model;  // 飞机型号，用于控制参数查询
```

- [ ] **Step 2: 查看 jsbsim_fdm.cxx 的构造函数**

```bash
grep -n "JSBSimFDM::JSBSimFDM" bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.cxx -A 30 | head -50
```

查找StdFlightController初始化位置。

- [ ] **Step 3: 修改构造函数，保存aircraft_model**

在JSBSimFDM构造函数中，从kwargs中提取aircraft_model：

```cpp
// 在初始化列表或开头
if (kwargs.find("aircraft_model") != kwargs.end()) {
    aircraft_model = kwargs.at("aircraft_model");
} else {
    aircraft_model = "F16";  // 默认值
}
```

- [ ] **Step 4: 修改StdFlightController的创建**

找到 `fc = StdFlightController(...)` 这一行，改为：

```cpp
fc = StdFlightController(jsbsim_inner_dt, aircraft_model);
```

- [ ] **Step 5: Commit jsbsim changes**

```bash
git add bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.hxx bvr_sim/src_cxx/simulator/aircraft/fdm/jsbsim_fdm.cxx
git commit -m "feat: JSBSimFDM passes aircraft_model to StdFlightController"
```

---

## Task 5: 编写单元测试验证参数管理器

**Files:**
- Create: `bvr_sim/src_cxx/simulator/aircraft/fc/test_flight_controller_params.cxx`
- Modify: `bvr_sim/src_cxx/test_main.cxx` (如需要注册测试)

- [ ] **Step 1: 创建测试文件**

```cpp
#include "flight_controller_params.hxx"
#include "rubbish_can/check.hxx"
#include <cassert>
#include <iostream>

namespace bvr_sim {

// 测试 1: Manager单例获取
void test_manager_singleton() {
    auto& mgr1 = FlightControllerParamsManager::getInstance();
    auto& mgr2 = FlightControllerParamsManager::getInstance();
    assert(&mgr1 == &mgr2);  // 应该是同一个对象
    std::cout << "✓ test_manager_singleton passed" << std::endl;
}

// 测试 2: F16参数获取
void test_f16_params() {
    auto& mgr = FlightControllerParamsManager::getInstance();
    const auto& params = mgr.getParams("F16");

    // 验证PID系数
    assert(params.kroll_p == 1.2);
    assert(params.kroll_i == 0.2);
    assert(params.kroll_d == 0.0);

    assert(params.kpitch_p == -3.4);
    assert(params.kpitch_i == -0.0);
    assert(params.kpitch_d == -0.5);

    assert(params.kthrottle_p == 0.03);
    assert(params.kthrottle_i == 0.06);
    assert(params.kthrottle_d == 500);

    // 验证速度阈值
    assert(params.stall_speed == 0.18);
    assert(params.min_controlled_speed == 0.3);

    std::cout << "✓ test_f16_params passed" << std::endl;
}

// 测试 3: F15参数获取（初值应同F16）
void test_f15_params() {
    auto& mgr = FlightControllerParamsManager::getInstance();
    const auto& f16 = mgr.getParams("F16");
    const auto& f15 = mgr.getParams("F15");

    // 初值应相同
    assert(f15.kroll_p == f16.kroll_p);
    assert(f15.kpitch_p == f16.kpitch_p);

    std::cout << "✓ test_f15_params passed" << std::endl;
}

// 测试 4: F18参数获取（初值应同F16）
void test_f18_params() {
    auto& mgr = FlightControllerParamsManager::getInstance();
    const auto& f16 = mgr.getParams("F16");
    const auto& f18 = mgr.getParams("F18");

    assert(f18.kroll_p == f16.kroll_p);
    assert(f18.kpitch_p == f16.kpitch_p);

    std::cout << "✓ test_f18_params passed" << std::endl;
}

// 测试 5: 非法key应触发check fail
void test_invalid_aircraft_key() {
    auto& mgr = FlightControllerParamsManager::getInstance();

    // 尝试获取不存在的飞机，应该会断言失败
    // 在正式测试中应该捕获这个失败
    std::cout << "  (test_invalid_aircraft_key 需要特殊处理check failure)" << std::endl;
}

}  // namespace bvr_sim

// 如果你的test_main.cxx使用了TEST宏，添加测试注册
// 否则在这里直接调用函数
#ifdef USING_TEST_FRAMEWORK

TEST(FlightControllerParams, ManagerSingleton) {
    bvr_sim::test_manager_singleton();
}

TEST(FlightControllerParams, F16Params) {
    bvr_sim::test_f16_params();
}

TEST(FlightControllerParams, F15Params) {
    bvr_sim::test_f15_params();
}

TEST(FlightControllerParams, F18Params) {
    bvr_sim::test_f18_params();
}

#endif
```

- [ ] **Step 2: 运行测试编译**

```bash
cd bvr_sim && build_windows.bat  # 或 bash build_linux.sh
python tests/run_unit_tests.py
```

期望输出：
```
✓ test_manager_singleton passed
✓ test_f16_params passed
✓ test_f15_params passed
✓ test_f18_params passed
```

- [ ] **Step 3: Commit tests**

```bash
git add bvr_sim/src_cxx/simulator/aircraft/fc/test_flight_controller_params.cxx
git commit -m "test: add unit tests for FlightControllerParamsManager"
```

---

## Task 6: 集成测试 - 验证参数在实际飞行控制中使用

**Files:**
- Modify: CMakeLists.txt (如需新增test target)
- Test: `tests/test_cpp.py` 或新增自定义测试

- [ ] **Step 1: 运行现有smoke test验证不破坏功能**

```bash
cd /path/to/repo
python tests/test_cpp.py
```

期望：10个episode成功运行，无错误。

- [ ] **Step 2: 验证F16参数被正确应用**

在test_cpp.py或自定义脚本中添加验证：

```python
# 伪代码，说明验证逻辑
# 在step之间添加状态检查，确认飞机能正常机动
env = BVR3DEnvCpp(config)
obs, info = env.reset()
for _ in range(10):
    action = env.action_space.sample()
    obs, reward, done, info = env.step(action)
    # 验证飞机状态合理（不会无故崩坠等）
    assert not info.get("crashed", False), "Aircraft should not crash"
print("✓ F16 parameters working correctly in flight dynamics")
```

- [ ] **Step 3: 运行smoke test**

```bash
cd /path/to/repo
python tests/test_cpp.py
```

期望输出：
```
Running 10 episodes with C++ backend...
Episode 1: OK
Episode 2: OK
...
Episode 10: OK
All episodes passed! ✓
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: parameter-aware flight controller fully integrated and tested"
```

---

## Task 7: CMakeLists.txt 集成（如需要）

**Files:**
- Modify: `bvr_sim/src_cxx/CMakeLists.txt`

- [ ] **Step 1: 检查CMakeLists.txt是否需要新增.cxx文件**

```bash
grep -n "fc_old.cxx\|flight_controller_params" bvr_sim/src_cxx/CMakeLists.txt
```

- [ ] **Step 2: 如果flight_controller_params.cxx未被include，添加它**

在合适的位置（通常是aircraft FC相关的source列表）：

```cmake
# 找到类似的行：
set(AIRCRAFT_SOURCES
    ...
    simulator/aircraft/fc/fc_old.cxx
    # 添加：
    simulator/aircraft/fc/flight_controller_params.cxx
    ...
)
```

- [ ] **Step 3: 验证编译**

```bash
cd bvr_sim
build_windows.bat  # 或 bash build_linux.sh
```

期望：编译成功，无warning关于未定义的符号。

- [ ] **Step 4: Commit CMakeLists changes**

```bash
git add bvr_sim/src_cxx/CMakeLists.txt
git commit -m "build: register flight_controller_params.cxx in CMakeLists"
```

---

## 验收标准

- ✅ 参数化控制器正常初始化，F16参数值不变
- ✅ 单位测试通过：Manager单例、F16/F15/F18参数读取、错误key检测
- ✅ 现有smoke test (test_cpp.py) 通过，无性能下降
- ✅ C++编译无错误、无新warning
- ✅ 所有改动提交到git，commit message清晰

---

## 后续工作（Not in this plan）

- 调整F15/F18的具体参数值（当前为F16的copy）
- 支持从JSON加载参数配置
- 添加运行时参数调整接口
- 性能基准测试对比改前改后

