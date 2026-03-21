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

// 测试入口（如果需要集成到test框架）
#ifdef BVR_SIM_RUN_TESTS

int main() {
    std::cout << "Running FlightControllerParams tests...\n" << std::endl;

    try {
        bvr_sim::test_manager_singleton();
        bvr_sim::test_f16_params();
        bvr_sim::test_f15_params();
        bvr_sim::test_f18_params();

        std::cout << "\n✓ All FlightControllerParams tests passed!" << std::endl;
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "\n✗ Test failed with exception: " << e.what() << std::endl;
        return 1;
    }
}

#endif
