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
