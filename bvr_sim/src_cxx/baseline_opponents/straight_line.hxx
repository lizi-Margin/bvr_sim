#pragma once

#include "base.hxx"
#include <string>
#include <vector>
#include <memory>

namespace bvr_sim {

class StraightLineOpponent3D : public BaseOpponent3D {
public:
    StraightLineOpponent3D() noexcept;

    ~StraightLineOpponent3D() noexcept override = default;

    void take_action(
        std::shared_ptr<Aircraft> agent,
        const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
        const std::vector<std::shared_ptr<SimulatedObject>>& partners,
        const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
    ) override;
};

}
