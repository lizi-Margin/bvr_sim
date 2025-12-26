#include "observation_space.hxx"
#include "simulator/simulator.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/missile/base.hxx"
#include "c3utils/funcs.hxx"
#include "rubbish_can/check.hxx"

namespace bvr_sim {

EntityObsSpace::EntityObsSpace(int max_team_missiles, int max_enemy_missiles)
    : ObservationSpace("entity"),
      norm_pos_(50000.0f),
      norm_vel_(600.0f),
      norm_alt_(10000.0f),
      max_team_missiles_(max_team_missiles),
      max_enemy_missiles_(max_enemy_missiles),
      entity_dim_(35) {}

int EntityObsSpace::get_obs_dim(int num_red, int num_blue) const {
    int n_enemies = num_blue;
    int n_allies = num_red - 1;
    int n_entities = 1 + n_enemies + n_allies + max_team_missiles_ + max_enemy_missiles_;
    return n_entities * entity_dim_;
}

std::vector<double> EntityObsSpace::extract_obs(
    const std::shared_ptr<Aircraft>& agent,
    const std::vector<std::shared_ptr<Aircraft>>& all_agents,
    const std::vector<std::shared_ptr<Missile>>& all_missiles) const {

    std::vector<double> obs;

    if (!agent || !agent->is_alive) {
        int obs_dim = get_obs_dim(
            static_cast<int>(std::count_if(all_agents.begin(), all_agents.end(),
                [](const std::shared_ptr<Aircraft>& a) { return a && a->color == TeamColor::Red; })),
            static_cast<int>(std::count_if(all_agents.begin(), all_agents.end(),
                [](const std::shared_ptr<Aircraft>& a) { return a && a->color == TeamColor::Blue; }))
        );
        obs.resize(obs_dim, 0.0f);
        return obs;
    }

    auto entity_features = extract_entity_features(agent, agent, all_missiles, true);
    obs.insert(obs.end(), entity_features.begin(), entity_features.end());

    for (const auto& enemy : all_agents) {
        if (enemy && enemy->color != agent->color) {
            if (enemy->is_alive) {
                entity_features = extract_entity_features(agent, enemy, all_missiles, false);
            } else {
                entity_features.assign(entity_dim_, 0.0f);
            }
            obs.insert(obs.end(), entity_features.begin(), entity_features.end());
        }
    }

    for (const auto& ally : all_agents) {
        if (ally && ally->color == agent->color && ally->uid != agent->uid) {
            if (ally->is_alive) {
                entity_features = extract_entity_features(agent, ally, all_missiles, false);
            } else {
                entity_features.assign(entity_dim_, 0.0f);
            }
            obs.insert(obs.end(), entity_features.begin(), entity_features.end());
        }
    }

    std::vector<std::shared_ptr<Missile>> team_missiles;
    for (const auto& missile : all_missiles) {
        if (missile && missile->color == agent->color && missile->is_alive) {
            team_missiles.push_back(missile);
        }
    }
    std::sort(team_missiles.begin(), team_missiles.end(),
        [agent](const std::shared_ptr<const Missile>& a, const std::shared_ptr<const Missile>& b) {
            check(a, "a");
            check(b, "b");
            if (!a->is_alive) return false;
            if (!b->is_alive) return true;
            double dist_a = c3utils::linalg_norm(
                std::array<double, 3>{a->position[0] - agent->position[0],
                                     a->position[1] - agent->position[1],
                                     a->position[2] - agent->position[2]});
            double dist_b = c3utils::linalg_norm(
                std::array<double, 3>{b->position[0] - agent->position[0],
                                     b->position[1] - agent->position[1],
                                     b->position[2] - agent->position[2]});
            return dist_a < dist_b;
        });

    for (int i = 0; i < max_team_missiles_; ++i) {
        
        if (i < static_cast<int>(team_missiles.size())) {
            check(team_missiles[i], "team_missiles[i]");
            if (team_missiles[i]->is_alive) {
                entity_features = extract_entity_features(agent, team_missiles[i], all_missiles, false, true);
            }
        } else {
            entity_features.assign(entity_dim_, 0.0f);
        }
        obs.insert(obs.end(), entity_features.begin(), entity_features.end());
    }

    std::vector<std::shared_ptr<Missile>> enemy_missiles;
    for (const auto& missile : all_missiles) {
        if (missile && missile->color != agent->color && missile->is_alive) {
            enemy_missiles.push_back(missile);
        }
    }
    std::sort(enemy_missiles.begin(), enemy_missiles.end(),
        [agent](const std::shared_ptr<const Missile>& a, const std::shared_ptr<const Missile>& b) {
            check(a, "a");
            check(b, "b");
            if (!a->is_alive) return false;
            if (!b->is_alive) return true;
            double dist_a = c3utils::linalg_norm(
                std::array<double, 3>{a->position[0] - agent->position[0],
                                     a->position[1] - agent->position[1],
                                     a->position[2] - agent->position[2]});
            double dist_b = c3utils::linalg_norm(
                std::array<double, 3>{b->position[0] - agent->position[0],
                                     b->position[1] - agent->position[1],
                                     b->position[2] - agent->position[2]});
            return dist_a < dist_b;
        });

    for (int i = 0; i < max_enemy_missiles_; ++i) {
        if (i < static_cast<int>(enemy_missiles.size())) {
            check(enemy_missiles[i], "enemy_missiles[i]");
            if (enemy_missiles[i]->is_alive) {
                entity_features = extract_entity_features(agent, enemy_missiles[i], all_missiles, false, true);
            }
        } else {
            entity_features.assign(entity_dim_, 0.0f);
        }
        obs.insert(obs.end(), entity_features.begin(), entity_features.end());
    }

    return obs;
}

std::vector<double> EntityObsSpace::extract_entity_features(
    const std::shared_ptr<Aircraft>& agent,
    const std::shared_ptr<SimulatedObject>& target,
    const std::vector<std::shared_ptr<Missile>>& all_missiles,
    bool is_self,
    bool is_missile) const {

    std::vector<double> features(entity_dim_, 0.0f);

    check(target, "target");
    if (is_self) {
        check(target == agent, "check");
        check(target->Type == SOT::Aircraft, "The ego agent, Type must be SOT::Aircraft");
        auto self_aircraft = std::dynamic_pointer_cast<const Aircraft>(target);
        check(self_aircraft, "self_aircraft");

        double speed = c3utils::linalg_norm(
            std::array<double, 3>{self_aircraft->velocity[0],
                                 self_aircraft->velocity[1],
                                 self_aircraft->velocity[2]});
        double mach = c3utils::get_mach(speed, self_aircraft->position[2]);
        features[12] = std::min(mach / 1.5f, 10.0);

        features[13] = self_aircraft->position[2] / norm_alt_;
        features[14] = 0.0f;

        features[15] = std::sin(self_aircraft->get_heading());
        features[16] = std::cos(self_aircraft->get_heading());
        features[17] = std::sin(self_aircraft->get_pitch());
        features[18] = std::cos(self_aircraft->get_pitch());

        features[19] = 1.0f;  // is_self
        features[20] = 0.0f;  // is_enemy
        features[21] = 0.0f;  // is_ally
        features[22] = 0.0f;  // is_missile
        features[23] = 0.0f;  // reserved

        features[26] = self_aircraft->under_missiles.size() > 0 ? 1.0f : 0.0f;  // has missile fire on this target
        features[27] = std::min(static_cast<float>(self_aircraft->under_missiles.size()) / 4.0f, 10.0f);  // num missiles fired on this target
        features[28] = std::min(static_cast<float>(agent->launched_missiles.size()) / 4.0f, 10.0f);  // num missiles fired
        features[29] = std::min(static_cast<float>(agent->launched_missiles.size()) / 4.0f, 10.0f);  // num missiles fired Special For Ego

        features[31] = self_aircraft->can_shoot() ? 1.0f : 0.0f;
        return features;
    }

    if (is_missile) {
        check(target->Type == SOT::Missile, "must be SOT::Missile");
        auto target_missile = std::dynamic_pointer_cast<const Missile>(target);
        check(target_missile, "target_missile");
        if (!target_missile->is_alive) {
            return features;
        }
    }
    else {
        check(target->Type == SOT::Aircraft, "must be SOT::Aircraft");
        if (!target->is_alive) {
            return features;
        }
    }

    std::array<double, 3> rel_pos{
        target->position[0] - agent->position[0],
        target->position[1] - agent->position[1],
        target->position[2] - agent->position[2]
    };
    std::array<double, 3> rel_vel{
        target->velocity[0] - agent->velocity[0],
        target->velocity[1] - agent->velocity[1],
        target->velocity[2] - agent->velocity[2]
    };

    features[0] = rel_pos[0] / norm_pos_;
    features[1] = rel_pos[1] / norm_pos_;
    features[2] = rel_pos[2] / norm_alt_;
    features[3] = rel_vel[0] / norm_vel_;
    features[4] = rel_vel[1] / norm_vel_;
    features[5] = rel_vel[2] / norm_vel_;

    double distance = c3utils::linalg_norm(rel_pos);
    double range_nm = c3utils::meters_to_nm(distance);
    features[6] = std::min(range_nm / 30.0, 2.0);

    double horizontal_range = c3utils::linalg_norm(std::array<double, 2>{rel_pos[0], rel_pos[1]});
    double azimuth_rad = 0.0f;
    double elevation_rad = 0.0f;

    if (horizontal_range > 1e-6f) {
        azimuth_rad = std::atan2(rel_pos[1], rel_pos[0]) - agent->get_heading();
        azimuth_rad = std::atan2(std::sin(azimuth_rad), std::cos(azimuth_rad));
        elevation_rad = std::atan2(rel_pos[2], horizontal_range);
    }

    features[7] = std::sin(azimuth_rad);
    features[8] = std::cos(azimuth_rad);
    features[9] = std::sin(elevation_rad);
    features[10] = std::cos(elevation_rad);

    if (distance > 1e-6f) {
        double radial_velocity = (rel_pos[0] * rel_vel[0] + rel_pos[1] * rel_vel[1] + rel_pos[2] * rel_vel[2]) / distance;
        features[11] = std::min(std::max(radial_velocity / norm_vel_, -1.0), 1.0);
    } else {
        features[11] = 0.0f;
    }

    double target_speed = c3utils::linalg_norm(
        std::array<double, 3>{target->velocity[0], target->velocity[1], target->velocity[2]});
    double target_mach = c3utils::get_mach(target_speed, target->position[2]);
    features[12] = std::min(target_mach / 3.0, 1.0);

    double target_alt = target->position[2];
    features[13] = target_alt / norm_alt_;

    double alt_diff = target_alt - agent->position[2];
    features[14] = alt_diff / norm_alt_;

    features[15] = std::sin(target->get_heading());
    features[16] = std::cos(target->get_heading());
    if (target->Type == SOT::Aircraft) {
        auto target_aircraft = std::dynamic_pointer_cast<const Aircraft>(target);
        check(target_aircraft, "target_aircraft");
        features[17] = std::sin(target_aircraft->get_pitch());
        features[18] = std::cos(target_aircraft->get_pitch());
    }

    bool is_enemy = (target->color != agent->color);
    bool is_ally = (target->color == agent->color) && (target->uid != agent->uid);

    features[19] = 0.0f;  // is ego
    features[20] = is_enemy ? 1.0f : 0.0f;
    features[21] = is_ally ? 1.0f : 0.0f;
    features[22] = is_missile ? 1.0f : 0.0f;
    features[23] = 0.0f;  // reserved

    if (!is_missile) {
        auto target_aircraft = std::dynamic_pointer_cast<const Aircraft>(target);
        check(target_aircraft, "target_aircraft");
        int has_missile_num = 0;
        for (const auto& missile : agent->launched_missiles) {
            check(missile, "missile");
            if (!missile->is_alive) {
                continue;
            }
            if (missile->target->uid == target->uid) {
                has_missile_num++;
            }
        }
        features[24] = has_missile_num > 0 ? 1.0f : 0.0f;  //has missile fire on this target from ego
        features[25] = std::min(static_cast<float>(has_missile_num) / 4.0f, 10.0f);  // num missiles fired on this target from ego

        features[26] = target_aircraft->under_missiles.size() > 0 ? 1.0f : 0.0f;  // has missile fire on this target
        features[27] = std::min(static_cast<float>(target_aircraft->under_missiles.size()) / 4.0f, 10.0f);  // num missiles fired on this target
        features[28] = std::min(static_cast<float>(target_aircraft->launched_missiles.size()) / 4.0f, 10.0f);  // num missiles fired
        features[29] = 0.0;  // num missiles fired Special For Ego
    } else {
        features[24] = 0.0f;
        features[25] = 0.0f;
        features[26] = 0.0f;
        features[27] = 0.0f;
        features[28] = 0.0f;
        features[29] = 0.0f;
    }


    features[30] = 0.0f;
    if (is_missile) {
        check(target->Type == SOT::Missile, "must be SOT::Missile");
        auto target_missile = std::dynamic_pointer_cast<const Missile>(target);
        check(target_missile, "target_missile");
        check(target_missile->target, "target_missile->target");
        if (target_missile->is_alive) {
            double target_dist = c3utils::linalg_norm(
                std::array<double, 3>{target_missile->target->position[0] - target_missile->position[0],
                                      target_missile->target->position[1] - target_missile->position[1],
                                      target_missile->target->position[2] - target_missile->position[2]});
            double speed = target_missile->get_speed();
            double tti = speed > 0 ? target_dist / (speed + 1e-8) : 0.0;
            features[30] = std::min(tti / 60.0, 1.0);
        }
    }
    
    bool this_entity_can_shoot = false;
    if (!is_missile) {
        auto this_aircraft = std::dynamic_pointer_cast<const Aircraft>(target);
        check(this_aircraft, "this_aircraft");
        this_entity_can_shoot = this_aircraft->can_shoot();
    }
    features[31] = this_entity_can_shoot ? 1.0f : 0.0f;

    bool locked = false;
    if (!is_missile) {
        for (const auto& e_l : agent->enemies_lock) {
            if (e_l->uid == target->uid) {
                locked = true;
                break;
            }
        }
    }
    features[32] = locked ? 1.0f : 0.0f;


    bool if_you_shoot__you_shoot_this = false;
    if (!agent->enemies_lock.empty()) {
        if (agent->enemies_lock[0]->uid == target->uid) {
            if_you_shoot__you_shoot_this = true;
        }
    }
    features[33] = if_you_shoot__you_shoot_this ? 1.0f : 0.0f;
    features[34] = if_you_shoot__you_shoot_this ? 1.0f : 0.0f;


    return features;
}

}
