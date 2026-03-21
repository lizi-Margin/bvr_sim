#include "aim120c.hxx"
#include "../aircraft/base.hxx"
#include "../sense/base.hxx"
#include "../ground/base.hxx"
#include "../ground/aa.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using c3utils::rad2deg;
using c3utils::Vector3;
using c3utils::linalg_norm;

constexpr bool prevent_low_loft = false;

double signed_angle(const std::array<double, 3>& from_direction, const std::array<double, 3>& to_direction) noexcept {
    std::array<double, 3> cross = {
        from_direction[1] * to_direction[2] - from_direction[2] * to_direction[1],
        from_direction[2] * to_direction[0] - from_direction[0] * to_direction[2],
        from_direction[0] * to_direction[1] - from_direction[1] * to_direction[0]
    };
    double cross_mag = linalg_norm(cross);
    double dot_val = from_direction[0] * to_direction[0] +
                     from_direction[1] * to_direction[1] +
                     from_direction[2] * to_direction[2];
    double angle = std::atan2(cross_mag, dot_val);
    return rad2deg(angle);
}

AIM120C::AIM120C(
    const std::string& uid,
    TeamColor color,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& friend_obj,
    const std::shared_ptr<SimulatedObject>& target,
    double dt,
    std::optional<double> t_thrust_override
) noexcept
    : Missile(uid, "AIM-120C7", color, parent, friend_obj, target, dt),
      speed(linalg_norm(velocity)),
      posture{0.0, 0.0, 0.0},
      guide_cmd_valid(true),
      radar_pitch(0.0),
      radar_yaw(0.0),
      losstime(0.0),
      loss(false),
    //   radar(this),
      L_beta(std::nullopt),
      L_eps(std::nullopt),
      _search_fov(deg2rad(20.0)),
      _search_range(nm_to_meters(15.0)),
      _search_start_range(nm_to_meters(10.0)),
      _search_started(false),
      _track_gimbal_limit(deg2rad(90.0)),
      _g(9.81),
      _t_max(default_missile_parameter.t_max),
      _t_thrust(t_thrust_override.has_value() ? t_thrust_override.value() : default_missile_parameter.t_thrust),
      _thrust(default_missile_parameter.thrust),
      _Length(default_missile_parameter.Length),
      _Diameter(default_missile_parameter.Diameter),
      _m0(default_missile_parameter.m0),
      _dm(default_missile_parameter.dm),
      _K(default_missile_parameter.K),
      _nyz_max(default_missile_parameter.nyz_max),
      _Rc(feet_to_meters(1000.0)),
      _mach_min(0.8),
      _v_min(get_mps(_mach_min, position[2])),
      _t(0.0),
      _m(_m0),
      _dtheta(0.0),
      _dphi(0.0),
      _distance_pre(std::numeric_limits<double>::infinity()),
      _distance_increment(static_cast<size_t>(20 / dt)),
      _left_t(static_cast<int>(1 / dt)),
      _dbeta_filtered(std::nullopt),
      _before_loss_real_last_known_target_pos{0.0, 0.0, 0.0} {

    _t_thrust += dt;




    if (parent->Type == SOT::Aircraft) {
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(parent);
        check(aircraft, "dynamic cast failed");
        double init_pitch = aircraft->get_pitch();
        if (prevent_low_loft) {
            init_pitch = std::max(init_pitch, 0.0);
        }
        double heading = aircraft->get_heading();
        posture = {0.0, -init_pitch, -heading};
    } else if (parent->Type == SOT::AA) {
        auto aa = std::dynamic_pointer_cast<AA>(parent);
        check(aa, "dynamic cast failed");
        if (target->Type != SOT::Aircraft) {
            ::colorful::printHONG("AIM120C target must be an Aircraft, when fired from AA");
            std::abort();
        }
        auto target_aircraft = std::dynamic_pointer_cast<Aircraft>(target);
        check(target_aircraft, "dynamic cast failed");
        auto vel = aa->get_launch_velocity(target_aircraft);
        auto [roll, pitch, heading] = velocity_to_euler(vel);
        posture = {0.0, -pitch, -heading};
        velocity = vel;
    } else {
        ::colorful::printHONG("AIM120C must be parented by an Aircraft or AA");
        std::abort();
    }
}

