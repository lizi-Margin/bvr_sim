#pragma once

#include "base.hxx"

namespace bvr_sim {

class GroundStaticTarget : public GroundUnit {
public:
    GroundStaticTarget(
        const std::string& uid,
        TeamColor color,
        const std::array<double, 3>& position,
        double dt = 0.1
    ) noexcept;

    ~GroundStaticTarget() noexcept override = default;
};

}