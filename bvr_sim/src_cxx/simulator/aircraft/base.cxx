#include "base.hxx"
#include "../sense/base.hxx"
#include "../missile/base.hxx"
#include "../so_pool.hxx"
#include "../weapon_factory.hxx"
#include "simulator/pylon_manager.hxx"
#include "so_pool.hxx"
#include "rubbish_can/check.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/colorful.hxx"
#include "c3utils/c3utils.hxx"

#include <cmath>
#include <iostream>
#include <sstream>
#include <iomanip>

namespace bvr_sim {

using namespace c3utils;

Aircraft::Aircraft(
    const std::string& uid_,
    const std::string& model,
    TeamColor color_,
    const std::array<double, 3>& position_,
    const std::array<double, 3>& velocity_,
    double dt_
) noexcept
    : SimulatedObject(uid_, color_, position_, velocity_, dt_, SOT::Aircraft),
      aircraft_model(model),
      bloods(100.0),
      sensed(false),
      radar(nullptr),
      rws(nullptr),
      mws(nullptr),
      sa_datalink(nullptr) {
}

bool Aircraft::can_shoot() const noexcept {
    return true;
}

bool Aircraft::can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept {
    check(enemy->color != this->color, "Aircraft::can_shoot_enm: enemy color is same as self");
    bool is_enemy = false;
    for (const auto& enm : enemies) {
        if (enm->uid == enemy->uid) {
            is_enemy = true;
            break;
        }
    }

    if (!is_enemy) {
        std::cout << "Warning: AA::can_shoot_enm: " << uid << " is not enemy of " << enemy->uid << std::endl;
    }

    if (!can_shoot()) {
        return false;
    }

    if (radar != nullptr) {
        const auto& radar_data = radar->get_data();
        if (radar_data.find(enemy->uid) != radar_data.end()) {
            return true;
        }
        else if (std::find_if(enemies_lock.begin(), enemies_lock.end(), [&enemy](const auto& enm) { return enm->uid == enemy->uid; }) != enemies_lock.end()) {

            colorful::printHUANG("Warning: Aircraft::can_shoot_enm: %s in enemies_lock but not in radar data\n",enemy->uid.c_str());
            return true;
        }
        SL::get().printf("Warning: Aircraft::can_shoot_enm: %s cannot shoot %s, not locked\n", uid.c_str(), enemy->uid.c_str());
        colorful::print("Warning: Aircraft::can_shoot_enm: %s cannot shoot %s, not locked\n", uid.c_str(), enemy->uid.c_str());
        for (const auto& enm : enemies_lock) {
            std::cout << "Warning: Aircraft::can_shoot_enm: " << uid << " in enemies_lock: " << enm->uid << std::endl;
        }
        for (const auto& enm : radar_data) {
            std::cout << "Warning: Aircraft::can_shoot_enm: " << uid << " in radar_data: " << enm.first << std::endl;
        }
    }

    // std::cout << "Warning: Aircraft::can_shoot_enm: " << uid << " cannot shoot " << enemy->uid << std::endl;
    SL::get().printf("Warning: Aircraft::can_shoot_enm: %s cannot shoot %s\n, no radar", uid.c_str(), enemy->uid.c_str());
    return false;
}

bool Aircraft::shoot(
    const std::string& missile_spec,
    const std::string& target_uid
) noexcept {
    if (!can_shoot()) {
        // std::cout << "Warning: Aircraft::shoot: " << uid << " cannot shoot" << std::endl;
        SL::get().printf("Warning: Aircraft::shoot: %s cannot shoot\n", uid.c_str());
        return false;
    }

    auto target = SOPool::instance().get(target_uid);
    if (!target) {
        std::cout << "Warning: Aircraft::shoot: target " << target_uid << " not found" << std::endl;
        return false;
    }
    if (!can_shoot_enm(target)) {
        // std::cout << "Warning: Aircraft::shoot: " << uid << " cannot shoot !can_shoot_enm(target)" << target->uid << std::endl;
        SL::get().printf("Warning: Aircraft::shoot: %s cannot shoot enm !can_shoot_enm %s\n", uid.c_str(), target->uid.c_str());
        return false;
    }

    auto self = std::dynamic_pointer_cast<SimulatedObject>(shared_from_this());
    if (!self) {
        std::cout << "Error: Aircraft::shoot: failed to cast self to SimulatedObject" << std::endl;
        return false;
    }

    int num_left = pylon_manager.num_left_weapons(missile_spec);
    if (num_left <= 0) {
        // std::cout << "Warning: Aircraft::shoot: " << uid << " no more " << missile_spec << std::endl;
        SL::get().printf("Warning: Aircraft::shoot: %s no more %s\n", uid.c_str(), missile_spec.c_str());
        return false;
    }

    auto missile = WeaponFactory::create_missile(missile_spec, self, target);
    if (!missile) {
        std::cout << "Warning: Aircraft::shoot: failed to create missile " << missile_spec << std::endl;
        return false;
    }

    pylon_manager.release_weapon(missile_spec);
    launched_missiles.push_back(missile);
    SOPool::instance().add(missile);

    if (target->Type == SOT::Aircraft) {
        auto aircraft_target = std::dynamic_pointer_cast<Aircraft>(target);
        if (aircraft_target) {
            bool already_under = false;
            for (const auto& m : aircraft_target->under_missiles) {
                if (m == missile) {
                    already_under = true;
                    break;
                }
            }

            if (!already_under) {
                aircraft_target->under_missiles.push_back(missile);
            } else {
                std::cout << "Error: missile " << missile->uid << " already under " << aircraft_target->uid << std::endl;
                SL::get().print("[Aircraft] Error: missile " + missile->uid + " already under " + aircraft_target->uid);
            }
        } else {
            colorful::printHONG("Warning: Aircraft::shoot: dynamic cast failed for " + target->uid);
            std::abort();
        }
    }

    return true;
}

void Aircraft::add_sensor(const std::string& name, const std::shared_ptr<SensorBase>& sensor) {
    if (!sensor) {
        SL::get().print("[Aircraft] Error: Sensor " + name + " is nullptr");
        return;
    }
    if (sensors.find(name) != sensors.end()) {
        SL::get().print("[Aircraft] Error: Sensor name " + name + " already exists");
        return;
    }

    sensors[name] = sensor;

    if (name == "radar") {
        radar = sensor;
    } else if (name == "rws") {
        rws = sensor;
    } else if (name == "mws") {
        mws = sensor;
    } else if (name == "sa_datalink") {
        sa_datalink = sensor;
    }
}

void Aircraft::update_sensors() noexcept {
    for (auto& [name, sensor] : sensors) {
        if (sensor != nullptr) {
            sensor->update();
        } else {
            std::cout << "Warning: " << name << " sensor is None" << std::endl;
        }
    }
}

double Aircraft::get_roll() const noexcept {
    return 0.0;
}

double Aircraft::get_pitch() const noexcept {
    double v_horizontal = std::sqrt(velocity[0] * velocity[0] + velocity[1] * velocity[1]);
    return std::atan2(-velocity[2], v_horizontal);
}

void Aircraft::step() {
    maintain_missile_lists();
};

void Aircraft::maintain_missile_lists() noexcept {
    // maintain under_missiles
    for (auto it = under_missiles.begin(); it != under_missiles.end();) {
        if ((*it)->is_alive) {
            ++it;
        } else {
            it = under_missiles.erase(it);
        }
    }
    // maintain launched_missiles
    for (auto it = launched_missiles.begin(); it != launched_missiles.end();) {
        if ((*it)->is_alive) {
            ++it;
        } else {
            it = launched_missiles.erase(it);
        }
    }
    // maintain enemies_lock
    for (auto it = enemies_lock.begin(); it != enemies_lock.end();) {
        if ((*it)->is_alive) {
            ++it;
        } else {
            // colorful::printHUANG("Warning: Aircraft::maintain_missile_lists: %s is dead, but still in enemies_lock\n", (*it)->uid.c_str());
            it = enemies_lock.erase(it);
        }
    }
}

void Aircraft::hit(double damage) noexcept {
    if (damage < 0.0) {
        bloods = 0.0;
    } else {
        bloods -= damage;
    }

    if (bloods <= 0.0) {
        is_alive = false;
    }
}

std::string Aircraft::log() noexcept {
    std::string color_str;
    if (sensed) {
        color_str = (color == TeamColor::Red) ? "Violet" : "Green";
    } else {
        color_str = (color == TeamColor::Red) ? "Red" : "Blue";
    }

    auto [lon, lat, alt] = NWU2LLA(position[0], position[1], position[2]);
    // auto [roll_deg_vel, pitch_deg_vel, yaw_deg_vel] = velocity_to_euler(velocity, true);

    double roll_deg = rad2deg(get_roll());
    double pitch_deg = rad2deg(get_pitch());
    double yaw_deg = rad2deg(get_heading());

    std::stringstream ss;
    ss << std::fixed << std::setprecision(6);

    if (is_alive) {
        ss << uid << ",T=" << lon << "|" << lat << "|" << alt << "|"
           << roll_deg << "|" << -pitch_deg << "|" << -yaw_deg << ","
           << "Name=" << aircraft_model << ",Color=" << color_str << ",Type=Air + FixedWing";

        if (radar != nullptr) {
            ss << radar->log_suffix();
        }

        ss << '\n';
        return ss.str();
    } else if (!render_explosion) {
        ss << uid << ",T=" << lon << "|" << lat << "|" << alt << "|"
           << roll_deg << "|" << -pitch_deg << "|" << -yaw_deg << ","
           << "Name=" << aircraft_model << ",Color=" << color_str << ",Type=Air + FixedWing";

        if (radar != nullptr) {
            ss << radar->log_suffix();
        }

        ss << '\n';

        render_explosion = true;
        // ss << "0,Event=Destroyed|" << uid << "|" << '\n';
        ss << "-" << uid << '\n';
        ss << "0,Event=Message|" << uid << get_new_uuid() << "|is_alive=" << is_alive << '\n';

        // std::string explosion_id = uid + "0" + get_new_uuid();
        // ss << explosion_id << ",T=" << lon << "|" << lat << "|" << alt << ",Type=Explosion + Medium";

        return ss.str();
    } else {
        return "";
    }
}

void Aircraft::write_register() noexcept {
    SimulatedObject::write_register();
    maintain_missile_lists();

    json::JSON under_missiles_size = json::Integral(static_cast<int>(under_missiles.size()));
    json::JSON launched_missiles_size = json::Integral(static_cast<int>(launched_missiles.size()));
    register_.set("under_missiles.size()", under_missiles_size);
    register_.set("launched_missiles.size()", launched_missiles_size);

    auto enemies_lock_list = json::Array();
    for (auto& enemy : enemies_lock) {
        check(enemy != nullptr, "Enemy " + enemy->uid + " is nullptr, but still in enemies_lock.");
        if (enemy->is_alive) {
            enemies_lock_list.append(json::String(enemy->uid));
        } else {
            check(false, "Enemy " + enemy->uid + " is dead, but still in enemies_lock.");
        }
    }
    register_.set("enemies_lock.size()", json::Integral(static_cast<int>(enemies_lock.size())));
    register_.set("enemies_lock", enemies_lock_list);
}

bool Aircraft::is_compass_action(const std::map<std::string, double>& action) const noexcept {
    return action.find("delta_heading") != action.end() &&
           action.find("delta_altitude") != action.end() &&
           action.find("delta_speed") != action.end();
}

bool Aircraft::is_physics_action(const std::map<std::string, double>& action) const noexcept {
    return action.find("elevator") != action.end() &&
           action.find("aileron") != action.end() &&
           action.find("rudder") != action.end() &&
           action.find("throttle") != action.end();
}

double Aircraft::normalize_angle(double angle) const noexcept {
    return norm_pi(angle);
}

}
