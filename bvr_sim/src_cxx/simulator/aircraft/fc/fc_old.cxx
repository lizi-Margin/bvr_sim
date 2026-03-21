#include "fc_old.hxx"
#include "c3utils/c3utils.hxx"
#include "funcs.hxx"
#include "io.hxx"
#include "vector.hxx"

namespace bvr_sim {

using c3utils::deg2rad;
using c3utils::feet_to_meters;
using c3utils::norm;
using c3utils::pi;

CrashingCounter::CrashingCounter(double dt, double max_time) noexcept
    : dt(dt), max_time(max_time), timer(max_time) {}

bool CrashingCounter::update(bool crashing) noexcept {
    if (crashing) {
        timer = 0.;
    } else {
        timer += dt;
    }
    return timer < max_time;
}

StdFlightController::StdFlightController(double dt, const std::string& aircraft_model) noexcept
    : dt(dt),
      sum_err_roll(0), last_err_roll(0),
      sum_err_pitch(0), last_err_pitch(0),
      sum_err_throttle(0), last_err_throttle(0),
      right_turn(0),
      crashing_counter(dt, 5.) {

    // 从Manager获取参数
    auto& manager = FlightControllerParamsManager::getInstance();
    params_ = manager.getParams(aircraft_model);

    // 设置PID系数
    kroll_p_ = params_.kroll_p;
    kroll_i_ = params_.kroll_i;
    kroll_d_ = params_.kroll_d;

    kpitch_p_ = params_.kpitch_p;
    kpitch_i_ = params_.kpitch_i;
    kpitch_d_ = params_.kpitch_d;

    kthrottle_p_ = params_.kthrottle_p;
    kthrottle_i_ = params_.kthrottle_i;
    kthrottle_d_ = params_.kthrottle_d;
}

void StdFlightController::reset() noexcept {
}

std::array<double, 4> StdFlightController::norm_fc_output(std::array<double, 4> action4) noexcept {
    action4[0] = norm(action4[0]);
    action4[1] = norm(action4[1]);
    action4[2] = norm(action4[2]);
    action4[3] = norm(action4[3], 0., 1.);
    return action4;
}

std::array<double, 4> StdFlightController::direct_LU_flight_controler(
    const FighterState& fighter,
    const Vector3& fix_vec,
    double intent_mach,
    double strength_bias
) noexcept {

    auto intent_heading = fix_vec.get_list();
    Vector3 intent_heading_vec_fix_origin(intent_heading);

    bool crashing = false;

    double ttg = (std::max(fighter.height, 0.) / std::max(fighter.vd, 1e-3));
    if (
        (ttg < 25 || fighter.pitch < -params_.max_pitch_angle)
        || fighter.height < params_.low_alt_threshold
    ) {
        if (fighter.height < params_.crash_height_threshold) {
            crashing = true;
        }
    }

    crashing = crashing_counter.update(crashing);

    if (crashing) {
        intent_heading[2] = 0;
        if (fighter.height < params_.severe_crash_height) {
            intent_heading = fighter.heading.get_list();
            intent_heading[2] = 0;
            intent_heading[2] = Vector3(intent_heading).get_module()/3;
        }

        // intent_heading[2] = std::tan(20) * Vector3(intent_heading).get_module();
        // auto rot = Vector3(intent_heading).normalize();
        // rot.rotate_zyx_self(0., -c3u::deg2rad(45), 0.);
        // intent_heading = rot.normalize().get_list();
    }

    intent_heading[2] = -intent_heading[2];
    Vector3 intent_heading_vec(intent_heading);
    intent_heading_vec.rev_rotate_zyx_self(fighter.roll, fighter.pitch, fighter.yaw);
    intent_heading_vec[2] = -1 * intent_heading_vec[2];
    intent_heading_vec = intent_heading_vec.normalize();

    Vector3 intent_heading_saver(intent_heading_vec.get_list());

    double err_pitch = Vector3(1, 0, 0).get_angle(intent_heading_vec, 1);
    if (err_pitch < 0) err_pitch *= 4;
    if (err_pitch > params_.max_pitch_angle) err_pitch = params_.max_pitch_angle;
    if (err_pitch < -params_.max_pitch_angle) err_pitch = -params_.max_pitch_angle;
    if (intent_heading_vec[0] < 0) {
        err_pitch = params_.max_pitch_angle;
    }
    err_pitch *= 1.5 / 2;

    double gain = 1. * std::tanh(-(fighter.vd - 50 * (fighter.height - 6000) / 11500) * 1e-2);

    double intent_location_angle = fighter.heading.get_angle(intent_heading_vec_fix_origin);
    // double low_alt_thre = params_.altitude_loss_threshold;

    double err_roll = 0;

    if (crashing) {
        // if (intent_location_angle > deg2rad(15)) {
        //     err_roll = 0;

        //     if (intent_heading_vec[1] > 0) right_turn = 1;
        //     if (intent_heading_vec[1] < 0) right_turn = -1;

        //     double deg_turn = deg2rad(55);
        //     err_roll += (-1.4 * (fighter.roll + right_turn * deg_turn));
        //     // if (fighter.roll > 0) err_roll += 1 * gain;
        //     // else err_roll += -1 * gain;
        // }
        // else {
            err_roll = Vector3(0, 0, 1).get_angle(intent_heading_vec, 0);
            right_turn = 0;
        // }
    }
    else if (intent_location_angle > params_.turn_angle_99deg) {
        err_roll = 0;

        if (intent_heading_vec[1] > 0 && right_turn == 0) right_turn = 1;
        if (intent_heading_vec[1] < 0 && right_turn == 0) right_turn = -1;

        double deg_turn = params_.turn_angle_90deg;
        if (right_turn == 1) err_roll += (-1.4 * (fighter.roll - deg_turn));
        if (right_turn == -1) err_roll += (-1.4 * (fighter.roll + deg_turn));
        if (fighter.roll > 0) err_roll += 1 * gain;
        else err_roll += -1 * gain;
    }
    else {
        if (err_pitch < 0 && err_pitch > deg2rad(-15)) {
            err_roll = Vector3(0, 0, -1).get_angle(intent_heading_vec, 0);
        } else {
            err_roll = Vector3(0, 0, 1).get_angle(intent_heading_vec, 0);
        }

        right_turn = 0;
    }

    intent_heading_vec = intent_heading_saver;

    double err_roll_angle = err_roll;
    if (err_roll > params_.max_roll_angle) err_roll = params_.max_roll_angle;
    if (err_roll < -params_.max_roll_angle) err_roll = -params_.max_roll_angle;

    double err_throttle = intent_mach - fighter.mach;

    double roll_bias = 0.75 * norm(strength_bias, -1., 1.) + 1.;
    double pitch_bias = 0.75 * norm(strength_bias, -1., 0.) + 1.;
    double kroll_p_local = kroll_p_ * roll_bias;
    double kroll_i_local = kroll_i_ * roll_bias;
    double kroll_d_local = kroll_d_ * roll_bias;
    double kpitch_p_local = kpitch_p_ * pitch_bias;
    double kpitch_i_local = kpitch_i_ * pitch_bias;
    double kpitch_d_local = kpitch_d_ * pitch_bias;

    if (fighter.height > params_.altitude_loss_threshold) {
        kpitch_p_local *= (params_.pitch_loss_threshold - fighter.height) / 9000;
        kpitch_i_local *= (params_.pitch_loss_threshold - fighter.height) / 9000;
        kroll_p_local *= (params_.roll_loss_threshold - fighter.height) / 5000;
        kroll_i_local *= (params_.roll_loss_threshold - fighter.height) / 5000;
    }

    if (crashing != true) {
        if (fighter.mach > params_.min_controlled_speed) {
            kpitch_p_local *= (fighter.mach + 0.2);
            kpitch_i_local *= (fighter.mach + 0.2);

            if (err_pitch > -pi / 12) {
                kroll_p_local *= 0.7 + 0.3 * (std::abs(err_pitch) / (1.5 * pi / 12));
                kroll_i_local *= 0.7 + 0.3 * (std::abs(err_pitch) / (1.5 * pi / 12));
            }
        } else {
            kpitch_p_local *= 0.5;
            kpitch_i_local *= 0.5;
            kroll_p_local *= 0.8;
            kroll_i_local *= 0.8;
        }

        kpitch_d_local *= fighter.mach;
    }

    auto action = pid(err_roll, err_pitch, err_throttle,
                      kroll_p_local, kroll_i_local, kroll_d_local,
                      kpitch_p_local, kpitch_i_local, kpitch_d_local,
                      get_throttle_base(fighter, intent_mach));

    if (!crashing) {
        if (std::abs(err_roll_angle) > params_.max_roll_angle && std::abs(err_roll_angle) < deg2rad(180 - 25)) {
            action[1] = 0;
        }
    }

    if (fighter.mach < params_.low_speed_threshold) {
        action[3] = 1;
        if (fighter.mach < params_.stall_speed) {
            action[1] /= 10;
            action[0] /= 2;
        }
    }

    if (fighter.height < 3200 && fighter.pitch < -1.15 && fighter.mach > params_.high_speed_threshold) {
        action[3] = 0;
    }

    return norm_fc_output(action);
}

std::array<double, 4> StdFlightController::pid(
    double err_roll, double err_pitch, double err_throttle,
    double kroll_p, double kroll_i, double kroll_d,
    double kpitch_p, double kpitch_i, double kpitch_d,
    double throttle_base
) noexcept {
    std::array<double, 4> pid_output = {0, 0, 0, 1};

    sum_err_roll += err_roll * dt;
    double d_err_roll = (err_roll - last_err_roll) / dt;
    pid_output[0] = kroll_p * err_roll + kroll_d * d_err_roll;
    if (std::abs(err_roll) < params_.roll_integral_threshold) {
        pid_output[1] += kroll_i * sum_err_roll;
    }
    sum_err_roll = norm(sum_err_roll, -params_.roll_integral_clamp, params_.roll_integral_clamp);

    if (std::abs(err_pitch) < params_.pitch_integral_threshold) {
        if (err_pitch <= params_.pitch_integral_deadband && err_pitch >= -params_.pitch_integral_deadband) {
            sum_err_pitch = 0;
        } else {
            sum_err_pitch += err_pitch * dt;
        }
    } else {
        sum_err_pitch = 0;
    }

    double d_err_pitch = (err_pitch - last_err_pitch) / dt;
    pid_output[1] = kpitch_p * err_pitch + kpitch_d * d_err_pitch;
    if (std::abs(err_pitch) < params_.pitch_integral_threshold) {
        pid_output[1] += kpitch_i * sum_err_pitch;
    }

    sum_err_pitch = norm(sum_err_pitch, -params_.pitch_integral_clamp, params_.pitch_integral_clamp);

    sum_err_throttle += err_throttle;
    double d_err_throttle = (err_throttle - last_err_throttle);
    pid_output[3] = throttle_base + kthrottle_p_ * err_throttle +
                    kthrottle_i_ * sum_err_throttle + kthrottle_d_ * d_err_throttle;
    pid_output[3] = norm(pid_output[3], 0., params_.max_throttle);

    sum_err_throttle = norm(sum_err_throttle, -params_.throttle_integral_clamp, params_.throttle_integral_clamp);

    last_err_roll = err_roll;
    last_err_pitch = err_pitch;
    last_err_throttle = err_throttle;

    return pid_output;
}

double StdFlightController::get_throttle_base(const FighterState& fighter, double intent_mach) noexcept {
    double base = params_.throttle_base_value;

    if (fighter.height > params_.throttle_altitude_threshold) {
        base += params_.throttle_altitude_coefficient * ((fighter.height - params_.throttle_altitude_threshold) / params_.throttle_altitude_threshold);
    }

    if (intent_mach > params_.throttle_mach_threshold) {
        base += (intent_mach - params_.throttle_mach_threshold);
    }

    if (fighter.height < params_.throttle_altitude_limit || fighter.pitch > 0) {
        base += params_.throttle_pitch_coefficient * fighter.pitch / params_.throttle_pitch_divisor;
    }

    if (fighter.mach < params_.low_mach_throttle_threshold) {
        base = params_.max_throttle;
    }

    return base;
}

}
