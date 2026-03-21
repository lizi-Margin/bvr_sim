#include "reward_components.hxx"
#include "simulator/simulator.hxx"
#include "simulator/simulator.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/missile/base.hxx"
#include "global_config.hxx"
#include "c3utils/funcs.hxx"
#include "rubbish_can/check.hxx"
#include <algorithm>
#include <cmath>

namespace bvr_sim {

// constexpr auto MISSILE_REWARD_MSSILE_SPEC = "";
constexpr auto MISSILE_REWARD_MSSILE_SPEC = "AIM";


EngageEnemyReward::EngageEnemyReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double EngageEnemyReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    std::vector<std::shared_ptr<const Aircraft>> alive_enemies;
    for (const auto& a : all_agents) {
        check(a, "Agent is null");
        if (a->color != agent->color && a->is_alive) {
            alive_enemies.push_back(a);
        }
    }

    if (alive_enemies.empty()) return 0.0;

    auto nearest_enemy = alive_enemies[0];
    double min_dist = c3utils::linalg_norm(
        std::array<double, 3>{nearest_enemy->position[0] - agent->position[0],
                             nearest_enemy->position[1] - agent->position[1],
                             nearest_enemy->position[2] - agent->position[2]});

    for (const auto& enemy : alive_enemies) {
        double dist = c3utils::linalg_norm(
            std::array<double, 3>{enemy->position[0] - agent->position[0],
                                 enemy->position[1] - agent->position[1],
                                 enemy->position[2] - agent->position[2]});
        if (dist < min_dist) {
            min_dist = dist;
            nearest_enemy = enemy;
        }
    }

    double current_distance = min_dist;
    double reward = 0.0;
    const double MAX_REL_SPEED = 500.0; // max relative speed

    check(cfg::dt > 0.0, "dt is not initialized");
    double delta_max = MAX_REL_SPEED * cfg::dt;

    auto it = last_distances_.find(agent->uid);
    if (it != last_distances_.end()) {
        double distance_delta = it->second - current_distance;
        distance_delta = distance_delta - delta_max;
        reward = distance_delta / delta_max;
    }

    last_distances_[agent->uid] = current_distance;
    return reward;
}

void EngageEnemyReward::reset() {
    last_distances_.clear();
}

EnemyTrackingReward::EnemyTrackingReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double EnemyTrackingReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    if (agent->enemies_lock.empty()) {
        return 0.0;
    }

    return static_cast<double>(agent->enemies_lock.size()) * 1.0;
}

EnemyDistanceReward::EnemyDistanceReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double EnemyDistanceReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    if (!agent || !agent->is_alive) return 0.0;

    std::vector<std::shared_ptr<const Aircraft>> alive_enemies;
    for (const auto& a : all_agents) {
        if (a && a->color != agent->color && a->is_alive) {
            alive_enemies.push_back(a);
        }
    }

    if (alive_enemies.empty()) return 0.0;

    auto nearest_enemy = alive_enemies[0];
    double min_dist = c3utils::linalg_norm(
        std::array<double, 3>{nearest_enemy->position[0] - agent->position[0],
                             nearest_enemy->position[1] - agent->position[1],
                             nearest_enemy->position[2] - agent->position[2]});

    for (const auto& enemy : alive_enemies) {
        double dist = c3utils::linalg_norm(
            std::array<double, 3>{enemy->position[0] - agent->position[0],
                                 enemy->position[1] - agent->position[1],
                                 enemy->position[2] - agent->position[2]});
        if (dist < min_dist) {
            min_dist = dist;
            nearest_enemy = enemy;
        }
    }

    double current_distance = min_dist;
    const double MAX_DIS = c3utils::nm_to_meters(40.0);
    const double MIN_DIS = c3utils::nm_to_meters(10.0);
    current_distance = std::min(std::max(current_distance, MIN_DIS), MAX_DIS);
    double reward = -(current_distance - MIN_DIS) / (MAX_DIS - MIN_DIS);

    return reward;
}

