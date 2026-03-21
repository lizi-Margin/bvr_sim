#pragma once

#include "../simulator/simulator.hxx"
#include "../simulator/aircraft/base.hxx"
#include "../simulator/missile/base.hxx"
#include "rubbish_can/json.hpp"
#include "c3utils/c3utils.hxx"
#include <string>
#include <vector>
#include <map>
#include <memory>
#include <cmath>
#include <optional>

namespace bvr_sim {

class BaseOpponent3D {
protected:
    std::string name;
    int time_counter;

public:
    BaseOpponent3D(const std::string& name = "BaseOpponent3D") noexcept;

    virtual ~BaseOpponent3D() noexcept = default;

    virtual void take_action(
        std::shared_ptr<Aircraft> agent,
        const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
        const std::vector<std::shared_ptr<SimulatedObject>>& partners,
        const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
    ) = 0;

    std::optional<json::JSON> get_action_cache() const noexcept;

protected:
    double normalize_angle(double angle) const noexcept;

    std::map<std::string, double> build_action_from_rates(
        double delta_heading,
        double delta_altitude,
        double delta_speed,
        bool shoot,
        const std::map<std::string, double>& other_commands = {}
    ) const noexcept;

    void apply_action(
        const std::shared_ptr<Aircraft>& agent,
        const std::map<std::string, double>& legacy_action,
        json::JSON fire_action_json = json::JSON()
    ) noexcept;
    json::JSON _action_cache;

    json::JSON get_fire_action(
        const std::shared_ptr<Aircraft>& agent,
        const std::string& target_uid,
        const std::string& missile_spec
    ) const noexcept;

    double calculate_heading_to_target(
        const std::shared_ptr<Aircraft>& agent,
        const std::array<double, 3>& target_pos
    ) const noexcept;

    double get_heading_action(
        const std::shared_ptr<Aircraft>& agent,
        double desired_heading
    ) const noexcept;
};

}