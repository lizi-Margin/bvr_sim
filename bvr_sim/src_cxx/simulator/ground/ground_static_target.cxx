#include "ground_static_target.hxx"

namespace bvr_sim {

GroundStaticTarget::GroundStaticTarget(
    const std::string& uid,
    TeamColor color,
    const std::array<double, 3>& position,
    double dt
) noexcept : GroundUnit(
        uid,
        // "60m Checker",
        // "Oil Rig",
        // "ammunitionBunker",
        // "Leclerc",
        // "Truck",
        // "MIM-104 Patriot (AMG Search Radar)",
        // "ZIL-131",
        "SA-11 Gadfly (9S470M1 CC)",  // Default model from Python
        color,
        position,
        dt
) {
    _collision_radius = 100.0;  // m
}

}