AltitudeAdvantageReward::AltitudeAdvantageReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double AltitudeAdvantageReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    std::vector<std::shared_ptr<const Aircraft>> alive_enemies;
    for (const auto& a : all_agents) {
        check(a, "Agent is null");
        if (a->color != agent->color && a->is_alive) {
            alive_enemies.push_back(a);
        }
    }

    if (alive_enemies.empty()) return 0.0;

    double total_alt_advantage = 0.0;
    for (const auto& enemy : alive_enemies) {
        double alt_diff = agent->position[2] - enemy->position[2];
        // total_alt_advantage += alt_diff / 1000.0;
        total_alt_advantage += alt_diff / 10000.0;   // fix: norm by 1万 meter, ~32000ft
    }

    double avg_alt_advantage = total_alt_advantage / alive_enemies.size();
    // return avg_alt_advantage;
    return c3u::norm(avg_alt_advantage, -1.0, 1.0);  // 现在用1万米做norm, 加上这个clip应该没事了, 相当于reward大小除了10, reward权重可以乘10
}

SafeAltitudeReward::SafeAltitudeReward(double weight, double safe_min, double safe_max, const std::string& name)
    : RewardComponent(weight, name), safe_min_(safe_min), safe_max_(safe_max) {}

double SafeAltitudeReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    if (!agent || !agent->is_alive) return 0.0;

    double altitude = agent->position[2];

    if (altitude >= safe_min_ && altitude <= safe_max_) {
        return 1.0;
    } else if (altitude < safe_min_) {
        double deficit = safe_min_ - altitude;
        double penalty = -deficit / 1000.0;
        return std::min(std::max(penalty, -2.0), 0.0);
    } else {
        double excess = altitude - safe_max_;
        double penalty = -excess / 1000.0;
        return std::min(std::max(penalty, -2.0), 0.0);
    }
}

MissileLaunchReward::MissileLaunchReward(double weight, double launch_reward,
                                         double duplicated_launch_penalty, const std::string& name)
    : RewardComponent(weight, name), launch_reward_(launch_reward),
      duplicated_launch_penalty_(duplicated_launch_penalty) {}

double MissileLaunchReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    std::unordered_map<std::string, int> current_missiles_map;
    for (const auto& missile : agent->launched_missiles) {
        check(missile, "Missile is null");
        check(missile->parent, "Missile parent is null");
        check(missile->parent->uid == agent->uid, "Missile parent is not the agent");
        if (missile->is_alive) {
            if (missile->target) {
                current_missiles_map[missile->target->uid]++;
            }
        }
    }

    double reward = 0.0;
    auto agent_it = last_missile_counts_map_.find(agent->uid);

    if (agent_it != last_missile_counts_map_.end()) {
        const auto& last_map = agent_it->second;
        for (const auto& [target_uid, current_count] : current_missiles_map) {
            auto target_it = last_map.find(target_uid);
            int last_count = (target_it != last_map.end()) ? target_it->second : 0;

            if (current_count > last_count) {
                if (current_count >= 2) {
                    reward = duplicated_launch_penalty_ * (current_count - 1);
                } else {
                    reward = launch_reward_;
                }
                break;  /// Only count the first launch
            }
        }
    }

    last_missile_counts_map_[agent->uid] = current_missiles_map;
    return reward;
}

void MissileLaunchReward::reset() {
    last_missile_counts_map_.clear();
}

MissileResultReward::MissileResultReward(double weight, double hit_reward, double miss_penalty, const std::string& name)
    : RewardComponent(weight, name), hit_reward_(hit_reward), miss_penalty_(miss_penalty) {}

double MissileResultReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    double reward = 0.0;

    for (const auto& missile : all_missiles) {
        if (!missile) continue;

        if (tracked_missiles_.find(missile->uid) != tracked_missiles_.end()) {
            continue;
        }

        if (missile->is_done) {
            tracked_missiles_.insert(missile->uid);

            if (missile->is_success) {
                reward += hit_reward_;
            } else {
                reward += miss_penalty_;
            }
        }
    }

    return reward;
}

