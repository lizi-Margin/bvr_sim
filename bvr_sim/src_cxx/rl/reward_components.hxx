#pragma once

#include <string>
#include <vector>
#include <unordered_map>
#include <unordered_set>
#include <memory>
#include "../c3utils/c3utils.hxx"

namespace bvr_sim {

class Aircraft;
class Missile;

struct RewardInfo {
    int current_step;
    bool episode_done;
};

class RewardComponent {
public:
    RewardComponent(double weight = 1.0, const std::string& name = "base")
        : weight_(weight), name_(name), enabled_(weight != 0.0) {}

    virtual ~RewardComponent() = default;

    virtual double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) = 0;

    double operator()(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) {
        if (!enabled_) return 0.0;
        return weight_ * compute(agent, all_agents, all_missiles, info);
    }

    virtual void reset() = 0;

    const std::string& get_name() const { return name_; }
    double get_weight() const { return weight_; }
    void set_weight(double weight) { weight_ = weight; enabled_ = (weight != 0.0); }

protected:
    double weight_;
    std::string name_;
    bool enabled_;
};

class EngageEnemyReward : public RewardComponent {
public:
    EngageEnemyReward(double weight = 0.01, const std::string& name = "engage_enemy");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override;

private:
    std::unordered_map<std::string, double> last_distances_;
};

class EnemyTrackingReward : public RewardComponent {
public:
    EnemyTrackingReward(double weight = 0.01, const std::string& name = "enemy_tracking");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}
};

class EnemyDistanceReward : public RewardComponent {
public:
    EnemyDistanceReward(double weight = 0.01, const std::string& name = "enemy_distance");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}
};

class AltitudeAdvantageReward : public RewardComponent {
public:
    AltitudeAdvantageReward(double weight = 0.005, const std::string& name = "altitude_advantage");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}
};

class SafeAltitudeReward : public RewardComponent {
public:
    SafeAltitudeReward(double weight = 0.01, double safe_min = 2000.0,
                       double safe_max = 12000.0, const std::string& name = "safe_altitude");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}

public:
    double safe_min_;
    double safe_max_;
};

class MissileLaunchReward : public RewardComponent {
public:
    MissileLaunchReward(double weight = 1.0, double launch_reward = 1.0,
                        double duplicated_launch_penalty = 1.0,
                        const std::string& name = "missile_launch");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override;

private:
    std::unordered_map<std::string, std::unordered_map<std::string, int>> last_missile_counts_map_;
public:
    double launch_reward_;
    double duplicated_launch_penalty_;
};

class MissileResultReward : public RewardComponent {
public:
    MissileResultReward(double weight = 1.0, double hit_reward = 100.0,
                        double miss_penalty = -5.0, const std::string& name = "missile_result");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override;

public:
    double hit_reward_;
    double miss_penalty_;
private:
    std::unordered_set<std::string> tracked_missiles_;
};

class MissileEvasionReward : public RewardComponent {
public:
    MissileEvasionReward(double weight = 0.02, const std::string& name = "missile_evasion");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override;

private:
    std::unordered_map<std::string, std::unordered_map<std::string, double>> last_missile_distances_;
};

class SpeedReward : public RewardComponent {
public:
    SpeedReward(double weight = 0.005, double target_speed = 600.0,
                const std::string& name = "speed");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}

public:
    double target_speed_;
};

class SurvivalReward : public RewardComponent {
public:
    SurvivalReward(double weight = 0.01, const std::string& name = "survival");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}
};

class WinLossReward : public RewardComponent {
public:
    WinLossReward(double weight = 1.0, double win_reward = 200.0,
                  double loss_penalty = -200.0, const std::string& name = "win_loss");

    double compute(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        const RewardInfo& info) override;

    void reset() override {}

public:
    double win_reward_;
    double loss_penalty_;
};

}
