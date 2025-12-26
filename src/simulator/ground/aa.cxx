#include "aa.hxx"
#include "../missile/base.hxx"
#include "../aircraft/base.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <sstream>
#include <iomanip>
#include <iostream>
#include <algorithm>

namespace bvr_sim {

using c3utils::rad2deg;

AA::AA(
    const std::string& uid,
    const std::string& model,
    TeamColor color,
    const std::array<double, 3>& position,
    double dt,
    int num_missiles
) noexcept : GroundUnit(
        uid,
        model,
        color,
        position,
        dt,
        SOT::AA
),
    num_missiles(num_missiles),
    num_left_missiles(num_missiles),
    _t(0.0) {
    _collision_radius = 10.0;  // m
}

bool AA::can_shoot() const noexcept {
    return num_left_missiles > 0;
}

bool AA::can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept {
    auto it = std::find(enemies.begin(), enemies.end(), enemy);
    if (it == enemies.end()) {
        std::cout << "Warning: AA::can_shoot_enm: " << uid << " is not enemy of " << enemy->uid << std::endl;
    }
    return can_shoot();
}

void AA::shoot(
    const std::shared_ptr<Missile>& missile,
    const std::shared_ptr<Aircraft>& target
) noexcept {
    if (!can_shoot()) {
        return;
    }

    launched_missiles.push_back(missile);
    num_left_missiles--;

    if (target != nullptr) {
        auto& under_missiles = const_cast<std::vector<std::shared_ptr<Missile>>&>(target->under_missiles);
        auto it = std::find(under_missiles.begin(), under_missiles.end(), missile);
        if (it == under_missiles.end()) {
            under_missiles.push_back(missile);
        }
    }
}

void AA::step() {
    _t += dt;
}

std::array<double, 3> AA::get_launch_velocity(const std::shared_ptr<Aircraft>& target) const noexcept {
    double launch_speed = 5.0;  // m/s

    std::array<double, 3> rel_vec = {
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    };

    double distance = std::sqrt(
        rel_vec[0] * rel_vec[0] +
        rel_vec[1] * rel_vec[1] +
        rel_vec[2] * rel_vec[2]
    );

    if (distance < 1e-6) {
        return {0.0, 0.0, launch_speed};
    }

    std::array<double, 3> direction = {
        rel_vec[0] / distance,
        rel_vec[1] / distance,
        rel_vec[2] / distance
    };

    return {
        direction[0] * launch_speed,
        direction[1] * launch_speed,
        direction[2] * launch_speed
    };
}

std::string AA::log() noexcept {
    auto [lon, lat, alt] = NWU2LLA(position[0], position[1], position[2]);

    std::ostringstream msg;
    msg << std::fixed << std::setprecision(6);

    // Note: search_range is not defined in this class, using a placeholder
    double search_range = 50000.0; // Default placeholder value

    if (is_alive) {
        msg << uid << ",T=" << lon << "|" << lat << "|" << alt << "|0.0|0.0|" << -rad2deg(_yaw_for_log) << ",";
        msg << "Name=" << model << ",Color=" << (color == TeamColor::Red ? "Red" : "Blue") << _log_tacview_Type << ", EngagementRange=" << search_range;
        msg << "\n";
        return msg.str();
    } else if (!render_explosion) {
        msg << uid << ",T=" << lon << "|" << lat << "|" << alt << "|0.0|0.0|" << -rad2deg(_yaw_for_log) << ",";
        msg << "Name=" << model << ",Color=" << (color == TeamColor::Red ? "Red" : "Blue") << _log_tacview_Type << ", EngagementRange=" << search_range;
        msg << "\n";

        // Cast away const for render_explosion modification
        const_cast<AA*>(this)->render_explosion = true;

        msg << "-" << uid << "\n";
        std::string explosion_id = uid + get_new_uuid();
        msg << explosion_id << ",T=" << lon << "|" << lat << "|" << alt << ",Type=Explosion + Large\n";
        return msg.str();
    } else {
        return "";
    }
}

}