void MissileResultReward::reset() {
    tracked_missiles_.clear();
}

MissileEvasionReward::MissileEvasionReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double MissileEvasionReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!agent->is_alive) return 0.0;

    std::vector<std::shared_ptr<const Missile>> enemy_missiles;
    for (const auto& missile : all_missiles) {
        check(missile, "Missile is null");
        if (missile->is_alive && missile->color != agent->color) {
            check(missile->target, "Missile target is null");
            bool target_is_me = missile->target->uid == agent->uid;
            bool radar_active = missile->radar_on;
            if (target_is_me && radar_active) {
                enemy_missiles.push_back(missile);
            }
        }
    }

    double reward = 0.0;
    std::string agent_key = agent->uid;

    if (!enemy_missiles.empty()) {
        auto closest_missile = enemy_missiles[0];
        double min_dist = c3utils::linalg_norm(
            std::array<double, 3>{closest_missile->position[0] - agent->position[0],
                                 closest_missile->position[1] - agent->position[1],
                                 closest_missile->position[2] - agent->position[2]});

        for (const auto& missile : enemy_missiles) {
            check(missile, "Missile target is null");
            double dist = c3utils::linalg_norm(
                std::array<double, 3>{missile->position[0] - agent->position[0],
                                     missile->position[1] - agent->position[1],
                                     missile->position[2] - agent->position[2]});
            if (dist < min_dist) {
                min_dist = dist;
                closest_missile = missile;
            }
        }

        double current_distance = min_dist;
        std::string missile_key = closest_missile->uid;

        auto agent_it = last_missile_distances_.find(agent_key);
        if (agent_it != last_missile_distances_.end()) {
            auto& missile_map = agent_it->second;
            auto missile_it = missile_map.find(missile_key);
            if (missile_it != missile_map.end()) {
                double distance_delta = current_distance - missile_it->second;
                if (distance_delta < 0) {
                    reward += distance_delta / 500.0;
                }
            }
            missile_map[missile_key] = current_distance;
        } else {
            last_missile_distances_[agent_key][missile_key] = current_distance;
        }
    } else {
        if (last_missile_distances_.find(agent_key) != last_missile_distances_.end()) {
            last_missile_distances_[agent_key].clear();
        }
    }

    return reward;
}

void MissileEvasionReward::reset() {
    last_missile_distances_.clear();
}

SpeedReward::SpeedReward(double weight, double target_speed, const std::string& name)
    : RewardComponent(weight, name), target_speed_(target_speed) {}

double SpeedReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    if (!agent || !agent->is_alive) return 0.0;

    double speed = c3utils::linalg_norm(
        std::array<double, 3>{agent->velocity[0], agent->velocity[1], agent->velocity[2]});
    double speed_ratio = std::min(speed / target_speed_, 1.0);

    return speed_ratio;
}

SurvivalReward::SurvivalReward(double weight, const std::string& name)
    : RewardComponent(weight, name) {}

double SurvivalReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    if (!agent) return 0.0;
    return agent->is_alive ? 1.0 : 0.0;
}

WinLossReward::WinLossReward(double weight, double win_reward, double loss_penalty, const std::string& name)
    : RewardComponent(weight, name), win_reward_(win_reward), loss_penalty_(loss_penalty) {}

double WinLossReward::compute(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    const RewardInfo& info) {

    check(agent, "Agent is null");
    if (!info.episode_done) {
        return 0.0;
    }
    // colorful::printHUANG("WinLossReward: episode_done is true");

    int red_alive = 0, blue_alive = 0;
    for (const auto& a : all_agents) {
        check(a, "Agent is null");
        if (a->is_alive) {
            if (a->color == TeamColor::Red) red_alive++;
            else if (a->color == TeamColor::Blue) blue_alive++;
        }
    }

    if (red_alive > blue_alive) {
        return agent->color == TeamColor::Red ? win_reward_ : loss_penalty_;
    } else if (blue_alive > red_alive) {
        return agent->color == TeamColor::Blue ? win_reward_ : loss_penalty_;
    } else {
        return 0.0;
    }
}

}
