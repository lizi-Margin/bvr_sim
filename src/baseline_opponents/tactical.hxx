#pragma once

#include "base.hxx"
#include "rubbish_can/json.hpp"
#include <string>
#include <vector>
#include <memory>

namespace bvr_sim {

class TacticalOpponent3D : public BaseOpponent3D {
private:
    int last_shoot_time;
    int crank_direction;
    int crank_switch_time;

public:
    TacticalOpponent3D() noexcept;

    ~TacticalOpponent3D() noexcept override = default;

    void take_action(
        std::shared_ptr<Aircraft> agent,
        const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
        const std::vector<std::shared_ptr<SimulatedObject>>& partners,
        const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
    ) override;

private:
    std::vector<std::shared_ptr<Missile>> get_active_missile(
        const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
    ) const noexcept;

    void evade_missiles(
        std::shared_ptr<Aircraft> agent,
        std::vector<std::shared_ptr<Missile>> missiles,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) noexcept;

    void guide_missiles(
        std::shared_ptr<Aircraft> agent,
        std::vector<std::shared_ptr<Missile>> missiles_in_flight,
        std::vector<std::shared_ptr<Aircraft>> alive_enemies,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) noexcept;

    void tactical_attack(
        std::shared_ptr<Aircraft> agent,
        std::shared_ptr<Aircraft> target,
        std::vector<std::shared_ptr<Aircraft>> alive_enemies,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) noexcept;

    void get_default_action(
        std::shared_ptr<Aircraft> agent,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) const noexcept;
};

}