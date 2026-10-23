#include "slamraam.hxx"
#include <cmath>
#include <iostream>
#include "c3utils/c3utils.hxx"
#include "simulator/aircraft/base.hxx"
#include "simulator/weapon_factory.hxx"
#include "so_pool.hxx"

namespace bvr_sim {

using c3utils::nm_to_meters;
using c3utils::feet_to_meters;
using c3utils::get_mps;

SLAMRAAM::SLAMRAAM(
    const std::string& uid,
    TeamColor color,
    const std::array<double, 3>& position,
    double dt,
    int num_missiles
) noexcept : AA(
        uid,
        "AN/TWQ-1 Avenger",  // use TWQ-1 model instead, tacview does not have SLAMRAAM model
        color,
        position,
        dt,
        num_missiles
),
    search_range(nm_to_meters(15.0)),
    height_gate(feet_to_meters(500.0)),
    velocity_gate(get_mps(0.2, 0.0)),
    last_shoot_time(-100.0),
    min_shoot_interval(3.0) {
}

bool SLAMRAAM::can_shoot() const noexcept {
    return num_left_missiles > 0 && (_t - last_shoot_time) >= min_shoot_interval;
}

bool SLAMRAAM::can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept {
    auto it = std::find(enemies.begin(), enemies.end(), enemy);
    if (it == enemies.end()) {
        std::cout << "Warning: AA::can_shoot_enm: " << uid << " is not enemy of " << enemy->uid << std::endl;
    }

    if (!can_shoot()) {
        return false;
    }

    if (enemy->position[2] < height_gate) {
        // std::cout << "Warning: AA::can_shoot_enm: " << uid << " is too low " << enemy->position[2] << " < " << height_gate << " to shoot " << enemy->uid << std::endl;
        return false;
    }

    if (enemy->get_speed() < velocity_gate) {
        // std::cout << "Warning: AA::can_shoot_enm: " << uid << " is too slow " << enemy->get_mach() << " < " << velocity_gate << " to shoot " << enemy->get_uid() << std::endl;
        return false;
    }

    double distance = std::sqrt(
        std::pow(enemy->position[0] - position[0], 2) +
        std::pow(enemy->position[1] - position[1], 2) +
        std::pow(enemy->position[2] - position[2], 2)
    );

    if (distance > search_range) {
        // std::cout << "Warning: AA::can_shoot_enm: " << uid << " is too far " << distance << " > " << search_range << " to shoot " << enemy->get_uid() << std::endl;
        return false;
    }

    return true;
}

void SLAMRAAM::shoot(
    const std::shared_ptr<Missile>& missile,
    const std::shared_ptr<Aircraft>& target
) noexcept {
    AA::shoot(missile, target);
    last_shoot_time = _t;
}

void SLAMRAAM::step() {
    _t += dt;
    if(!environment || !is_alive)return;
    search_radar.update(*this,*environment,search_range);
    tracked_target.clear();
    for(const auto& [id,observation]:search_radar.contacts) {
        auto target=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(id));
        if(!target || !target->is_alive || !can_shoot_enm(target))continue;
        tracked_target=id;
        // One live missile per salvo. Original magazine, range, altitude/speed gates and interval remain.
        bool airborne=false;
        for(const auto& missile:launched_missiles)if(missile && missile->is_alive)airborne=true;
        if(airborne)break;
        auto missile=WeaponFactory::create_missile("AIM-120C7",shared_from_this(),target);
        if(missile){shoot(missile,target);SOPool::instance().add(missile);}
        break;
    }
}

}
