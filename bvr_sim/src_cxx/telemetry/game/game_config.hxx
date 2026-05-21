#pragma once

namespace bvr_sim {

struct GameCameraConfig {
    static constexpr float k_min_distance = 20.0f;
    static constexpr float k_defualt_distance = 30.0f;
    static constexpr float k_max_distance = 100.0f;
    static constexpr float k_follow_height_ratio = 0.6f;
};

struct GameLightingConfig {
    static constexpr float k_sun_dir_x = 0.46f;
    static constexpr float k_sun_dir_y = 0.78f;
    static constexpr float k_sun_dir_z = -0.42f;
    static constexpr float k_sun_r = 1.08f;
    static constexpr float k_sun_g = 1.00f;
    static constexpr float k_sun_b = 0.90f;
    static constexpr float k_sun_intensity = 1.12f;
};

struct GameModelScaleConfig {
    static constexpr bool k_use_real_scale = false;
    static constexpr float k_uniform_scale = 75.0f;
};

} // namespace bvr_sim
