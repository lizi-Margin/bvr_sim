#pragma once
#include "global_config.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

class SimpleScalarFilter {
private:
    double alpha;
    double init_value;
    double value;

public:
    SimpleScalarFilter(double alpha, double initial_value = 0.0) noexcept : alpha(alpha), init_value(initial_value), value(initial_value) {}
    void reset() noexcept {
        value = init_value;
    }
    double update(double x) noexcept {
        value = alpha * x + (1 - alpha) * value;
        return value;
    }
};

#include <cmath>

class TimeScalarFilter {
private:
    double tau;
    double init_value;
    double value;

public:
    TimeScalarFilter(double alpha_04, double initial_value = 0.0) noexcept
        : init_value(initial_value), value(initial_value)
    {
        // 根据 dt=0.4 时的 alpha 反推 tau
        tau = -0.4 / ::std::log(1.0 - alpha_04);
    }

    void reset() noexcept {
        value = init_value;
    }

    double update(double x, double dt) noexcept {
        double alpha = 1.0 - ::std::exp(-dt / tau);
        alpha = ::std::clamp(alpha, 0.0, 1.0);
        value = alpha * x + (1.0 - alpha) * value;
        return value;
    }

    double get_value() const noexcept {
        return value;
    }
};

}