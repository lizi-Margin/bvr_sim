#pragma once
#include <array>
#include <map>
#include <optional>
#include <utility>
#include "rubbish_can/json.hpp"
#include "rubbish_can/check.hxx"
#include "simulator/register.hxx"


namespace bvr_sim {

namespace action_space_check {

inline bool has_possible_action(const Register& register_) {
    return register_.has("delta_heading") || register_.has("delta_altitude") || register_.has("delta_speed") || register_.has("fire") ||
           register_.has("aileron_cmd") || register_.has("elevator_cmd") || register_.has("rudder_cmd") || register_.has("throttle_cmd");
}

inline void wipe_out_action(Register& register_) { 
    register_.pop("delta_heading");
    register_.pop("delta_altitude");
    register_.pop("delta_speed");
    register_.pop("fire");
    register_.pop("aileron_cmd");
    register_.pop("elevator_cmd");
    register_.pop("rudder_cmd");
    register_.pop("throttle_cmd");
    // legacy
    register_.pop("shoot");
    
    if (has_possible_action(register_)) {
        check(false, "WTF");
    }
}

inline void check_action_json(const json::JSON& action_json) {
    auto check_optional_number_or_null = [&](const std::string& key) {
        if (!action_json.hasKey(key)) {
            return;
        }
        auto type = action_json.at(key).JSONType();
        check(type == json::JSON::Class::Floating || type == json::JSON::Class::Integral || type == json::JSON::Class::Null, key.c_str());
    };

    check_optional_number_or_null("delta_heading");
    check_optional_number_or_null("delta_altitude");
    check_optional_number_or_null("delta_speed");
    check_optional_number_or_null("aileron_cmd");
    check_optional_number_or_null("elevator_cmd");
    check_optional_number_or_null("rudder_cmd");
    check_optional_number_or_null("throttle_cmd");
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
    ActionSpace(json::JSON &&action_json) : action_json(std::move(action_json)) {
        action_space_check::check_action_json(this->action_json);
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
        auto aileron_cmd = register_.get("aileron_cmd");
        auto elevator_cmd = register_.get("elevator_cmd");
        auto rudder_cmd = register_.get("rudder_cmd");
        auto throttle_cmd = register_.get("throttle_cmd");
        

        // lambda to retrieve the float value from the register, with error checking
        auto get_float_from_register = [&](std::optional<json::JSON>& value_opt, const std::string& key) -> void {
            if (!value_opt.has_value()) {
                return;
            }
            auto& value = value_opt.value();
            if (value.JSONType() == json::JSON::Class::Floating) {
                action_json[key] = std::move(value);
            } else if (value.JSONType() == json::JSON::Class::Integral) {
                action_json[key] = json::Float(value.ToInt());
            } else if (value.JSONType() == json::JSON::Class::Null) {
                action_json[key] = json::JSON();
            } else {
                colorful::printHONG(
                    "Expected a numeric type for action component, but got type %s",
                    json::JSON::ClassString(value.JSONType()).c_str()
                );
            }
            return;
        };

        get_float_from_register(delta_heading, "delta_heading");
        get_float_from_register(delta_altitude, "delta_altitude");
        get_float_from_register(delta_speed, "delta_speed");
        get_float_from_register(aileron_cmd, "aileron_cmd");
        get_float_from_register(elevator_cmd, "elevator_cmd");
        get_float_from_register(rudder_cmd, "rudder_cmd");
        get_float_from_register(throttle_cmd, "throttle_cmd");

        auto fire = register_.get("fire");
        if (fire.has_value()) {
            action_json["fire"] = std::move(fire.value());
        }

        action_space_check::check_action_json(this->action_json);
    }
    ~ActionSpace() = default;

    double delta_heading() const {
        if (!action_json.hasKey("delta_heading") || action_json.at("delta_heading").JSONType() == json::JSON::Class::Null) {
            return 0.0;
        }
        return action_json.at("delta_heading").ToFloat();
    }

    double delta_altitude() const {
        if (!action_json.hasKey("delta_altitude") || action_json.at("delta_altitude").JSONType() == json::JSON::Class::Null) {
            return 0.0;
        }
        return action_json.at("delta_altitude").ToFloat();
    }

    double delta_speed() const {
        if (!action_json.hasKey("delta_speed") || action_json.at("delta_speed").JSONType() == json::JSON::Class::Null) {
            return 0.0;
        }
        return action_json.at("delta_speed").ToFloat();
    }

    void set_delta_heading(double value) {
        action_json["delta_heading"] = json::Float(value);
    }

    void set_delta_altitude(double value) {
        action_json["delta_altitude"] = json::Float(value);
    }

    void set_delta_speed(double value) {
        action_json["delta_speed"] = json::Float(value);
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

    std::optional<double> aileron_cmd() const {
        if (!action_json.hasKey("aileron_cmd")) {
            return std::nullopt;
        }
        if (action_json.at("aileron_cmd").JSONType() == json::JSON::Class::Null) {
            return std::nullopt;
        }
        return action_json.at("aileron_cmd").ToFloat();
    }

    std::optional<double> elevator_cmd() const {
        if (!action_json.hasKey("elevator_cmd")) {
            return std::nullopt;
        }
        if (action_json.at("elevator_cmd").JSONType() == json::JSON::Class::Null) {
            return std::nullopt;
        }
        return action_json.at("elevator_cmd").ToFloat();
    }

    std::optional<double> rudder_cmd() const {
        if (!action_json.hasKey("rudder_cmd")) {
            return std::nullopt;
        }
        if (action_json.at("rudder_cmd").JSONType() == json::JSON::Class::Null) {
            return std::nullopt;
        }
        return action_json.at("rudder_cmd").ToFloat();
    }

    std::optional<double> throttle_cmd() const {
        if (!action_json.hasKey("throttle_cmd")) {
            return std::nullopt;
        }
        if (action_json.at("throttle_cmd").JSONType() == json::JSON::Class::Null) {
            return std::nullopt;
        }
        return action_json.at("throttle_cmd").ToFloat();
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