bool AIM120C::_can_track_from(const std::shared_ptr<SimulatedObject>& friend_) const noexcept {
    if (!friend_) {
        return false;
    }

    if (friend_->Type == SOT::Aircraft){
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(friend_);
        if (aircraft) {
            if (!aircraft->is_alive) {
                return false;
            }
            if (!aircraft->radar) {
                return false;
            }
            for (const auto& [locked_uid, _] : aircraft->radar->get_data()) {
                if (locked_uid == target->uid) {
                    return true;
                }
            }
        }
    }

    return false;
}

bool AIM120C::can_track_target() noexcept {
    if (!target) {
        return false;
    }

    if (losstime > 0.1 && !radar_on) {
        if (!loss) {
            _before_loss_real_last_known_target_pos = last_known_target_pos;
            loss = true;
        }
        _loss_update_target_info();
    } else {
        loss = false;
    }

    if (_can_track_from(parent) || _can_track_from(friend_obj)) {
        guide_cmd_valid = true;
    } else {
        guide_cmd_valid = false;
    }

    double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    if (!_search_started) {
        double est_distance = linalg_norm({
            last_known_target_pos[0] - position[0],
            last_known_target_pos[1] - position[1],
            last_known_target_pos[2] - position[2]
        });
        if (est_distance < _search_start_range) {
            _search_started = true;
        }
    }

    if (_search_started && distance < _search_range) {
        auto heading = velocity;
        auto rel = std::array<double, 3>{
            target->position[0] - position[0],
            target->position[1] - position[1],
            target->position[2] - position[2]
        };
        double heading_norm = linalg_norm(heading);
        double denom = (distance * heading_norm + 1e-8);
        double dot_prod = heading[0] * rel[0] + heading[1] * rel[1] + heading[2] * rel[2];
        double attack_angle = std::acos(std::clamp(dot_prod / denom, -1.0, 1.0));

        if (attack_angle < _track_gimbal_limit) {
            if (guide_cmd_valid) {
                radar_on = true;
                return true;
            }
            if (attack_angle < _search_fov) {
                radar_on = true;
                return true;
            }

            Vector3 to_last_known(last_known_target_pos[0] - position[0],
                                  last_known_target_pos[1] - position[1],
                                  last_known_target_pos[2] - position[2]);
            Vector3 to_target(rel[0], rel[1], rel[2]);
            double search_angle = to_last_known.get_angle(to_target);

            if (search_angle < _search_fov) {
                radar_on = true;
                return true;
            }
        } else {
            radar_on = false;
        }
    } else {
        radar_on = false;
    }

    if (guide_cmd_valid || radar_on) {
        losstime = 0.0;
        return true;
    } else {
        losstime += dt;
        return false;
    }
}

void AIM120C::_loss_update_target_info() noexcept {
    if (loss) {
        double time_factor = std::min({losstime, std::pow(losstime, 0.95), _t_max / 6.0});
        last_known_target_pos[0] = _before_loss_real_last_known_target_pos[0] + time_factor * last_known_target_vel[0];
        last_known_target_pos[1] = _before_loss_real_last_known_target_pos[1] + time_factor * last_known_target_vel[1];
        last_known_target_pos[2] = _before_loss_real_last_known_target_pos[2] + time_factor * last_known_target_vel[2];
    }
}


