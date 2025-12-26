#pragma once
#include <array>
#include <map>
#include "rubbish_can/json.hpp"
#include "rubbish_can/check.hxx"
#include "simulator/register.hxx"


namespace bvr_sim {

namespace action_space_check {

inline bool has_possible_action(const Register& register_) {
    return register_.has("delta_heading") || register_.has("delta_altitude") || register_.has("delta_speed") || register_.has("fire");
}

inline void wipe_out_action(Register& register_) { 
    register_.pop("delta_heading");
    register_.pop("delta_altitude");
    register_.pop("delta_speed");
    register_.pop("fire");
    // legacy
    register_.pop("shoot");
    
    if (has_possible_action(register_)) {
        check(false, "WTF");
    }
}

inline void check_action_json(const json::JSON& action_json) {
    check(action_json.hasKey_checkTypeIfExist("delta_heading", json::JSON::Class::Floating), "delta_heading");
    check(action_json.hasKey_checkTypeIfExist("delta_altitude", json::JSON::Class::Floating), "delta_altitude");
    check(action_json.hasKey_checkTypeIfExist("delta_speed", json::JSON::Class::Floating), "delta_speed");
    if (action_json.hasKey("fire", json::JSON::Class::Object)) {
        auto fire_json = action_json.at("fire");
        check(fire_json.hasKey_checkTypeIfExist("target_uid", json::JSON::Class::String), "fire.target_uid");
        check(fire_json.hasKey_checkTypeIfExist("weapon_spec", json::JSON::Class::String), "fire.weapon_spec");
    }
    else if (action_json.hasKey("fire", json::JSON::Class::Null)) {
        // pass
    }
    else if (action_json.hasKey("fire", json::JSON::Class::Floating)){
        double fire_prob = action_json.at("fire").ToFloat();
        std::printf("deprecated fire float format, fire_prob: %f\n", fire_prob);
        check(false, "deprecated fire float format, use object format instead");
    }
    else if (!action_json.hasKey("fire")){
        //pass
    } else {
        colorful::printHONG("Invalid fire action Type: " + action_json.at("fire").dump());
    }
}

// inline bool fire(const json::JSON& action_json) {
//     check_action_json(action_json);
//     return action_json.hasKey("fire", json::JSON::Class::Object);
// }

}



class ActionSpace {
protected:
    json::JSON action_json;

public:
    ActionSpace(const json::JSON &action_json) : action_json(action_json) {
        action_space_check::check_action_json(action_json);
    }
    ActionSpace(const std::map<std::string, json::JSON> &action_json) : action_json(json::Object()) {
        for (auto& [key, value] : action_json) {
            this->action_json[key] = value;
        }
        action_space_check::check_action_json(this->action_json);
    }
    ActionSpace(const Register& register_) : action_json(json::Object()) {
        auto delta_heading = register_.get("delta_heading");
        auto delta_altitude = register_.get("delta_altitude");
        auto delta_speed = register_.get("delta_speed");
        if (delta_heading.has_value() && delta_heading.value().JSONType() == json::JSON::Class::Floating) {
            action_json["delta_heading"] = delta_heading.value();
        }
        if (delta_altitude.has_value() && delta_altitude.value().JSONType() == json::JSON::Class::Floating) {
            action_json["delta_altitude"] = delta_altitude.value();
        }
        if (delta_speed.has_value() && delta_speed.value().JSONType() == json::JSON::Class::Floating) {
            action_json["delta_speed"] = delta_speed.value();
        }

        auto fire = register_.get("fire");
        if (fire.has_value()) {
            action_json["fire"] = fire.value();
        }

        action_space_check::check_action_json(this->action_json);
    }
    ~ActionSpace() = default;

    double delta_heading() const {
        return action_json.at("delta_heading").ToFloat();
    }

    double delta_altitude() const {
        return action_json.at("delta_altitude").ToFloat();
    }

    double delta_speed() const {
        return action_json.at("delta_speed").ToFloat();
    }

    std::array<double, 3> get_campus() const {
        std::array<double, 3> res{};
        res[0] = delta_heading();
        res[1] = delta_altitude();
        res[2] = delta_speed();
        return res;
    }

    bool fire() {
        return action_json.hasKey("fire", json::JSON::Class::Object);
    }

    std::string fire_target_uid() {
        if (!fire()) {
            format_check(false, "make sure fire is true to call this function");
        }
        return action_json.at("fire").at("target_uid").ToString();
    }

    std::string fire_weapon_spec() {
        if (!fire()) {
            format_check(false, "make sure fire is true to call this function");
        }
        return action_json.at("fire").at("weapon_spec").ToString();
    }
};

}