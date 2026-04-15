#include "aim120c.hxx"
#include "../aircraft/base.hxx"
#include "../sense/base.hxx"
#include "../ground/base.hxx"
#include "../ground/aa.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "c3utils/c3utils.hxx"
#include "rubbish_can/interp_table.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using c3utils::rad2deg;
using c3utils::Vector3;
using c3utils::linalg_norm;

constexpr bool prevent_low_loft = false;

namespace {

constexpr double kMinSpeed = 1e-6;
constexpr std::array<double, 3> kGravityNwu = {0.0, 0.0, -1.0};

std::array<double, 3> velocity_to_rpy_nwu(const std::array<double, 3>& vel) noexcept {
    const auto angles = Vector3(vel).get_rotate_angle_fix();
    return {angles[0], angles[1], angles[2]};
}

std::array<double, 3> scale_vec(const std::array<double, 3>& vec, double scale) noexcept {
    return {vec[0] * scale, vec[1] * scale, vec[2] * scale};
}

std::array<double, 3> add_scaled_vec(
    const std::array<double, 3>& lhs,
    const std::array<double, 3>& rhs,
    double scale
) noexcept {
    return {lhs[0] + rhs[0] * scale, lhs[1] + rhs[1] * scale, lhs[2] + rhs[2] * scale};
}

}

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
    const std::string& missile_model,
    TeamColor color,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& friend_obj,
    const std::shared_ptr<SimulatedObject>& target,
    double dt,
    std::optional<double> t_thrust_override
) noexcept
    : Missile(uid, missile_model, color, parent, friend_obj, target, dt),
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
      _search_fov(deg2rad(15.0)),
      _search_range(nm_to_meters(15.0)),
      _search_start_range(nm_to_meters(10.0)),
      _search_started(false),
      _track_gimbal_limit(deg2rad(60.0)),
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
      _Rc(feet_to_meters(500.0)),
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
        posture = {0.0, init_pitch, heading};
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
        posture = {0.0, pitch, heading};
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

    double pitch_m = std::atan2(-dz_m, std::sqrt(dx_m * dx_m + dy_m * dy_m));
    double climb_angle_m = -pitch_m;
    double x_t = last_known_target_pos[0];
    double y_t = last_known_target_pos[1];
    double z_t = last_known_target_pos[2];

    double Rxyz = linalg_norm({x_m - x_t, y_m - y_t, z_t - z_m});
    // double beta = std::atan2(y_m - y_t, x_m - x_t);
    double beta = std::atan2(y_t - y_m, x_t - x_m);
    double eps = std::atan2(z_t - z_m, linalg_norm(std::array<double, 2>{x_t - x_m, y_t - y_m}));

    double dbeta = 0.0;
    if (L_beta.has_value()) {
        dbeta = norm_pi(beta - L_beta.value()) / dt;
    }
    L_beta = beta;

    double deps = 0.0;
    if (L_eps.has_value()) {
        deps = norm_pi(eps - L_eps.value()) / dt;
    }
    L_eps = eps;

    if (!radar_on && _t < 4.0) {
        double min_val = std::min(meters_to_nm(Rxyz), 10.0);
        if (rad2deg(posture[1]) < min_val) {
            deps = std::max(deps, 0.1);
        }
    }

    double phi = std::atan2(dy_m, dx_m);
    double angle_error = norm_pi(beta - phi);






    double desired_dbeta;
    
    if (radar_on && Rxyz < feet_to_meters(5000.0)) {
        // double desired_dbeta_from_angle;
        // double angle_gain = 5.0;
        // // desired_dbeta_from_angle = angle_gain * angle_error;
        // // if (desired_dbeta_from_angle * dbeta < 0) {
        // //     desired_dbeta = desired_dbeta_from_angle;
        // // } else {
        // //     desired_dbeta = std::max(std::abs(desired_dbeta_from_angle), std::abs(dbeta)) * std::copysign(1.0, desired_dbeta_from_angle);
        // // }
        // // desired_dbeta = dbeta;
        // desired_dbeta_from_angle = angle_gain * -1 * angle_error;
        // desired_dbeta = desired_dbeta_from_angle;
        desired_dbeta = dbeta;
    } else if (_t < _t_thrust) {
        double desired_dbeta_from_angle;
        double angle_lend_min = 0.0;
        double angle_gain = 0.1;
        double max_cmd_rate = 0.5;
        double blend = std::max((_t_thrust - _t) / _t_thrust, angle_lend_min);
        desired_dbeta_from_angle = angle_gain * -1 * angle_error;
        desired_dbeta_from_angle = std::clamp(desired_dbeta_from_angle, -max_cmd_rate, max_cmd_rate);
        desired_dbeta = blend * desired_dbeta_from_angle + (1.0 - blend) * dbeta;
        // desired_dbeta = dbeta;
    } else {
        desired_dbeta = dbeta;
    }


    double ny = K_func(Rxyz) * v_m / _g * std::cos(climb_angle_m) * desired_dbeta;
    double nz = K_func(Rxyz) * v_m / _g * deps + std::cos(climb_angle_m);

    // ny = std::clamp(ny, ny_filter.get_value() - 2.0 * dt, ny_filter.get_value() + 2.0 * dt);
    // ny_filter.update(ny, dt);

    ny = std::clamp(ny, -_nyz_max, _nyz_max);
    nz = std::clamp(nz, -_nyz_max, _nyz_max);

    double distance = calculate_min_distance(position, velocity, last_known_target_pos, last_known_target_vel, dt);

    return {{ny, nz}, distance};
}

