#include "awacs.hxx"
#include "../aircraft/base.hxx"
#include "../data_obj.hxx"

namespace bvr_sim {

SADatalink::SADatalink(
    const std::shared_ptr<Aircraft>& parent,
    const std::string& aircraft_model,
    double noise_std_position
) noexcept : SensorBase(parent),
    noise_std_position(noise_std_position),
    refresh_interval_s(6.0),
    refresh_interval_steps(std::max(1, static_cast<int>(refresh_interval_s / parent->dt))),
    last_update_step(     -std::max(1, static_cast<int>(refresh_interval_s / parent->dt)) - 114514),
    step_cnt(0) {
}

void SADatalink::update() {
    step_cnt += 1;
    if ((step_cnt - last_update_step) >= refresh_interval_steps) {
        _update();
        last_update_step = step_cnt;
    }
}

std::string SADatalink::log_suffix() const noexcept {
    return "";
}

void SADatalink::_update() {
    data_dict.clear();

    for (const auto& enemy : parent->enemies) {
        if (!enemy->is_alive) {
            continue;
        }

        if (enemy->Type != SOT::Aircraft) {
            continue;
        }

        // Create SA track for this enemy
        auto sa_track = std::make_shared<DataObj>(
            enemy,
            noise_std_position,
            0.0  // Datalink doesn't provide velocity
        );
        data_dict[enemy->uid] = sa_track;
    }
}

}