#pragma once

namespace bvr_sim {

struct GameCameraConfig {
    static constexpr float k_min_distance = 750.0f;
    static constexpr float k_max_distance = 180000.0f;
    static constexpr float k_follow_height_ratio = 0.6f;
};

} // namespace bvr_sim
