#include "mmodelA.hxx"
#include "../aircraft/base.hxx"
#include "../ground/base.hxx"
#include "../ground/aa.hxx"
#include "../simulator.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>
#include <limits>

namespace bvr_sim {

using c3utils::rad2deg;
using c3utils::deg2rad;
using c3utils::Vector3;
using c3utils::linalg_norm;
using c3utils::get_mps;
using c3utils::get_mach;
using c3utils::feet_to_meters;
using c3utils::nm_to_meters;

MModelA::MModelA(
    const std::string& uid,
    TeamColor color,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& friend_obj,
    const std::shared_ptr<SimulatedObject>& target,
    double dt,
    const std::string& missile_model
) noexcept
    : Missile(uid, "MModelA", color, parent, friend_obj, target, dt),
      params_(MissileParams::get_missile_params(missile_model)),
      speed(linalg_norm(velocity)),
      posture{0.0, 0.0, 0.0},
      radar_pitch(0.0),
      radar_yaw(0.0),
      guide_cmd_valid(true),
      losstime(0.0),
      loss(false),
      L_beta(std::nullopt),
      L_eps(std::nullopt),
      _dbeta_filtered(std::nullopt),
      _search_started(false),
      _t(0.0),
      _m(params_.m0),
      _dtheta(0.0),
      _dphi(0.0),
      _distance_pre(std::numeric_limits<double>::infinity()),
      _left_t(static_cast<int>(1.0 / dt)),
      _before_loss_real_last_known_target_pos{0.0, 0.0, 0.0}
{
    // Initialize _distance_increment as deque<bool> with size 20
    for (int i = 0; i < 20; ++i) {
        _distance_increment.push_back(false);
    }

    // Initialize parent aircraft posture if applicable
    if (parent->Type == SOT::Aircraft) {
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(parent);
        check(aircraft, "dynamic cast failed");
        double init_pitch = aircraft->get_pitch();
        double heading = aircraft->get_heading();
        posture = {0.0, -init_pitch, -heading};
    } else if (parent->Type == SOT::AA) {
        auto aa = std::dynamic_pointer_cast<AA>(parent);
        check(aa, "dynamic cast failed");
        if (target->Type != SOT::Aircraft) {
            ::colorful::printHONG("MModelA target must be an Aircraft, when fired from AA");
            std::abort();
        }
        auto target_aircraft = std::dynamic_pointer_cast<Aircraft>(target);
        check(target_aircraft, "dynamic cast failed");
        auto vel = aa->get_launch_velocity(target_aircraft);
        auto [roll, pitch, heading] = velocity_to_euler(vel);
        posture = {0.0, -pitch, -heading};
        velocity = vel;
    } else {
        ::colorful::printHONG("MModelA must be parented by an Aircraft or AA");
        std::abort();
    }
}

void MModelA::step() noexcept {
    if (!is_alive) {
        return;
    }

    if (!target) {
        return;
    }

    _t += dt;
    speed = linalg_norm(velocity);

    update_target_info();

    double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    _distance_increment.push_back(distance > _distance_pre);
    _distance_pre = distance;

    bool timeout = _t > params_.t_max;
    bool crash = position[2] < 0.0;
    double v_min = get_mps(params_.mach_min, position[2]);
    bool too_slow = (_t > params_.t_thrust && speed < v_min);
    bool farther_and_farther_away = (_distance_increment.size() == _distance_increment.max_size() &&
                                     std::count(_distance_increment.begin(), _distance_increment.end(), true) >=
                                     static_cast<int>(_distance_increment.max_size()));
    bool target_down = !(target && target->is_alive);

    if (distance < params_.Rc && target && target->is_alive) {
        if (target->Type == SOT::Aircraft) {
            auto aircraft = std::dynamic_pointer_cast<Aircraft>(target);
            if (!aircraft) {
                colorful::printHONG("[MModelA] dynamic cast failed");
                std::abort();
            }
            aircraft->hit();
        } else if (target->Type == SOT::GroundUnit) {
            auto ground = std::dynamic_pointer_cast<GroundUnit>(target);
            if (!ground) {
                colorful::printHONG("[MModelA] dynamic cast failed");
                std::abort();
            }
            if (ground->check_collision(position)) {
                ground->hit();
            } else {
                ground->hit(10.0);
            }
        }

        is_success = true;
        is_done = true;
        log_done_reason = "hit";
    } else if (timeout || crash || too_slow || farther_and_farther_away || target_down) {
        is_success = false;
        is_done = true;

        if (timeout) {
            log_done_reason = "timeout";
        } else if (crash) {
            log_done_reason = "crash";
        } else if (too_slow) {
            log_done_reason = "too_slow " + std::to_string(speed) + " < " + std::to_string(v_min);
        } else if (farther_and_farther_away) {
            log_done_reason = "farther_and_farther_away";
        } else if (target_down) {
            log_done_reason = "target_down";
        }
    } else {
        auto [cmd_beta, cmd_eps] = update_guidance();
        _state_trans({cmd_beta, cmd_eps});
    }

    if (is_done) {
        is_alive = false;
    }
}

std::pair<double, double> MModelA::update_guidance() noexcept {
    // TODO: Implement guidance logic (copy from aim120c.cxx::_guidance())
    // Return proportional navigation commands [cmd_beta, cmd_eps]
    return {0.0, 0.0};
}

void MModelA::_state_trans(const std::array<double, 2>& action) noexcept {
    // TODO: Implement state transition and control surface dynamics
    // (copy from aim120c.cxx::_state_trans())
}

void MModelA::update_aerodynamics() noexcept {
    // Simplified: Mach-only drag lookup (no AOA compensation)
    double mach = speed / get_mps(1.0, position[2]);
    mach = std::max(mach, params_.mach_min);
    double cx_total = params_.cx_total_table->interpolate(mach);

    // Atmospheric density: exponential model
    double rho = 1.225 * std::exp(-position[2] / 9300.0);

    // Drag force: 0.5 * rho * v^2 * Cx * S_ref
    double drag_force = 0.5 * rho * speed * speed * cx_total * params_.S_ref;

    // TODO: Apply drag_force to velocity updates in update_kinematics()
}

void MModelA::update_kinematics() noexcept {
    // TODO: Implement RK4 integration for position/velocity/attitude
    // (copy kinematic integration logic from aim120c.cxx)
}

} // namespace bvr_sim
