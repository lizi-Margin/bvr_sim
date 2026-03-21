#pragma once

#include <array>
#include "c3utils/c3utils.hxx"

namespace bvr_sim {

using c3utils::Vector3;

struct FighterState {
    double roll;
    double pitch;
    double yaw;
    double mach;
    double vd;
    double height;
    c3utils::Vector3 heading;
};

class CrashingCounter {
private:
    double dt;
    double max_time;
    double timer;

public:
    CrashingCounter(double dt, double max_time = 1.0) noexcept;
    bool update(bool crashing) noexcept;
};

class StdFlightController {
private:
    double kroll_p_;
    double kroll_i_;
    double kroll_d_;

    double kpitch_p_;
    double kpitch_i_;
    double kpitch_d_;

    double kthrottle_p_;
    double kthrottle_i_;
    double kthrottle_d_;
    double dt;

    double sum_err_roll;
    double last_err_roll;
    double sum_err_pitch;
    double last_err_pitch;
    double sum_err_throttle;
    double last_err_throttle;

    int right_turn;

    CrashingCounter crashing_counter;

public:
    explicit StdFlightController(double dt) noexcept;

    void reset() noexcept;

    std::array<double, 4> norm_fc_output(std::array<double, 4> action4) noexcept;

    std::array<double, 4> direct_LU_flight_controler(
        const FighterState& fighter,
        const c3utils::Vector3& fix_vec,
        double intent_mach,
        double strength_bias = 0.0
    ) noexcept;

    std::array<double, 4> pid(
        double err_roll, double err_pitch, double err_throttle,
        double kroll_p, double kroll_i, double kroll_d,
        double kpitch_p, double kpitch_i, double kpitch_d,
        double throttle_base = 0.5
    ) noexcept;

    static double get_throttle_base(const FighterState& fighter, double intent_mach) noexcept;
};

}
