#include "mad.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/pylon_manager.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include <algorithm>
#include <cmath>

namespace bvr_sim {

MadOpponent3D::MadOpponent3D() noexcept
    : BaseOpponent3D("Mad3D"),
      last_shoot_time(0),
      crank_direction(1),
      crank_switch_time(0) {
}

void MadOpponent3D::take_action(
    std::shared_ptr<Aircraft> agent,
    const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
    const std::vector<std::shared_ptr<SimulatedObject>>& partners,
    const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
) {
    time_counter++;

    if (!agent->is_alive) {
        auto final_action = build_action_from_rates(0.0, 0.0, 0.0, false);
        apply_action(agent, final_action);
        return;
    }

    // Filter out dead enemies
    std::vector<std::shared_ptr<Aircraft>> alive_enemies;
    for (const auto& enemy : enemies) {
        if (enemy->is_alive) {
            if (enemy->Type == SOT::Aircraft) {
                auto ac = std::dynamic_pointer_cast<Aircraft>(enemy);
                if (!ac) {
                    colorful::printHONG("dynamic cast failed in mad opponent\n");
                    std::abort();
                }
                alive_enemies.push_back(ac);
            }
        }
    }

    if (alive_enemies.empty()) {
        auto final_action = build_action_from_rates(0.0, 0.0, 0.0, false);
        apply_action(agent, final_action);
        return;
    }

    // Find nearest enemy
    auto nearest_enemy = *std::min_element(alive_enemies.begin(), alive_enemies.end(),
        [&agent](const std::shared_ptr<Aircraft>& a, const std::shared_ptr<Aircraft>& b) {
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

    // Head towards enemy (horizontal)
    double target_heading = calculate_heading_to_target(agent, nearest_enemy->position);

    // Crank maneuver: offset heading by ±30 degrees
    double crank_offset = c3u::deg2rad(30.0) * crank_direction;
    double desired_heading = target_heading + crank_offset;

    // Switch crank direction periodically (20s)
    if (time_counter - crank_switch_time > static_cast<int>(20.0 / agent->dt)) {
        crank_direction *= -1;
        crank_switch_time = time_counter;
    }

    double delta_heading = get_heading_action(agent, desired_heading);

    // Match enemy altitude with offset
    double target_altitude = std::max({
        nearest_enemy->get_altitude() + 1000.0,
        agent->get_altitude(),
        c3u::feet_to_meters(32000.0)
    });
    double altitude_diff = target_altitude - agent->get_altitude();
    double delta_altitude = altitude_diff * 0.5;  // P-gain = 0.5

    // 1.2 ma speed
    double target_speed = 411.0;
    double speed_diff = target_speed - agent->get_speed();
    double delta_speed = speed_diff * 0.5;

    // Shoot if locked and in range
    bool shoot = false;
    int time_since_last_shoot = time_counter - last_shoot_time;

    // Check if nearest enemy is in lock list
    bool enemy_locked = false;
    for (const auto& locked_aircraft : agent->enemies_lock) {
        if (locked_aircraft->uid == nearest_enemy->uid) {
            enemy_locked = true;
            break;
        }
    }

    SL::get().print("[MadOpponent3D] uid:" + agent->uid + " Nearest enemy: " + nearest_enemy->uid + " locked: " + std::to_string(enemy_locked));

    // Check if agent has weapons using pylon manager
    bool has_weapons = agent->pylon_manager.num_left_weapons("AIM-120") > 0;

    if (enemy_locked && has_weapons && time_since_last_shoot > 30) {
        double distance = c3utils::linalg_norm_vec(c3utils::Vector3(
            nearest_enemy->position[0] - agent->position[0],
            nearest_enemy->position[1] - agent->position[1],
            nearest_enemy->position[2] - agent->position[2]
        ));
        if (distance < c3u::nm_to_meters(40.0)) {  // 40 nm
            shoot = true;
            last_shoot_time = time_counter;
        }
        SL::get().print("[MadOpponent3D] uid:" + agent->uid + " Lock on " + nearest_enemy->uid + " distance: " + std::to_string(distance));
    }

    auto final_action = build_action_from_rates(
        delta_heading,
        delta_altitude,
        delta_speed,
        shoot
    );
    json::JSON fire_action_json = json::JSON();
    if (shoot) {
        SL::get().print("[MadOpponent3D] uid:" + agent->uid + " Fire at " + nearest_enemy->uid);
        fire_action_json = get_fire_action(agent, nearest_enemy->uid, "AIM-120");
    }
    apply_action(agent, final_action, fire_action_json);
}

}