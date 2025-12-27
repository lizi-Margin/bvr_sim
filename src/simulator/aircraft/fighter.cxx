#include "fighter.hxx"
#include "../missile/base.hxx"
// #include "../so_pool.hxx"
#include "rubbish_can/SL.hxx"
// #include "simulator/pylon_manager.hxx"
#include "rl/action_space.hxx"
#include <iostream>
#include <cmath>

namespace bvr_sim {

const static bool BYPASS_THROTTLE_CONTROL = true;

using namespace c3utils;

const static std::string AAM_SPEC = "AIM-120";
const static std::string AGM_SPEC = "JSOW";

Fighter::Fighter(
    const std::string& uid_,
    TeamColor color_,
    const std::array<double, 3>& position_,
    const std::array<double, 3>& velocity_,
    double dt_,
    const std::string& fdm_type
) noexcept
    : Aircraft(uid_, "F16", color_, position_, velocity_, dt_),
      _t(0.0),
      min_shoot_interval(5.0),
      last_shoot_time(-100.0) {

    initialize_fdm(fdm_type);

    std::map<std::string, std::any> initial_state;
    initial_state["position"] = position_;
    initial_state["velocity"] = velocity_;
    initial_state["roll"] = 0.0;
    initial_state["pitch"] = 0.0;
    initial_state["yaw"] = std::atan2(velocity_[1], velocity_[0]);

    fdm->reset(initial_state);
    write_register();
}

void Fighter::initialize_fdm(const std::string& fdm_type) noexcept {
    if (fdm_type == "simple") {
        fdm = std::make_unique<SimpleFDM>(dt);
    } else if (fdm_type == "jsbsim") {
        std::map<std::string, std::string> kwargs;
        kwargs["aircraft_model"] = aircraft_model;
        fdm = std::make_unique<JSBSimFDM>(dt, kwargs);
    } else {
        std::cerr << "Warning: Unknown FDM type '" << fdm_type << "', defaulting to SimpleFDM" << std::endl;
        fdm = std::make_unique<SimpleFDM>(dt);
    }
}

bool Fighter::can_shoot() const noexcept {
    bool res = _t - last_shoot_time >= min_shoot_interval;
    return res;
}

bool Fighter::can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept {
    return Aircraft::can_shoot_enm(enemy);
}

void Fighter::step() {
    Aircraft::step();
    if (!is_alive) {
        return;
    }

    _t += dt;

    std::map<std::string, double> action;
    if (action_space_check::has_possible_action(register_)){
        ActionSpace action_space(register_);
        action["delta_heading"] = action_space.delta_heading();
        action["delta_altitude"] = action_space.delta_altitude();
        action["delta_speed"] = action_space.delta_speed();
        if (action_space.fire()){
            if (shoot(action_space.fire_weapon_spec(), action_space.fire_target_uid())){
                last_shoot_time = _t;
            }
        }
    } else {
        action["delta_heading"] = 0.0;
        action["delta_altitude"] = 0.0;
        action["delta_speed"] = 0.0;
    }
    if (BYPASS_THROTTLE_CONTROL) {
        action["delta_speed"] = 1.0;
    }
    action_space_check::wipe_out_action(register_);

    fdm->step(action);
    if (fdm->is_terminated()) {
        SL::get().printf("[Fighter] %s FDM terminated, setting is_alive to false\n", uid.c_str());
        is_alive = false;
        bloods = 0.0;
        write_register();
        return;
    }

    position = fdm->get_position();
    velocity = fdm->get_velocity();

    if (sensors.size() == 0) {
        SL::get().printf("Warning: Fighter %s has no sensors\n", uid.c_str());
    }
    update_sensors();

    if (bloods <= 0.0) {
        is_alive = false;
    }

    // write_register();
}

double Fighter::get_speed() const noexcept {
    return fdm->get_speed();
}

double Fighter::get_heading() const noexcept {
    return fdm->get_heading();
}

double Fighter::get_pitch() const noexcept {
    return fdm->get_pitch();
}

double Fighter::get_roll() const noexcept {
    return fdm->get_roll();
}

std::array<double, 3> Fighter::get_rpy() const noexcept {
    return fdm->get_rpy();
}

}
