#include "rl_manager.hxx"
#include "core.hxx"
#include "so_pool.hxx"
#include "simulator/simulator.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/missile/base.hxx"
#include "bsl_pool.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "rubbish_can/colorful.hxx"
#include "action_space.hxx"
#include "rubbish_can/json_getter.hxx"
#include <algorithm>

namespace bvr_sim {

RLManager::RLManager()
    : obs_space_(std::make_shared<EntityObsSpace>()),
      reward_manager_{} {

    // const std::string default_config_path = "config/reward_config.json";
    // reward_manager_.load_config(default_config_path);
}

std::vector<std::shared_ptr<Aircraft>> RLManager::get_all_agents() const {
    std::vector<std::shared_ptr<Aircraft>> agents;
    auto all_objects = SOPool::instance().get_all_ever_existed();
    all_objects = SOPool::get_by_type(all_objects, SOT::Aircraft);
    for (const auto& obj : all_objects) {
        if (obj && obj->Type == SOT::Aircraft) {
            auto agent = std::dynamic_pointer_cast<Aircraft>(obj);
            check(agent, "agent");
            agents.push_back(agent);
        } else if (!obj) {
            colorful::printHONG("[RLManager::get_all_agents] Null object in SOPool");
            check(false, "[RLManager::get_all_agents] Null object in SOPool");
        } else {
            colorful::printHONG("[RLManager::get_all_agents] Object type mismatch: expected Aircraft, got %d", static_cast<int>(obj->Type));
            check(false, "[RLManager::get_all_agents] Object type mismatch: expected Aircraft");
        }
    }
    return agents;
}

std::vector<std::shared_ptr<Missile>> RLManager::get_all_missiles() const {
    std::vector<std::shared_ptr<Missile>> missiles;
    auto all_objects = SOPool::instance().get_all_ever_existed();
    all_objects = SOPool::get_by_type(all_objects, SOT::Missile);
    for (const auto& obj : all_objects) {
        if (obj && obj->Type == SOT::Missile) {
            auto missile = std::dynamic_pointer_cast<Missile>(obj);
            check(missile, "missile");
            missiles.push_back(missile);
        } else if (!obj) {
            colorful::printHONG("[RLManager::get_all_missiles] Null object in SOPool");
            check(false, "[RLManager::get_all_missiles] Null object in SOPool");
        } else {
            colorful::printHONG("[RLManager::get_all_missiles] Object type mismatch: expected Missile, got %d", static_cast<int>(obj->Type));
            check(false, "[RLManager::get_all_missiles] Object type mismatch: expected Missile");
        }
    }
    return missiles;
}

std::shared_ptr<Aircraft> RLManager::get_agent(const std::string& uid) const {
    auto all = SOPool::instance().get_all_ever_existed();
    std::shared_ptr<SimulatedObject> obj = nullptr;
    for (const auto& o : all) {
        if (o->uid == uid) {
            obj = o;
            break;
        }
    }

    if (obj && obj->Type == SOT::Aircraft) {
        auto agent = std::dynamic_pointer_cast<Aircraft>(obj);
        check(agent, "agent");
        return agent;
    } else {
        colorful::printHONG("[RLManager::get_agent] Object is not an aircraft or is nullptr.");
        check(false, "[RLManager::get_agent] Object is not an aircraft or is nullptr.");
    }
    return nullptr;
}

std::vector<double> RLManager::get_observation(const std::string& agent_uid) {
    const std::shared_ptr<Aircraft>& agent = get_agent(agent_uid);
    if (!agent) {
        colorful::printHUANG("[RLManager::get_observation] Agent %s not found.", agent_uid.c_str());
        SL::get().printf("[RLManager::get_observation] Agent %s not found.\n", agent_uid.c_str());
        return std::vector<double>();
    }

    auto all_agents = get_all_agents();
    auto all_missiles = get_all_missiles();

    if (obs_space_) {
        return obs_space_->extract_obs(agent, all_agents, all_missiles);
    }
    colorful::printHONG("[RLManager::get_observation] Observation space not set.");
    std::abort();

    return std::vector<double>();
}

double RLManager::get_reward(const std::string& agent_uid, const json::JSON& info) {
    const std::shared_ptr<Aircraft>& agent = get_agent(agent_uid);
    if (!agent) {
        SL::get().printf("[RLManager::get_reward] Error: Requesting Agent %s for reward can not be found.\n", agent_uid.c_str());
        colorful::printHUANG("[RLManager::get_reward] Error: Requesting Agent %s for reward can not be found.", agent_uid.c_str());
        return 0.0;
    }

    auto all_agents = get_all_agents();
    auto all_missiles = get_all_missiles();

    RewardInfo info_struct;

    if (info.hasKey("current_step", json::JSON::Class::Integral)) {
        info_struct.current_step = info.at("current_step").ToInt();
    }   
    else if (info.hasKey("current_step", json::JSON::Class::Floating)) {
        info_struct.current_step = static_cast<int>(info.at("current_step").ToFloat());
    }
    else {
        colorful::printHONG("[RLManager::get_reward] current_step is not integral or floating number.");
        check(false, "[RLManager::get_reward] current_step is not integral or floating number.");
    }

    if (info.hasKey("episode_done", json::JSON::Class::Boolean)) {
        info_struct.episode_done = info.at("episode_done").ToBool();
    }
    else {
        colorful::printHONG("[RLManager::get_reward] episode_done is not boolean.");
        check(false, "[RLManager::get_reward] episode_done is not boolean.");
    }

    return reward_manager_.compute_reward(agent, all_agents, all_missiles, info_struct);
}

bool RLManager::get_done(const std::string& agent_uid) {
    const std::shared_ptr<Aircraft>& agent = get_agent(agent_uid);
    if (!agent) {
        colorful::printHUANG("[RLManager::get_done] Warning: Agent %s not found.", agent_uid.c_str());
        SL::get().printf("[RLManager::get_done] Warning: Agent %s not found.\n", agent_uid.c_str());
        return false;
    }
    return !agent->is_alive;
}

bool RLManager::get_episode_done() {
    auto all_agents = get_all_agents();

    int red_alive = 0, blue_alive = 0;
    for (const auto& agent : all_agents) {
        if (agent && agent->is_alive) {
            if (agent->color == TeamColor::Red) red_alive++;
            else if (agent->color == TeamColor::Blue) blue_alive++;
        }
    }

    bool one_or_more_team_killed =  (red_alive == 0) || (blue_alive == 0);
    bool two_team_killed =  (red_alive == 0) && (blue_alive == 0);

    auto all_missiles = get_all_missiles();
    bool no_missile_flying = std::all_of(all_missiles.begin(), all_missiles.end(),
        [](const std::shared_ptr<Missile>& m) { return !m->is_alive; });

    bool episode_done = (one_or_more_team_killed && no_missile_flying) || two_team_killed;
    return episode_done;
}

std::vector<double> RLManager::get_baseline_action_vec(const std::string& agent_uid) {
    auto dict_action = BaselinePool::instance().get_action_cache(agent_uid);
    std::vector<double> res;
    if (dict_action.has_value()) {
        ActionSpace action_space(dict_action.value());
        res = {
            action_space.delta_heading(),
            action_space.delta_altitude(),
            action_space.delta_speed(),
            action_space.fire() ? 1.0 : 0.0
        };
    } else {
        res = {0.0, 0.0, 0.0, 0.0};
    }
    return res;
}

std::optional<json::JSON> RLManager::get_baseline_action(const std::string& agent_uid) {
    auto dict_action = BaselinePool::instance().get_action_cache(agent_uid);
    if (dict_action.has_value()) {
        action_space_check::check_action_json(dict_action.value());
        return dict_action.value();
    }
    return std::nullopt;
}


std::unordered_map<std::string, double> RLManager::get_reward_breakdown(const std::string& agent_uid) {
    return reward_manager_.get_reward_breakdown(agent_uid);
}

void RLManager::reset() {
    reward_manager_.reset();
}

void RLManager::load_reward_config(const std::string& config_path) {
    reward_manager_.load_config(config_path);
}
void RLManager::load_reward_config_str(const std::string& config_str) {
    reward_manager_.load_config_str(config_str);
}

void RLManager::set_observation_space(const std::string& obs_space_spec) {
    if (obs_space_spec == "entity") {
        obs_space_ = std::make_shared<EntityObsSpace>();
    } else {
        colorful::printHUANG("[RLManager::set_observation_space] Not implemented yet.");
        // obs_space_ = std::make_shared<EntityObsSpace>(obs_space_spec);
    }
}

int RLManager::get_obs_dim() const {
    auto red_agents = SOPool::instance().get_by_color(TeamColor::Red);
    auto blue_agents = SOPool::instance().get_by_color(TeamColor::Blue);
    int num_red_ = static_cast<int>(red_agents.size());
    int num_blue_ = static_cast<int>(blue_agents.size());

    if (num_red_ <= 0 || num_blue_ <= 0) {
        check(false, "No agent of red or blue team.");
    }

    if (obs_space_) {
        return obs_space_->get_obs_dim(num_red_, num_blue_);
    }
    colorful::printHONG("[RLManager::get_obs_dim] Observation space not set.");
    check(false, "Observation space is nullptr.");
    return 0;
}


}
