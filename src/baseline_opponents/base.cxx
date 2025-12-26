#include "base.hxx"
#include "cmd_handler.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/json_getter.hxx"
#include <algorithm>

namespace bvr_sim {

BaseOpponent3D::BaseOpponent3D(const std::string& name) noexcept
    : name(name), time_counter(0), _action_cache{}
{
    auto action = build_action_from_rates(0.0, 0.0, 0.0, false);
    {
        json::JSON base = json::JSON::Make(json::JSON::Class::Object);
        for (const auto& [key, value] : action) {
            base[key] = json::Float(value);
        }
        base["fire"] = json::JSON();
        _action_cache = std::move(base);
    }
}

double BaseOpponent3D::normalize_angle(double angle) const noexcept {
    using namespace c3utils;
    return norm_pi(angle);
}

std::map<std::string, double> BaseOpponent3D::build_action_from_rates(
    double delta_heading,
    double delta_altitude,
    double delta_speed,
    bool shoot,
    const std::map<std::string, double>& other_commands
) const noexcept {
    std::map<std::string, double> action = {
        {"delta_heading", delta_heading},
        {"delta_altitude", delta_altitude},
        {"delta_speed", delta_speed},
        {"shoot", shoot ? 1.0 : 0.0}
    };

    // Add any other commands
    for (const auto& [key, value] : other_commands) {
        action[key] = value;
    }

    return action;
}


json::JSON BaseOpponent3D::get_fire_action(
    const std::shared_ptr<Aircraft>& agent,
    const std::string& target_uid,
    const std::string& missile_spec
) const noexcept {
    json::JSON fire_subdict = json::JSON::Make(json::JSON::Class::Object);
    fire_subdict["target_uid"] = json::String(target_uid);
    fire_subdict["weapon_spec"] = json::String(missile_spec);
    return fire_subdict;
}

void BaseOpponent3D::apply_action(
    const std::shared_ptr<Aircraft>& agent,
    const std::map<std::string, double>& legacy_action,
    json::JSON fire_action_json
) noexcept {
    std::string cmd;
    {
        json::JSON base = json::JSON::Make(json::JSON::Class::Object);
        for (const auto& [key, value] : legacy_action) {
            base[key] = json::Float(value);
        }
        base["fire"] = fire_action_json;
        cmd = "set " + agent->uid + " " + base.dump(1, "", "");
        _action_cache = std::move(base);
        // std::printf("BaseOpponent3D::apply_action: %s\n", cmd.c_str());
        // std::printf("BaseOpponent3D::action cachk: %s\n", _action_cache.dump().c_str());
    }

    {
        auto res = CmdHandler::instance().handle(cmd);
        if (res.JSONType() == json::JSON::Class::Object) {
            if (res["status"].ToString() == "ok") {
                // pass
            } else {
                SL::get().print("[BaseOpponent3D] Error: " + res["message"].ToString());
            }
        } else {
            SL::get().print("[BaseOpponent3D] Error: Invalid response format from CmdHandler.");
        }
    }
}

std::optional<json::JSON> BaseOpponent3D::get_action_cache() const noexcept {
    if (_action_cache.JSONType() == json::JSON::Class::Null) {
        return std::nullopt;
    }
    return _action_cache;
}


double BaseOpponent3D::calculate_heading_to_target(
    const std::shared_ptr<Aircraft>& agent,
    const std::array<double, 3>& target_pos
) const noexcept {

    std::array<double, 3> rel_pos = {
        target_pos[0] - agent->position[0],
        target_pos[1] - agent->position[1],
        target_pos[2] - agent->position[2]
    };

    // Calculate heading in NWU frame
    return std::atan2(rel_pos[1], rel_pos[0]);
}

double BaseOpponent3D::get_heading_action(
    const std::shared_ptr<Aircraft>& agent,
    double desired_heading
) const noexcept {
    double current_heading = agent->get_heading();
    double angle_diff = normalize_angle(desired_heading - current_heading);

    // Proportional control with P-gain = 2.0
    double heading_rate = angle_diff * 2.0;

    return heading_rate;
}

}