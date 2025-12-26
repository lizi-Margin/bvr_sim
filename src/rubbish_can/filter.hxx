#pragma once

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