std::pair<std::array<double, 2>, double> AIM120C::_guidance() noexcept {
    double x_m = position[0], y_m = position[1], z_m = position[2];
    double dx_m = velocity[0], dy_m = velocity[1], dz_m = velocity[2];
    double v_m = linalg_norm(velocity);

    if (v_m < 1e-6) {
        return {{0.0, 0.0}, std::numeric_limits<double>::infinity()};
    }

    double theta_m = std::asin(std::clamp(dz_m / v_m, -1.0, 1.0));
    double x_t = last_known_target_pos[0];
    double y_t = last_known_target_pos[1];
    double z_t = last_known_target_pos[2];

    double Rxyz = linalg_norm({x_m - x_t, y_m - y_t, z_t - z_m});
    double beta = std::atan2(y_m - y_t, x_m - x_t);
    double eps = std::atan2(z_m - z_t, linalg_norm(std::array<double, 2>{x_m - x_t, y_m - y_t}));

    double dbeta_measured = 0.0;
    if (L_beta.has_value()) {
        dbeta_measured = -(beta - L_beta.value()) / dt;
    }
    L_beta = beta;

    double deps = 0.0;
    if (L_eps.has_value()) {
        deps = -(eps - L_eps.value()) / dt;
    }
    L_eps = eps;

    if (_t < 4.0) {
        double min_val = std::min(meters_to_nm(Rxyz), 10.0);
        if (rad2deg(posture[1]) < min_val) {
            deps = std::max(deps, 0.1);
        }
    }

    double phi = std::atan2(dy_m, dx_m);
    double angle_error = norm_pi(phi - norm_pi(beta - pi));

    double angle_gain = 0.1;
    double max_cmd_rate = 1.0;
    double angle_lend_min = 0.0;
    double angleGuideTime = _t_thrust;

    double blend = 0.0;
    if (_t < angleGuideTime) {
        blend = std::max((angleGuideTime - _t) / angleGuideTime, angle_lend_min);
    } else {
        blend = angle_lend_min;
    }

    double desired_dbeta_from_angle = angle_gain * angle_error;
    desired_dbeta_from_angle = std::clamp(desired_dbeta_from_angle, -max_cmd_rate, max_cmd_rate);

    double desired_dbeta = blend * desired_dbeta_from_angle + (1.0 - blend) * dbeta_measured;
    double dbeta_cmd = desired_dbeta;

    double ny = K_func(Rxyz) * v_m / _g * std::cos(theta_m) * dbeta_cmd;
    double nz = K_func(Rxyz) * v_m / _g * deps + std::cos(theta_m);

    ny = std::clamp(ny, -_nyz_max, _nyz_max);
    nz = std::clamp(nz, -_nyz_max, _nyz_max);

    double distance = calculate_min_distance(position, velocity, last_known_target_pos, last_known_target_vel, dt);

    return {{ny, nz}, distance};
}

double AIM120C::K_func(double Rxyz) const noexcept {
    if (_t < _t_thrust) {
        return _K;
    }
    double base_K = std::max(_K * (_t_max - _t) / _t_max, 0.5);
    if (radar_on) {
        double R_min = nm_to_meters(1.0);
        double K_MAX = 2.0 * _K;
        if (Rxyz < R_min) {
            return K_MAX;
        }
        double mix = R_min / Rxyz;
        return K_MAX * _K * mix + base_K * (1.0 - mix);
    }
    return base_K;
}

double AIM120C::calculate_min_distance(
    const std::array<double, 3>& missile_pos,
    const std::array<double, 3>& missile_vel,
    const std::array<double, 3>& aircraft_pos,
    const std::array<double, 3>& aircraft_vel,
    double delta_t
) const noexcept {
    double dx = aircraft_pos[0] - missile_pos[0];
    double dy = aircraft_pos[1] - missile_pos[1];
    double dz = aircraft_pos[2] - missile_pos[2];

    double dvx = aircraft_vel[0] - missile_vel[0];
    double dvy = aircraft_vel[1] - missile_vel[1];
    double dvz = aircraft_vel[2] - missile_vel[2];

    double a = dvx * dvx + dvy * dvy + dvz * dvz;
    if (a < 1e-12) {
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }

    double dot = dx * dvx + dy * dvy + dz * dvz;
    double t0 = -dot / a;

    double distance_sq;
    if (t0 <= 0) {
        distance_sq = dx * dx + dy * dy + dz * dz;
    } else if (t0 >= delta_t) {
        double dx_end = dx + dvx * delta_t;
        double dy_end = dy + dvy * delta_t;
        double dz_end = dz + dvz * delta_t;
        distance_sq = dx_end * dx_end + dy_end * dy_end + dz_end * dz_end;
    } else {
        distance_sq = (dx * dx + dy * dy + dz * dz) - (dot * dot) / a;
    }

    return std::sqrt(std::max(distance_sq, 0.0));
}

