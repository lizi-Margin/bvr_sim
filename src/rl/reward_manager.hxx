#pragma once

#include <vector>
#include <memory>
#include <unordered_map>
#include <string>
#include "reward_components.hxx"

namespace bvr_sim {

class Aircraft;
class Missile;

class RewardManager {
public:
    RewardManager();
    explicit RewardManager(const std::string& config_path);
    ~RewardManager() = default;

    void load_config(const std::string& config_path);
    void load_config_str(const std::string& config_str);

    void add_component(std::shared_ptr<RewardComponent> component);
    void remove_component(const std::string& name);
    std::shared_ptr<RewardComponent> get_component(const std::string& name);

    double compute_reward(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info);

    std::unordered_map<std::string, double> get_reward_breakdown(const std::string& agent_uid);

    void reset();

private:
    void initialize_components();
    // void apply_config();

    std::vector<std::shared_ptr<RewardComponent>> components_;
    std::unordered_map<std::string, std::shared_ptr<RewardComponent>> component_dict_;
    std::unordered_map<std::string, double> config_;
    std::unordered_map<std::string, std::unordered_map<std::string, double>> breakdown_cache_;
};

}
