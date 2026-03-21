#pragma once

#include <memory>
#include <string>
#include <vector>
#include <unordered_map>
#include <optional>
#include "observation_space.hxx"
#include "reward_manager.hxx"
#include "rubbish_can/json.hpp"

namespace bvr_sim {

class SimCore;
class Aircraft;
class Missile;

class RLManager {
public:
    RLManager();
    ~RLManager() = default;


    std::vector<double> get_observation(const std::string& agent_uid);

    double get_reward(const std::string& agent_uid, const json::JSON& info);

    bool get_done(const std::string& agent_uid);

    bool get_episode_done();

    std::vector<double> get_baseline_action_vec(const std::string& agent_uid);
    std::optional<json::JSON> get_baseline_action(const std::string& agent_uid);

    std::unordered_map<std::string, double> get_reward_breakdown(const std::string& agent_uid);

    void reset();

    void load_reward_config(const std::string& config_path);
    void load_reward_config_str(const std::string& config_str);

    void set_observation_space(const std::string& obs_space_spec);
    int get_obs_dim() const;

private:
    std::shared_ptr<ObservationSpace> obs_space_;
    RewardManager reward_manager_;

    std::vector<std::shared_ptr<Aircraft>> get_all_agents() const;
    std::vector<std::shared_ptr<Missile>> get_all_missiles() const;
    std::shared_ptr<Aircraft> get_agent(const std::string& uid) const;
};

}
