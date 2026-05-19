#include "standoff.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/missile/base.hxx"
#include "simulator/pylon_manager.hxx"
#include "support/support.hxx"
#include "global_config.hxx"
#include "c3utils/funcs.hxx"
#include <algorithm>
#include <cmath>

namespace bvr_sim {

namespace {
constexpr double kCrankAngleDeg = 50.0;
constexpr double kSupportSpeedMach = 0.8;
constexpr double kDefensiveSpeedMach = 1.0;
constexpr double kCrankSwitchSec = 100.0;
}

StandoffOpponent3D::StandoffOpponent3D() noexcept
    : BaseOpponent3D("Standoff3D"),
      last_shoot_time(-static_cast<int>(30.0 / cfg::dt)),
      crank_direction(randomize_crank_direction()),
      crank_switch_time(0) {
}

void StandoffOpponent3D::take_action(
    std::shared_ptr<Aircraft> agent,
    const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
    const std::vector<std::shared_ptr<SimulatedObject>>& partners,
    const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
) {
    time_counter++;

    if (!agent->is_alive) {
        return;
    }

    std::vector<std::shared_ptr<Aircraft>> alive_enemies;
    if (!agent->enemies_lock.empty()) {
        alive_enemies = agent->enemies_lock;
    } else {
        for (const auto& enemy : enemies) {
            if (enemy->is_alive && enemy->Type == SOT::Aircraft) {
                auto e = std::dynamic_pointer_cast<Aircraft>(enemy);
                check(e, "StandoffOpponent3D::take_action: dynamic cast failed");
                alive_enemies.push_back(e);
            }
        }
        std::sort(alive_enemies.begin(), alive_enemies.end(),
            [&agent](const std::shared_ptr<Aircraft>& a, const std::shared_ptr<Aircraft>& b) {
                check(a, "StandoffOpponent3D::take_action: a is null");
                check(b, "StandoffOpponent3D::take_action: b is null");
                double dist_a = c3utils::linalg_norm_vec(c3utils::Vector3(
                    a->position[0] - agent->position[0],
                    a->position[1] - agent->position[1],
                    a->position[2] - agent->position[2]
                ));
                double dist_b = c3utils::linalg_norm_vec(c3utils::Vector3(
                    b->position[0] - agent->position[0],
                    b->position[1] - agent->position[1],
                    b->position[2] - agent->position[2]
                ));
                dist_a += static_cast<double>(a->under_missiles.size()) * 10000.0;
                dist_b += static_cast<double>(b->under_missiles.size()) * 10000.0;
                return dist_a < dist_b;
            }
        );
    }

    if (alive_enemies.empty()) {
        double delta_heading, delta_altitude, delta_speed;
        bool shoot;
        json::JSON fire_action_json;
        get_default_action(agent, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
        auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
        apply_action(agent, final_action, fire_action_json);
        return;
    }

    auto target = alive_enemies.front();
    std::vector<std::shared_ptr<Missile>> missiles_in_flight;
    for (const auto& missile : agent->launched_missiles) {
        if (missile->is_alive && missile->target /* && missile->target->uid == target->uid */) {
            missiles_in_flight.push_back(missile);
        }
    }

    std::vector<std::shared_ptr<Missile>> active_missiles = get_active_missile(missiles_targeting_me);

    double delta_heading, delta_altitude, delta_speed;
    bool shoot;
    json::JSON fire_action_json = json::JSON::Make(json::JSON::Class::Object);

    if (!active_missiles.empty()) {
        defensive_abort(agent, active_missiles, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
    } else if (!missiles_in_flight.empty()) {
        support_crank(agent, target, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
    } else {
        shoot_and_crank(agent, target, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
    }

    auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
    apply_action(agent, final_action, fire_action_json);
}

std::vector<std::shared_ptr<Missile>> StandoffOpponent3D::get_active_missile(
    const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
) const noexcept {
    std::vector<std::shared_ptr<Missile>> active_missile;
    for (const auto& missile : missiles_targeting_me) {
        if (!missile->is_alive) {
            continue;
        }
        if (missile->radar_on) {
            active_missile.push_back(missile);
        }
    }
    return active_missile;
}

void StandoffOpponent3D::defensive_abort(
    std::shared_ptr<Aircraft> agent,
    const std::vector<std::shared_ptr<Missile>>& missiles,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) const noexcept {
    auto closest_missile = *std::min_element(missiles.begin(), missiles.end(),
        [&agent](const std::shared_ptr<Missile>& a, const std::shared_ptr<Missile>& b) {
            double dist_a = c3utils::linalg_norm_vec(c3utils::Vector3(
                a->position[0] - agent->position[0],
                a->position[1] - agent->position[1],
                a->position[2] - agent->position[2]
            ));
            double dist_b = c3utils::linalg_norm_vec(c3utils::Vector3(
                b->position[0] - agent->position[0],
                b->position[1] - agent->position[1],
                b->position[2] - agent->position[2]
            ));
            return dist_a < dist_b;
        });

    c3utils::Vector3 rel_pos(
        closest_missile->position[0] - agent->position[0],
        closest_missile->position[1] - agent->position[1],
        closest_missile->position[2] - agent->position[2]
    );
    const double missile_heading = std::atan2(rel_pos[1], rel_pos[0]);
    const double desired_heading = missile_heading + c3u::pi;
    delta_heading = get_heading_action(agent, desired_heading);

    delta_altitude = 0.0;

    const double target_speed = c3u::get_mps(kDefensiveSpeedMach, agent->get_altitude());
    delta_speed = (target_speed - agent->get_speed()) * 0.7;

    shoot = false;
    fire = json::JSON();
}

void StandoffOpponent3D::shoot_and_crank(
    std::shared_ptr<Aircraft> agent,
    std::shared_ptr<Aircraft> target,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) noexcept {
    const double desired_heading = get_crank_heading(agent, target);
    delta_heading = get_heading_action(agent, desired_heading);

    delta_altitude = 0.0;

    const double target_speed = c3u::get_mps(kSupportSpeedMach, agent->get_altitude());
    delta_speed = (target_speed - agent->get_speed()) * 0.6;

    shoot = true;
    fire = get_fire_action(agent, target->uid, "AIM-120");
    last_shoot_time = time_counter;
}

void StandoffOpponent3D::support_crank(
    std::shared_ptr<Aircraft> agent,
    std::shared_ptr<Aircraft> target,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) noexcept {
    const double desired_heading = get_crank_heading(agent, target);
    delta_heading = get_heading_action(agent, desired_heading);

    delta_altitude = 0.0;

    const double target_speed = c3u::get_mps(kSupportSpeedMach, agent->get_altitude());
    delta_speed = (target_speed - agent->get_speed()) * 0.5;

    shoot = false;
    fire = json::JSON();
}

void StandoffOpponent3D::get_default_action(
    std::shared_ptr<Aircraft> agent,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) const noexcept {
    delta_heading = 0.0;
    delta_altitude = 0.0;
    delta_speed = 0.0;
    shoot = false;
    fire = json::JSON();
}

double StandoffOpponent3D::get_crank_heading(
    std::shared_ptr<Aircraft> agent,
    std::shared_ptr<Aircraft> target
) noexcept {
    if ((time_counter - crank_switch_time) * cfg::dt > kCrankSwitchSec) {
        crank_direction *= -1;
        crank_switch_time = time_counter;
    }

    const double target_heading = calculate_heading_to_target(agent, target->position);
    return target_heading + c3u::deg2rad(kCrankAngleDeg) * crank_direction;
}

}
