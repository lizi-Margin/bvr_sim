#include "straight_line.hxx"
#include "simulator/aircraft/base.hxx"

namespace bvr_sim {

StraightLineOpponent3D::StraightLineOpponent3D() noexcept
    : BaseOpponent3D("StraightLine3D") {
}

void StraightLineOpponent3D::take_action(
    std::shared_ptr<Aircraft> agent,
    const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
    const std::vector<std::shared_ptr<SimulatedObject>>& partners,
    const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
) {
    time_counter++;

    if (!agent->is_alive) {
        auto final_action = build_action_from_rates(0.0, 0.0, 0.0, false);
        apply_action(agent, final_action);
        return;
    }

    // Straight line flight: no heading, altitude, or speed changes
    auto final_action = build_action_from_rates(0.0, 0.0, 0.0, false);
    apply_action(agent, final_action);
}

}
