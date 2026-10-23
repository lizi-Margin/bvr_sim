#pragma once
#include "vehicle.hxx"

namespace bvr_sim {
std::shared_ptr<GroundUnit> create_ground_unit(const GroundUnitSpec &spec,
                                               std::shared_ptr<const Terrain> environment, double dt);
}
