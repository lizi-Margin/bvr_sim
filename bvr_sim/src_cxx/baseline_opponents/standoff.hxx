#pragma once

#include "base.hxx"
#include "support/json.hpp"
#include <memory>
#include <random>
#include <vector>

namespace bvr_sim {

class StandoffOpponent3D : public BaseOpponent3D {
private:
    int last_shoot_time;
    int crank_direction;
    int crank_switch_time;

public:
    static int randomize_crank_direction() noexcept {
        static std::mt19937 gen(std::random_device{}());
        static std::uniform_int_distribution<int> dist(0, 1);
        return dist(gen) == 0 ? -1 : 1;
    }

    StandoffOpponent3D() noexcept;

    ~StandoffOpponent3D() noexcept override = default;

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

    void defensive_abort(
        std::shared_ptr<Aircraft> agent,
        const std::vector<std::shared_ptr<Missile>>& missiles,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) const noexcept;

    void shoot_and_crank(
        std::shared_ptr<Aircraft> agent,
        std::shared_ptr<Aircraft> target,
        double& delta_heading,
        double& delta_altitude,
        double& delta_speed,
        bool& shoot,
        json::JSON& fire
    ) noexcept;

    void support_crank(
        std::shared_ptr<Aircraft> agent,
        std::shared_ptr<Aircraft> target,
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

    double get_crank_heading(
        std::shared_ptr<Aircraft> agent,
        std::shared_ptr<Aircraft> target
    ) noexcept;
};

}