void AIM120C::_state_trans_eula(const std::array<double, 2>& action) noexcept {
    double ny = action[0];
    double nz = action[1];

    position[0] += dt * velocity[0];
    position[1] += dt * velocity[1];
    position[2] += dt * velocity[2];

    double v = linalg_norm(velocity);
    if (v < 1e-6) {
        return;
    }

    double angle = deg2rad(-std::copysign(1.0, velocity[2]) *
                           signed_angle(velocity, {velocity[0], velocity[1], 0.0}));
    double theta = posture[1];
    double phi = posture[2];

    Vector3 body_x(1.0, 0.0, 0.0);
    body_x.rotate_zyx_self(0.0, _dtheta * dt, _dphi * dt);
    Vector3 ref_x(1.0, 0.0, 0.0);
    double alpha_est = body_x.get_angle(ref_x);

    auto [drag, cx] = aero.compute_drag(v, alpha_est, position[2]);

    double thrust = (_t < _t_thrust) ? _thrust : 0.0;
    double gravity = _m * _g * std::sin(angle);

    double nx = (thrust - drag + gravity) / (_m * _g);
    double dv = _g * (nx - std::sin(theta));

    _dphi = _g / v * (ny / std::cos(theta));
    _dtheta = _g / v * (nz - std::cos(theta));

    v += dt * dv;
    phi += dt * _dphi;
    theta += dt * _dtheta;

    velocity[0] = v * std::cos(theta) * std::cos(phi);
    velocity[1] = -v * std::cos(theta) * std::sin(phi);
    velocity[2] = v * std::sin(theta);

    posture[0] = 0.0;
    posture[1] = theta;
    posture[2] = phi;

    if (_t < _t_thrust) {
        _m -= dt * _dm;
    }
}

void AIM120C::_state_trans(const std::array<double, 2>& action) noexcept {
    double ny = action[0];
    double nz = action[1];

    double v = linalg_norm(velocity);
    if (v < 1e-6) {
        return;
    }

    double theta_0 = posture[1];
    double phi_0 = posture[2];
    auto pos_0 = position;
    double v_0 = v;

    auto derivatives = [&](const std::array<double, 3>& pos, double vel_mag, double theta, double phi,
                           double dphi_prev, double dtheta_prev) -> std::tuple<std::array<double, 3>, double, double, double> {
        double angle = deg2rad(-std::copysign(1.0, pos[2]) *
                               signed_angle({vel_mag * std::cos(theta) * std::cos(phi),
                                           -vel_mag * std::cos(theta) * std::sin(phi),
                                            vel_mag * std::sin(theta)},
                                          {vel_mag * std::cos(theta) * std::cos(phi),
                                           -vel_mag * std::cos(theta) * std::sin(phi),
                                            0.0}));

        Vector3 body_x(1.0, 0.0, 0.0);
        body_x.rotate_zyx_self(0.0, dtheta_prev * dt, dphi_prev * dt);
        Vector3 ref_x(1.0, 0.0, 0.0);
        double alpha_est = body_x.get_angle(ref_x) * 2.0;

        auto [drag, cx] = aero.compute_drag(vel_mag, alpha_est, pos[2]);

        double thrust = (_t < _t_thrust) ? _thrust : 0.0;
        double gravity = _m * _g * std::sin(angle);

        double nx = (thrust - drag + gravity) / (_m * _g);
        double dv = _g * (nx - std::sin(theta));

        double dphi = _g / vel_mag * (ny / std::cos(theta));
        double dtheta = _g / vel_mag * (nz - std::cos(theta));

        std::array<double, 3> velocity = {
            vel_mag * std::cos(theta) * std::cos(phi),
            -vel_mag * std::cos(theta) * std::sin(phi),
            vel_mag * std::sin(theta)
        };

        return {velocity, dv, dphi, dtheta};
    };

    auto [vel_k1, dv_k1, dphi_k1, dtheta_k1] = derivatives(pos_0, v_0, theta_0, phi_0, _dphi, _dtheta);
    auto pos_k2 = std::array<double, 3>{pos_0[0] + 0.5 * dt * vel_k1[0],
                                        pos_0[1] + 0.5 * dt * vel_k1[1],
                                        pos_0[2] + 0.5 * dt * vel_k1[2]};
    double v_k2 = v_0 + 0.5 * dt * dv_k1;
    double theta_k2 = theta_0 + 0.5 * dt * dtheta_k1;
    double phi_k2 = phi_0 + 0.5 * dt * dphi_k1;

    auto [vel_k2, dv_k2, dphi_k2, dtheta_k2] = derivatives(pos_k2, v_k2, theta_k2, phi_k2, dphi_k1, dtheta_k1);
    auto pos_k3 = std::array<double, 3>{pos_0[0] + 0.5 * dt * vel_k2[0],
                                        pos_0[1] + 0.5 * dt * vel_k2[1],
                                        pos_0[2] + 0.5 * dt * vel_k2[2]};
    double v_k3 = v_0 + 0.5 * dt * dv_k2;
    double theta_k3 = theta_0 + 0.5 * dt * dtheta_k2;
    double phi_k3 = phi_0 + 0.5 * dt * dphi_k2;

    auto [vel_k3, dv_k3, dphi_k3, dtheta_k3] = derivatives(pos_k3, v_k3, theta_k3, phi_k3, dphi_k2, dtheta_k2);
    auto pos_k4 = std::array<double, 3>{pos_0[0] + dt * vel_k3[0],
                                        pos_0[1] + dt * vel_k3[1],
                                        pos_0[2] + dt * vel_k3[2]};
    double v_k4 = v_0 + dt * dv_k3;
    double theta_k4 = theta_0 + dt * dtheta_k3;
    double phi_k4 = phi_0 + dt * dphi_k3;

    auto [vel_k4, dv_k4, dphi_k4, dtheta_k4] = derivatives(pos_k4, v_k4, theta_k4, phi_k4, dphi_k3, dtheta_k3);

    position[0] = pos_0[0] + (dt / 6.0) * (vel_k1[0] + 2*vel_k2[0] + 2*vel_k3[0] + vel_k4[0]);
    position[1] = pos_0[1] + (dt / 6.0) * (vel_k1[1] + 2*vel_k2[1] + 2*vel_k3[1] + vel_k4[1]);
    position[2] = pos_0[2] + (dt / 6.0) * (vel_k1[2] + 2*vel_k2[2] + 2*vel_k3[2] + vel_k4[2]);

    double v_new = v_0 + (dt / 6.0) * (dv_k1 + 2*dv_k2 + 2*dv_k3 + dv_k4);
    double theta_new = theta_0 + (dt / 6.0) * (dtheta_k1 + 2*dtheta_k2 + 2*dtheta_k3 + dtheta_k4);
    double phi_new = phi_0 + (dt / 6.0) * (dphi_k1 + 2*dphi_k2 + 2*dphi_k3 + dphi_k4);

    _dphi = (phi_new - phi_0) / dt;
    _dtheta = (theta_new - theta_0) / dt;

    velocity[0] = v_new * std::cos(theta_new) * std::cos(phi_new);
    velocity[1] = -v_new * std::cos(theta_new) * std::sin(phi_new);
    velocity[2] = v_new * std::sin(theta_new);

    posture[0] = 0.0;
    posture[1] = theta_new;
    posture[2] = phi_new;

    if (_t < _t_thrust) {
        _m -= dt * _dm;
    }
}

