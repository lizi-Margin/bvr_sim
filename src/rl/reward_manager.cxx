#include "reward_manager.hxx"
// #include "simulator/simulator.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "rubbish_can/json.hpp"
#include "simulator/aircraft/base.hxx"
#include <fstream>
#include <sstream>
#include <iostream>

namespace bvr_sim {

static std::string get_root_dir() noexcept {
    std::string root_dir = std::string(__FILE__).substr(0, std::string(__FILE__).find_last_of("\\/"));
    for (auto& c : root_dir) {
        if (c == '\\') {
            c = '/';
        }
    }
    return root_dir + "/";
}


RewardManager::RewardManager() {
    load_config(get_root_dir() + "./reward_default_config.json");
}

RewardManager::RewardManager(const std::string& config_path) {
    load_config(config_path);
}

void RewardManager::initialize_components() {
    auto get_config = [this](const std::string& key, double default_val) -> double {
        auto it = config_.find(key);
        if (it != config_.end()) {
            SL::get().printf("[RewardManager] Get reward config value for key: '%s' is %f\n", key.c_str(), it->second);
            // std::printf("[RewardManager] Get reward config value for key: '%s' is %f\n", key.c_str(), it->second);
            return it->second; 
        }
        else {
            colorful::printHUANG("Warning: Reward config value for key: '" + key + "' is not found, use default value: " + std::to_string(default_val));
            SL::get().printf("[RewardManager] Warning: Reward config value for key: '%s' is not found, use default value: %f\n", key.c_str(), default_val);
            return default_val;
        }
    };

    add_component(std::make_shared<EngageEnemyReward>(
        get_config("engage_enemy_weight", 0.15),
        "engage_enemy"));

    add_component(std::make_shared<EnemyTrackingReward>(
        get_config("enemy_tracking_weight", 0.01),
        "enemy_tracking"));

    add_component(std::make_shared<EnemyDistanceReward>(
        get_config("enemy_distance_weight", 0.0),
        "enemy_distance"));

    add_component(std::make_shared<AltitudeAdvantageReward>(
        get_config("altitude_advantage_weight", 0.001),
        "altitude_advantage"));

    add_component(std::make_shared<SafeAltitudeReward>(
        get_config("safe_altitude_weight", 0.002),
        get_config("safe_altitude_min", 400.0),
        get_config("safe_altitude_max", 12000.0),
        "safe_altitude"));

    add_component(std::make_shared<MissileEvasionReward>(
        get_config("missile_evasion_weight", 0.2),
        "missile_evasion"));

    add_component(std::make_shared<SpeedReward>(
        get_config("speed_weight", 0.01),
        get_config("target_speed", 450.0),
        "speed"));

    add_component(std::make_shared<SurvivalReward>(
        get_config("survival_weight", 0.01),
        "survival"));

    add_component(std::make_shared<MissileLaunchReward>(
        get_config("missile_launch_weight", 1.0),
        get_config("missile_launch_reward", 6.0),
        get_config("missile_duplicated_launch_penalty", -3.0),
        "missile_launch"));

    add_component(std::make_shared<MissileResultReward>(
        get_config("missile_result_weight", 1.0),
        get_config("missile_hit_reward", 100.0),
        get_config("missile_miss_penalty", -3.0),
        "missile_result"));

    add_component(std::make_shared<WinLossReward>(
        get_config("win_loss_weight", 1.0),
        get_config("win_reward", 80.0),
        get_config("loss_penalty", -50.0),
        "win_loss"));
}

void RewardManager::load_config(const std::string& config_path) {
    std::ifstream file(config_path);
    if (!file.is_open()) {
        colorful::printHUANG("Warning: Could not open reward config file: " + config_path);
        SL::get().printf("Warning: Could not open reward config file: %s\n", config_path.c_str());
        colorful::printHUANG("Using default reward configuration.");
        return;
    }

    std::stringstream buffer;
    buffer << file.rdbuf();
    file.close();
    load_config_str(buffer.str());
}

void RewardManager::load_config_str(const std::string& config_str) {
    try {
        json::JSON config = json::JSON::Load(config_str);

        config_.clear();

        for (auto& [key, value] : config.ObjectRange()) {
            if (value.IsFloating()) {
                config_[key] = value.ToFloat();
            }
            else if (value.IsIntegral()) {
                config_[key] = static_cast<double>(value.ToInt());
            }
            else {
                colorful::printHUANG("Warning: Reward config value for key: '" + key + "' ,value: '" + value.dump() + "' is not a number, skip.");
            }
        }

        colorful::printLV("[RewardManager] Successfully loaded reward config, total %d values in json.", config_.size());
        // colorful::printLV("[RewardManager] Successfully loaded reward config, keys: %s.", config.dump().c_str());
        SL::get().printf("[RewardManager] Successfully loaded reward config, total %d values in json.\n", config_.size());
        SL::get().printf("[RewardManager] Successfully loaded reward config, keys: %s.\n", config.dump().c_str());
    } catch (const std::exception& e) {
        colorful::printHONG("[RewardManager] Error loading reward config: " + std::string(e.what()));
        SL::get().printf("[RewardManager] Error loading reward config: %s\n", e.what());
        check(false, "");
    }

    components_.clear();
    component_dict_.clear();
    initialize_components();
}

// void RewardManager::apply_config() {
//     auto get_config = [this](const std::string& key, double default_val) -> double {
//         auto it = config_.find(key);
//         return (it != config_.end()) ? it->second : default_val;
//     };

//     auto set_weight = [this](const std::string& name, double weight) {
//         auto comp = get_component(name);
//         if (comp) {
//             comp->set_weight(weight);
//         } else {
//             colorful::printHONG("RewardComponent with name " + name + " not found, set weight failed");
//             std::abort();
//         }
//     };

//     set_weight("engage_enemy", get_config("engage_enemy_weight", 0.15));
//     set_weight("enemy_distance", get_config("enemy_distance_weight", 0.0));
//     set_weight("altitude_advantage", get_config("altitude_advantage_weight", 0.001));
//     set_weight("safe_altitude", get_config("safe_altitude_weight", 0.002));
//     set_weight("missile_evasion", get_config("missile_evasion_weight", 0.2));
//     set_weight("speed", get_config("speed_weight", 0.01));
//     set_weight("survival", get_config("survival_weight", 0.01));
//     set_weight("missile_launch", get_config("missile_launch_weight", 1.0));
//     set_weight("missile_result", get_config("missile_result_weight", 1.0));
//     set_weight("win_loss", get_config("win_loss_weight", 1.0));

//     auto speed_comp = std::dynamic_pointer_cast<SpeedReward>(get_component("speed"));
//     if (speed_comp) {
//         double target_speed = get_config("target_speed", 450.0);
//         speed_comp->target_speed_ = target_speed;
//     } else {
//         colorful::printHONG("dynamic_cast<SpeedReward> failed");
//         std::abort();
//     }

//     auto safe_alt_comp = std::dynamic_pointer_cast<SafeAltitudeReward>(get_component("safe_altitude"));
//     if (safe_alt_comp) {
//         double safe_min = get_config("safe_altitude_min", 400.0);
//         double safe_max = get_config("safe_altitude_max", 12000.0);
//         safe_alt_comp->safe_min_ = safe_min;
//         safe_alt_comp->safe_max_ = safe_max;
//     } else {
//         colorful::printHONG("dynamic_cast<SafeAltitudeReward> failed");
//         std::abort();
//     }

//     auto missile_launch_comp = std::dynamic_pointer_cast<MissileLaunchReward>(get_component("missile_launch"));
//     if (missile_launch_comp) {
//         double launch_reward = get_config("missile_launch_reward", 6.0);
//         double penalty = get_config("missile_duplicated_launch_penalty", -3.0);
//         missile_launch_comp->launch_reward_ = launch_reward;
//         missile_launch_comp->duplicated_launch_penalty_ = penalty;
//     } else {
//         colorful::printHONG("dynamic_cast<MissileLaunchReward> failed");
//         std::abort();
//     }

//     auto missile_result_comp = std::dynamic_pointer_cast<MissileResultReward>(get_component("missile_result"));
//     if (missile_result_comp) {
//         double hit_reward = get_config("missile_hit_reward", 100.0);
//         double miss_penalty = get_config("missile_miss_penalty", -3.0);
//         missile_result_comp->hit_reward_ = hit_reward;
//         missile_result_comp->miss_penalty_ = miss_penalty;
//     } else {
//         colorful::printHONG("dynamic_cast<MissileResultReward> failed");
//         std::abort();
//     }

//     auto win_loss_comp = std::dynamic_pointer_cast<WinLossReward>(get_component("win_loss"));
//     if (win_loss_comp) {
//         double win_reward = get_config("win_reward", 80.0);
//         double loss_penalty = get_config("loss_penalty", -50.0);
//         win_loss_comp->win_reward_ = win_reward;
//         win_loss_comp->loss_penalty_ = loss_penalty;
//     } else {
//         colorful::printHONG("dynamic_cast<WinLossReward> failed");
//         std::abort();
//     }
// }

void RewardManager::add_component(std::shared_ptr<RewardComponent> component) {
    if (component) {
        components_.push_back(component);
        component_dict_[component->get_name()] = component;
    }
}

void RewardManager::remove_component(const std::string& name) {
    auto it = component_dict_.find(name);
    if (it != component_dict_.end()) {
        auto component = it->second;
        components_.erase(
            std::remove(components_.begin(), components_.end(), component),
            components_.end()
        );
        component_dict_.erase(it);
    }
}

std::shared_ptr<RewardComponent> RewardManager::get_component(const std::string& name) {
    auto it = component_dict_.find(name);
    if (it != component_dict_.end()) {
        return it->second;
    } else {
        colorful::printHONG("[RewardManager] RewardComponent with name " + name + " not found");
        std::abort();
    }
    return nullptr;
}

double RewardManager::compute_reward(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    double total_reward = 0.0;
    std::string agent_uid = agent->uid;

    auto& breakdown = breakdown_cache_[agent_uid];
    breakdown.clear();

    for (auto& component : components_) {
        if (component) {
            double component_reward = component->operator()(agent, all_agents, all_missiles, info);
            total_reward += component_reward;
            breakdown[component->get_name()] = component_reward;
        }
    }

    breakdown["TOTAL"] = total_reward;
    return total_reward;
}

std::unordered_map<std::string, double> RewardManager::get_reward_breakdown(const std::string& agent_uid) {
    auto it = breakdown_cache_.find(agent_uid);
    if (it != breakdown_cache_.end()) {
        return it->second;
    }
    return std::unordered_map<std::string, double>();
}

void RewardManager::reset() {
    breakdown_cache_.clear();
    for (auto& component : components_) {
        if (component) {
            component->reset();
        }
    }
}

}
