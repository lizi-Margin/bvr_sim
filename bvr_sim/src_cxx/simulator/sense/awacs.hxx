#pragma once

#include "base.hxx"
#include <string>

namespace bvr_sim {

class SADatalink : public SensorBase {
private:
    double noise_std_position;
    double refresh_interval_s;
    int refresh_interval_steps;
    int last_update_step;
    int step_cnt;

public:
    SADatalink(
        const std::shared_ptr<Aircraft>& parent,
        const std::string& aircraft_model = "",
        double noise_std_position = 500.0  // meters (low accuracy datalink)
    ) noexcept;

    ~SADatalink() noexcept override = default;

    void update() override;

    std::string log_suffix() const noexcept override;

private:
    void _update();
};

}