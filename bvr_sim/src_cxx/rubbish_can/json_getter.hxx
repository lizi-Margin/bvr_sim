# pragma once

#include <array>
#include "rubbish_can/json.hpp"

inline bool get_string_from_json(
        const std::string& key,
        json::JSON spec_json,
        std::string& value
) noexcept {
    bool success = false;
    try {
        if (spec_json.hasKey(key)) {
            if (spec_json[key].JSONType() == json::JSON::Class::String) {
                value = spec_json[key].ToString();
                success = true;
            }
        }
    } catch (...) {
        return false;
    }
    return success;
}

inline bool get_double_from_json(
        const std::string& key,
        json::JSON spec_json,
        double& value
) noexcept {
    bool success = false;
    try {
        if (spec_json.hasKey(key)) {
            if (spec_json[key].JSONType() == json::JSON::Class::Floating) {
                value = spec_json[key].ToFloat();
                success = true;
            } else if (spec_json[key].JSONType() == json::JSON::Class::Integral) {
                value = static_cast<double>(spec_json[key].ToInt());
                success = true;
            }
        }
    } catch (...) {
        return false;
    }
    return success;
}

inline bool get_array3_from_json(
        const std::string& key,
        json::JSON spec_json,
        std::array<double, 3>& position
) noexcept {
    bool success = false;
    try {
        if (spec_json.hasKey(key)) {
            auto pos = spec_json[key];
            if (pos.JSONType() == json::JSON::Class::Array) {
                if (pos.size() == 3) {
                    std::array<double, 3> pos_arr = {0.0, 0.0, 0.0};
                    for (size_t i = 0; i < 3; i++) {
                        if (pos[i].JSONType() == json::JSON::Class::Floating) {
                            pos_arr[i] = pos[i].ToFloat();
                            success = true;
                        } else if (pos[i].JSONType() == json::JSON::Class::Integral) {
                            pos_arr[i] = static_cast<double>(pos[i].ToInt());
                            success = true;
                        } else {
                            success = false;
                            break;
                        }
                    }
                    if (success) {
                        position = std::move(pos_arr);
                    }
                }
            }
        }
    } catch (...) {
        return false;
    }
    return success;
}


inline bool get_map_ss_from_json(
        const std::string& key,
        json::JSON spec_json,
        std::map<std::string, std::string>& map
) noexcept {
    bool success = false;
    try {
        if (spec_json.hasKey(key)) {
            auto map_json = spec_json[key];
            if (map_json.JSONType() == json::JSON::Class::Object) {
                std::map<std::string, std::string> map_tmp;
                if (map_json.size() == 0) {
                    success = true;
                }
                for (auto& [k, v] : map_json.ObjectRange()) {
                    if (v.JSONType() == json::JSON::Class::String) {
                        map_tmp[k] = v.ToString();
                        success = true;
                    } else {
                        success = false;
                        break;
                    }
                }
                
                if (success) {
                    map = std::move(map_tmp);
                }
            }
        }
    } catch (...) {
        return false;
    }
    return success;
}
