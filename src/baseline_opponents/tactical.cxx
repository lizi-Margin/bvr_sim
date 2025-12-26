#include "tactical.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/missile/base.hxx"
#include "simulator/pylon_manager.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "global_config.hxx"
#include "c3utils/funcs.hxx"
#include <algorithm>
#include <cmath>

namespace bvr_sim {

TacticalOpponent3D::TacticalOpponent3D() noexcept
    : BaseOpponent3D("Tactical3D"),
      last_shoot_time(-static_cast<int>(30.0 / cfg::dt)), // Convert 30 seconds to steps (assuming default dt=0.1)
      crank_direction(1),
      crank_switch_time(0) {
}

void TacticalOpponent3D::take_action(
    std::shared_ptr<Aircraft> agent,
    const std::vector<std::shared_ptr<SimulatedObject>>& enemies,
    const std::vector<std::shared_ptr<SimulatedObject>>& partners,
    const std::vector<std::shared_ptr<Missile>>& missiles_targeting_me
) {
    time_counter++;

    if (!agent->is_alive) {
        return;
    }

    // Filter out dead enemies
    std::vector<std::shared_ptr<Aircraft>> alive_enemies;
    if (!agent->enemies_lock.empty()) {
        alive_enemies = agent->enemies_lock;
    } else {
        for (const auto& enemy : enemies) {
            if (enemy->is_alive && enemy->Type == SOT::Aircraft) {
                auto e = std::dynamic_pointer_cast<Aircraft>(enemy);
                check(e, "TacticalOpponent3D::take_action: dynamic cast failed");
                alive_enemies.push_back(e);
            }
        }
        std::sort(alive_enemies.begin(), alive_enemies.end(),
            [&agent](const std::shared_ptr<Aircraft>& a, const std::shared_ptr<Aircraft>& b) {
                check(a, "TacticalOpponent3D::take_action: a is null");
                check(b, "TacticalOpponent3D::take_action: b is null");
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

    // auto nearest_enemy = *std::min_element(alive_enemies.begin(), alive_enemies.end(),
    //     [&agent](const std::shared_ptr<Aircraft>& a, const std::shared_ptr<Aircraft>& b) {
    //         check(a, "TacticalOpponent3D::take_action: a is null");
    //         check(b, "TacticalOpponent3D::take_action: b is null");
    //         double dist_a = c3utils::linalg_norm_vec(c3utils::Vector3(
    //             a->position[0] - agent->position[0],
    //             a->position[1] - agent->position[1],
    //             a->position[2] - agent->position[2]
    //         ));
    //         dist_a += a->under_missiles.size() * 1000.0;
    //         double dist_b = c3utils::linalg_norm_vec(c3utils::Vector3(
    //             b->position[0] - agent->position[0],
    //             b->position[1] - agent->position[1],
    //             b->position[2] - agent->position[2]
    //         ));
    //         dist_b += b->under_missiles.size() * 1000.0;
    //         return dist_a < dist_b;
    //     });

    auto nearest_enemy = alive_enemies.front();

    // Get missiles in flight from the agent
    std::vector<std::shared_ptr<Missile>> missiles_in_flight;
    for (const auto& missile : agent->launched_missiles) {
        if (missile->is_alive && missile->target->uid == nearest_enemy->uid) {
            missiles_in_flight.push_back(missile);
        }
    }

    // Get active missiles targeting the agent
    std::vector<std::shared_ptr<Missile>> active_missiles = get_active_missile(missiles_targeting_me);
    // std::cout << missiles_in_flight.size() << " missiles in flight, " << missiles_targeting_me.size() << " missiles targeting me, " << active_missiles.size() << " active missiles targeting me\n";

    // Priority 1: Evade incoming missiles (highest priority)
    if (!active_missiles.empty()) {
        double delta_heading, delta_altitude, delta_speed;
        bool shoot;
        json::JSON fire_action_json = json::JSON::Make(json::JSON::Class::Object);
        evade_missiles(agent, active_missiles, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
        auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
        apply_action(agent, final_action, fire_action_json);
        return;
    }

    // Priority 2: Guide missiles in flight
    if (!missiles_in_flight.empty() && !alive_enemies.empty()) {
        double delta_heading, delta_altitude, delta_speed;
        bool shoot;
        json::JSON fire_action_json = json::JSON::Make(json::JSON::Class::Object);
        guide_missiles(agent, missiles_in_flight, alive_enemies, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
        auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
        apply_action(agent, final_action, fire_action_json);
        return;
    }

    // Priority 3: Attack when no missiles in flight
    if (!alive_enemies.empty() && agent->pylon_manager.num_left_weapons("AIM-120") > 0) {
        double delta_heading, delta_altitude, delta_speed;
        bool shoot;
        json::JSON fire_action_json = json::JSON::Make(json::JSON::Class::Object);
        tactical_attack(agent, nearest_enemy, alive_enemies, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
        auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
        apply_action(agent, final_action, fire_action_json);
        return;
    }

    // Priority 4: No enemies - maintain course
    double delta_heading, delta_altitude, delta_speed;
    bool shoot;
    json::JSON fire_action_json = json::JSON::Make(json::JSON::Class::Object);
    get_default_action(agent, delta_heading, delta_altitude, delta_speed, shoot, fire_action_json);
    auto final_action = build_action_from_rates(delta_heading, delta_altitude, delta_speed, shoot);
    apply_action(agent, final_action, fire_action_json);
}

std::vector<std::shared_ptr<Missile>> TacticalOpponent3D::get_active_missile(
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

void TacticalOpponent3D::evade_missiles(
    std::shared_ptr<Aircraft> agent,
    std::vector<std::shared_ptr<Missile>> missiles,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) noexcept {
    // Find closest missile
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
    double distance = c3utils::linalg_norm_vec(rel_pos);

    // Calculate missile bearing
    double missile_heading = std::atan2(rel_pos[1], rel_pos[0]);

    // Turn away (opposite direction)
    double desired_heading = missile_heading + c3u::pi;
    delta_heading = get_heading_action(agent, desired_heading);

    // Dive if high, maintain if low (to reduce radar lock and increase distance)
    double target_speed;
    if (distance < 15000.0) {  // Close range: aggressive maneuver
        if (agent->get_altitude() > 4000.0) {
            delta_altitude = -125.0;  // Dive
        } else {
            delta_altitude = 20.0;    // Climb
        }
        target_speed = c3u::get_mps(1.2, agent->get_altitude());
    } else {  // Far range: crank maneuver
        if (agent->get_altitude() > 4000.0) {
            delta_altitude = -30.0;  // Gentle dive
        } else {
            delta_altitude = 0.0;
        }
        target_speed = c3u::get_mps(1.1, agent->get_altitude());
    }

    double speed_diff = target_speed - agent->get_speed();
    delta_speed = speed_diff;

    // Temporary override as was in Python
    delta_altitude = 0.0;

    shoot = false;
    fire = json::JSON();
}

void TacticalOpponent3D::guide_missiles(
    std::shared_ptr<Aircraft> agent,
    std::vector<std::shared_ptr<Missile>> missiles_in_flight,
    std::vector<std::shared_ptr<Aircraft>> alive_enemies,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) noexcept {
    // Get target of first missile
    std::shared_ptr<Aircraft> target = std::dynamic_pointer_cast<Aircraft>(missiles_in_flight[0]->target);
    if (!target || std::find_if(alive_enemies.begin(), alive_enemies.end(),
        [&target](const std::shared_ptr<Aircraft>& e) { return e->uid == target->uid; }) == alive_enemies.end()) {
        get_default_action(agent, delta_heading, delta_altitude, delta_speed, shoot, fire);
        return;
    }

    c3utils::Vector3 rel_pos(
        target->position[0] - agent->position[0],
        target->position[1] - agent->position[1],
        target->position[2] - agent->position[2]
    );
    double distance = c3utils::linalg_norm_vec(rel_pos);
    double target_heading = std::atan2(rel_pos[1], rel_pos[0]);

    // Crank maneuver: offset heading by ±30 degrees
    double crank_offset = c3u::deg2rad(30.0) * crank_direction;
    double desired_heading = target_heading + crank_offset;

    // Switch crank direction periodically
    // Convert 20 seconds to steps based on agent's dt
    if (time_counter - crank_switch_time > static_cast<int>(20.0 / agent->dt)) {
        crank_direction *= -1;
        crank_switch_time = time_counter;
    }

    delta_heading = get_heading_action(agent, desired_heading);

    // Target altitude calculation
    double target_altitude = std::max(agent->get_altitude() - 30.0, c3u::feet_to_meters(7000.0));
    double altitude_diff = target_altitude - agent->get_altitude();
    delta_altitude = altitude_diff;

    // Moderate speed for guidance
    double target_speed = c3u::get_mps(0.9, agent->get_altitude());
    double speed_diff = target_speed - agent->get_speed();
    delta_speed = speed_diff * 0.5;

    // Can shoot additional missiles if conditions are good
    shoot = false;
    fire = json::JSON();
    int time_since_last_shoot = time_counter - last_shoot_time;

    // Check if target is in lock list
    bool target_locked = std::find_if(agent->enemies_lock.begin(), agent->enemies_lock.end(),
        [&target](const std::shared_ptr<Aircraft>& locked) { return locked->uid == target->uid; }) != agent->enemies_lock.end();

    if (agent->pylon_manager.num_left_weapons("AIM-120") > 0 &&
        time_since_last_shoot > static_cast<int>(50.0 / agent->dt) &&  // Convert 50 seconds to steps
        target_locked) {
        // Check if first missile is far from target
        c3utils::Vector3 missile_to_target(
            missiles_in_flight[0]->position[0] - target->position[0],
            missiles_in_flight[0]->position[1] - target->position[1],
            missiles_in_flight[0]->position[2] - target->position[2]
        );
        double missile_to_target_dist = c3utils::linalg_norm_vec(missile_to_target);
        if (missile_to_target_dist > 20000.0 && distance < 45000.0) {
            shoot = true;
            fire = get_fire_action(agent, target->uid, "AIM-120");
            last_shoot_time = time_counter;
        }
    }

    // Apply JSOW shoot command as other command
    double shoot_jsow = 1.0;
    if (agent->pylon_manager.num_left_weapons("AIM-120") < agent->pylon_manager.num_frozen_weapons("AIM-120") / 2) {
        shoot_jsow = 0.0;
    }

    // For this function we just return the basic action, and the JSOW command can be handled separately
    // if needed, or by using the other_commands parameter in build_action_from_rates
    std::map<std::string, double> other_commands = {{"shoot_jsow", shoot_jsow}};
}

void TacticalOpponent3D::tactical_attack(
    std::shared_ptr<Aircraft> agent,
    std::shared_ptr<Aircraft> target,
    std::vector<std::shared_ptr<Aircraft>> alive_enemies,
    double& delta_heading,
    double& delta_altitude,
    double& delta_speed,
    bool& shoot,
    json::JSON& fire
) noexcept {
     c3utils::Vector3 rel_pos(
        target->position[0] - agent->position[0],
        target->position[1] - agent->position[1],
        target->position[2] - agent->position[2]
    );
    double distance = c3utils::linalg_norm_vec(rel_pos);

    // Head towards enemy
    double desired_heading = calculate_heading_to_target(agent, target->position);
    delta_heading = get_heading_action(agent, desired_heading);

    // Altitude strategy
    double target_altitude = agent->get_altitude() + 150.0;
    double altitude_diff = target_altitude - agent->get_altitude();
    delta_altitude = altitude_diff;

    // Speed: accelerate if far, moderate if close
    double target_speed;
    target_speed = c3u::get_mps(1.5, agent->get_altitude());


    double speed_diff = target_speed - agent->get_speed();
    delta_speed = speed_diff * 0.6;

    // Shoot tactically
    shoot = false;
    fire = json::JSON();
    int time_since_last_shoot = time_counter - last_shoot_time;

    // Check if nearest enemy is in lock list
    bool enemy_locked = std::find_if(agent->enemies_lock.begin(), agent->enemies_lock.end(),
        [&target](const std::shared_ptr<Aircraft>& locked) { return locked->uid == target->uid; }) != agent->enemies_lock.end();

    if (enemy_locked &&
        agent->pylon_manager.num_left_weapons("AIM-120") > 0 &&
        time_since_last_shoot > static_cast<int>(10.0 / agent->dt)) {  // Convert 10 seconds to steps
        if (distance < c3u::nm_to_meters(8.0)) {
            shoot = true;
            fire = get_fire_action(agent, target->uid, "AIM-120");
            last_shoot_time = time_counter;
        } else if (distance < c3u::nm_to_meters(38.0)) {
            shoot = true;
            fire = get_fire_action(agent, target->uid, "AIM-120");
            last_shoot_time = time_counter;
        }
    }
}

void TacticalOpponent3D::get_default_action(
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

}