#pragma once
#include "simulator/environment.hxx"
#include "simulator/simulator.hxx"
#include <map>

namespace bvr_sim {
struct GroundRadarDetection {
    std::string uid;
    std::array<double, 3> position{}, velocity{};
    double range = 0;
};
// Explicit ground-sensor approximation: omnidirectional range + terrain/structure LOS.
// Observations are refreshed by core ticks; no HUD or mission event creates a detection.
class GroundSearchRadar {
  public:
    std::map<std::string, GroundRadarDetection> contacts;
    void update(const SimulatedObject &owner, const Terrain &environment, double range);
};
} // namespace bvr_sim