double AIM120C::K_func(double Rxyz) const noexcept {
    double base_K = std::max(_K * (_t_max - _t) / _t_max, 0.5);
    if (radar_on) {
        // double R_min = nm_to_meters(1.0);
        // double K_MAX = 5.0 * _K;
        // if (Rxyz < R_min) {
        //     return K_MAX;
        // }
        // double mix = R_min / Rxyz;
        // return K_MAX * _K * mix + base_K * (1.0 - mix);
        return _K;
    }

    if (_t < _t_thrust) {
        return _K;
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

// void AIM120C::_state_trans_eula(const std::array<double, 2>& action) noexcept {
//     double ny = action[0];
//     double nz = action[1];

//     position[0] += dt * velocity[0];
//     position[1] += dt * velocity[1];
//     position[2] += dt * velocity[2];

//     double v = linalg_norm(velocity);
//     if (v < 1e-6) {
//         return;
//     }

//     double angle = deg2rad(-std::copysign(1.0, velocity[2]) *
//                            signed_angle(velocity, {velocity[0], velocity[1], 0.0}));
//     double theta = posture[1];
//     double phi = posture[2];

//     Vector3 body_x(1.0, 0.0, 0.0);
//     body_x.rotate_zyx_self(0.0, _dtheta, _dphi);
//     Vector3 ref_x(1.0, 0.0, 0.0);
//     double alpha_est = body_x.get_angle(ref_x);
//     // alpha_est *= alpha_est_angle_table.interpolate(alpha_est);
//     alpha_est *= alpha_est_mach_table.interpolate(c3u::get_mach(v, position[2]));
//     alpha_est = std::clamp(alpha_est, 0.0, deg2rad(80.0));

//     auto [drag, cx] = aero.compute_drag(v, alpha_est, position[2]);

//     double thrust = (_t < _t_thrust) ? _thrust : 0.0;
//     double gravity = _m * _g * std::sin(angle);

//     double nx = (thrust - drag + gravity) / (_m * _g);
//     double dv = _g * (nx - std::sin(theta));

//     _dphi = _g / v * (ny / std::cos(theta));
//     _dtheta = _g / v * (nz - std::cos(theta));

//     v += dt * dv;
//     phi += dt * _dphi;
//     theta += dt * _dtheta;

//     velocity[0] = v * std::cos(theta) * std::cos(phi);
//     velocity[1] = -v * std::cos(theta) * std::sin(phi);
//     velocity[2] = v * std::sin(theta);

//     posture[0] = 0.0;
//     posture[1] = theta;
//     posture[2] = phi;

//     if (_t < _t_thrust) {
//         _m -= dt * _dm;
//     }
// }

void AIM120C::_state_trans(const std::array<double, 2>& action) noexcept {
    double ny = action[0];
    double nz = action[1];

    double v = linalg_norm(velocity);
    if (v < kMinSpeed) {
        return;
    }

    auto pos_0 = position;
    auto vel_0 = velocity;
    const auto rpy_0 = velocity_to_rpy_nwu(vel_0);
    const double theta_0 = rpy_0[1];
    const double phi_0 = rpy_0[2];

    auto compute_alpha_est = [&](double speed, const std::array<double, 3>& pos,
                                 double dphi_prev, double dtheta_prev) noexcept {
        Vector3 body_x(1.0, 0.0, 0.0);
        body_x.rotate_zyx_self(0.0, dtheta_prev * dt, dphi_prev * dt);
        Vector3 ref_x(1.0, 0.0, 0.0);
        double alpha_est = body_x.get_angle(ref_x) * 2.0;
        // alpha_est *= alpha_est_angle_table.interpolate(alpha_est);
        alpha_est *= alpha_est_mach_table.interpolate(c3u::get_mach(speed, pos[2]));
        return std::clamp(alpha_est, 0.0, deg2rad(80.0));
    };

    auto derivatives = [&](const std::array<double, 3>& pos, const std::array<double, 3>& vel,
                           double dphi_prev, double dtheta_prev)
        -> std::tuple<std::array<double, 3>, std::array<double, 3>> {
        const double speed = linalg_norm(vel);
        if (speed < kMinSpeed) {
            return {vel, {0.0, 0.0, 0.0}};
        }

        const auto rpy = velocity_to_rpy_nwu(vel);
        const double theta = rpy[1];
        const double phi = rpy[2];
        const std::array<double, 3> forward = scale_vec(vel, 1.0 / speed);
        auto side = Vector3(0.0, 1.0, 0.0).rotate_zyx_self(0.0, theta, phi).get_list();
        auto normal_up = Vector3(0.0, 0.0, 1.0).rotate_zyx_self(0.0, theta, phi).get_list();

        const double alpha_est = compute_alpha_est(speed, pos, dphi_prev, dtheta_prev);
        auto [drag, cx] = aero.compute_drag(speed, alpha_est, pos[2]);

        double thrust = (_t < _t_thrust) ? _thrust : 0.0;
        const double axial_accel = (thrust - drag) / _m;

        std::array<double, 3> accel = scale_vec(forward, axial_accel);
        accel = add_scaled_vec(accel, side, _g * ny);
        accel = add_scaled_vec(accel, normal_up, _g * nz);
        accel = add_scaled_vec(accel, kGravityNwu, _g);

        return {vel, accel};
    };

    auto [dpos_k1, dvel_k1] = derivatives(pos_0, vel_0, _dphi, _dtheta);

    auto pos_k2 = add_scaled_vec(pos_0, dpos_k1, 0.5 * dt);
    auto vel_k2 = add_scaled_vec(vel_0, dvel_k1, 0.5 * dt);
    auto rpy_k2 = velocity_to_rpy_nwu(vel_k2);
    double dphi_k1 = norm_pi(rpy_k2[2] - phi_0) / std::max(0.5 * dt, 1e-9);
    double dtheta_k1 = norm_pi(rpy_k2[1] - theta_0) / std::max(0.5 * dt, 1e-9);

    auto [dpos_k2, dvel_k2] = derivatives(pos_k2, vel_k2, dphi_k1, dtheta_k1);

    auto pos_k3 = add_scaled_vec(pos_0, dpos_k2, 0.5 * dt);
    auto vel_k3 = add_scaled_vec(vel_0, dvel_k2, 0.5 * dt);
    auto rpy_k3 = velocity_to_rpy_nwu(vel_k3);
    double dphi_k2 = norm_pi(rpy_k3[2] - phi_0) / std::max(0.5 * dt, 1e-9);
    double dtheta_k2 = norm_pi(rpy_k3[1] - theta_0) / std::max(0.5 * dt, 1e-9);

    auto [dpos_k3, dvel_k3] = derivatives(pos_k3, vel_k3, dphi_k2, dtheta_k2);

    auto pos_k4 = add_scaled_vec(pos_0, dpos_k3, dt);
    auto vel_k4 = add_scaled_vec(vel_0, dvel_k3, dt);
    auto rpy_k4 = velocity_to_rpy_nwu(vel_k4);
    double dphi_k3 = norm_pi(rpy_k4[2] - phi_0) / dt;
    double dtheta_k3 = norm_pi(rpy_k4[1] - theta_0) / dt;

    auto [dpos_k4, dvel_k4] = derivatives(pos_k4, vel_k4, dphi_k3, dtheta_k3);

    for (size_t i = 0; i < 3; ++i) {
        position[i] = pos_0[i] + (dt / 6.0) *
            (dpos_k1[i] + 2.0 * dpos_k2[i] + 2.0 * dpos_k3[i] + dpos_k4[i]);
        velocity[i] = vel_0[i] + (dt / 6.0) *
            (dvel_k1[i] + 2.0 * dvel_k2[i] + 2.0 * dvel_k3[i] + dvel_k4[i]);
    }

    posture = velocity_to_rpy_nwu(velocity);
    _dphi = norm_pi(posture[2] - phi_0) / dt;
    _dtheta = norm_pi(posture[1] - theta_0) / dt;

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
        // _state_trans_eula(action);
        _state_trans(action);
    }

    if (is_done) {
        is_alive = false;
    }
    // write_register();
}

std::array<double, 3> AIM120C::get_rpy() const noexcept {
    return posture;
}

}