void AIM120C::step() noexcept {
    SL::get().print("[AIM120C] step called");
    if (!is_alive) {
        return;
    }

    if (!target) {
        return;
    }

    _t += dt;
    speed = linalg_norm(velocity);
    _v_min = get_mps(_mach_min, position[2]);
    update_target_info();

    double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    _distance_increment.push_back(distance > _distance_pre);
    _distance_pre = distance;

    bool timeout = _t > _t_max;
    bool crash = position[2] < 0.0;
    bool too_slow = (_t > _t_thrust && get_speed() < _v_min);
    bool farther_and_farther_away = (_distance_increment.size() == _distance_increment.max_size() &&
                                     std::count(_distance_increment.begin(), _distance_increment.end(), true) >=
                                     static_cast<int>(_distance_increment.max_size()));
    bool target_down = !(target && target->is_alive);

    if (distance < _Rc && target && target->is_alive) {
        
        

        if (target->Type == SOT::Aircraft) {
            auto aircraft = std::dynamic_pointer_cast<Aircraft>(target);
            if (!aircraft) {
                colorful::printHONG("[AIM120C] dynamic cast failed");
                std::abort();
            }
            aircraft->hit();
        } else if (target->Type == SOT::GroundUnit) {
            auto ground = std::dynamic_pointer_cast<GroundUnit>(target);
            if (!ground) {
                colorful::printHONG("[AIM120C] dynamic cast failed");
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
            log_done_reason = "too_slow " + std::to_string(get_speed()) + " < " + std::to_string(_v_min);
        } else if (farther_and_farther_away) {
            log_done_reason = "farther_and_farther_away";
        } else if (target_down) {
            log_done_reason = "target_down";
        }
    } else {
        auto [action, distance_that_missile_knows] = _guidance();
        _state_trans_eula(action);
    }

    if (is_done) {
        is_alive = false;
    }
    // write_register();
}

}
