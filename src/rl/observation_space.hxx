#pragma once

#include <vector>
#include <string>
#include <memory>
#include <cmath>
#include <algorithm>
#include "../c3utils/c3utils.hxx"

namespace bvr_sim {

class Aircraft;
class Missile;
class SimulatedObject;

class ObservationSpace {
public:
    ObservationSpace(const std::string& name = "base") : name_(name) {}
    virtual ~ObservationSpace() = default;

    virtual int get_obs_dim(int num_red, int num_blue) const = 0;

    virtual std::vector<double> extract_obs(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles
    ) const = 0;

    const std::string& get_name() const { return name_; }

protected:
    std::string name_;
};

class EntityObsSpace : public ObservationSpace {
public:
    EntityObsSpace(int max_team_missiles = 4, int max_enemy_missiles = 2);

    int get_obs_dim(int num_red, int num_blue) const override;

    std::vector<double> extract_obs(
        const std::shared_ptr<Aircraft>& agent,
        const std::vector<std::shared_ptr<Aircraft>>& all_agents,
        const std::vector<std::shared_ptr<Missile>>& all_missiles
    ) const override;

private:
    std::vector<double> extract_entity_features(
        const std::shared_ptr<Aircraft>& agent,
        const std::shared_ptr<SimulatedObject>& target,
        const std::vector<std::shared_ptr<Missile>>& all_missiles,
        bool is_self = false,
        bool is_missile = false
    ) const;

    double norm_pos_;
    double norm_vel_;
    double norm_alt_;
    int max_team_missiles_;
    int max_enemy_missiles_;

    size_t entity_dim_;
};

}
