#pragma once

#include <string>
#include <map>
#include <memory>
#include "rubbish_can/check.hxx"

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

    // PID 积分作用阈值和限制
    double roll_integral_threshold;        // Roll integral action threshold (0.32 rad)
    double roll_integral_clamp;            // Roll integral clamping limit (2.5)
    double pitch_integral_threshold;       // Pitch integral action threshold (π/6 rad)
    double pitch_integral_deadband;        // Pitch integral deadband (π/90 rad)
    double pitch_integral_clamp;           // Pitch integral clamping limit (8.0)
    double throttle_integral_clamp;        // Throttle integral clamping limit (10.0)

    // 油门基值计算参数
    double throttle_base_value;            // Initial throttle base (0.5)
    double throttle_altitude_threshold;    // Altitude for throttle adjustment (7500 m)
    double throttle_altitude_coefficient;  // Coefficient for altitude-based adjustment (0.5)
    double throttle_mach_threshold;        // Mach threshold for throttle boost (1.0)
    double throttle_altitude_limit;        // Altitude limit for pitch-based adjustment (10000 m)
    double throttle_pitch_coefficient;     // Coefficient for pitch-based adjustment (0.4)
    double throttle_pitch_divisor;         // Divisor for pitch angle (π/2 rad)
    double low_mach_throttle_threshold;    // Low mach threshold (0.7)
    double max_throttle;                   // Maximum throttle value (1.0)
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
