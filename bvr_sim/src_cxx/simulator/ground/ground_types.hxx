#pragma once
// Core-owned value contracts; safe for snapshot clients without physics dependencies.
#include <array>
#include <string>
#include <vector>

namespace bvr_sim {
struct VehicleParameters {
    double max_speed = 10, acceleration = 2, brake = 4, yaw_rate = .8;
    double radius = 2.1, height = 2.0, max_grade = .35, max_step = .6;
    double waypoint_radius = 1.5;
};
struct VehicleRoute {
    std::vector<std::array<double, 2>> points;
    double speed = 6;
    bool loop = false;
};
struct GroundUnitSpec {
    std::string uid, model = "WillysJeep", kind = "vehicle", team = "red";
    std::array<double, 3> position{};
    VehicleRoute route;
    int missiles = 6;
    bool mission_target = true;
};
} // namespace bvr_sim
