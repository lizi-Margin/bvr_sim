#include "mmodelA.hxx"
#include "../aircraft/base.hxx"
#include "../sense/base.hxx"
#include "../ground/base.hxx"
#include "../ground/aa.hxx"
#include "../simulator.hxx"
#include "support/support.hxx"
#include "c3utils/c3utils.hxx"
#include "resource_paths.hxx"
#include <cmath>
#include <algorithm>
#include <limits>
#include <map>

namespace bvr_sim {

using c3utils::linalg_norm;
using c3utils::get_mps;
using c3utils::feet_to_meters;
using c3utils::meters_to_nm;
using c3utils::norm_pi;
using c3utils::pi;
using c3utils::rad2deg;
using c3utils::Vector3;
// Note: velocity_to_euler is in bvr_sim namespace (from simulator.hxx), not c3utils

constexpr bool prevent_low_loft = false;

// ─── Parameter factory ────────────────────────────────────────────────────────

ParamStore MModelA::_make_params(const std::string& missile_model) noexcept {
    static const std::map<std::string, std::string> config_mapping = {
        {"AIM-9", "aim9m.json"},
        {"AIM-9M", "aim9m.json"},
        {"AIM-9M-Omni", "aim9m_omni.json"},
        {"AIM-120C", "aim120c_mmodela.json"},
        {"AIM-120C-MModelA", "aim120c_mmodela.json"},
        {"AIM-120C-MModelA-Poor", "aim120c_mmodela_poor.json"},
    };

    auto it = config_mapping.find(missile_model);
    if (it == config_mapping.end()) {
        colorful::printHONG("[MModelA] Unknown missile model: " + missile_model + ", returning empty ParamStore");
        return ParamStore{};
    }

    try {
        const auto path = resource_paths::get_resource_path("missile/mmodelA/" + it->second);
        return ParamStore::from_file(path.string());
    } catch (const std::exception& e) {
        colorful::printHONG("[MModelA] Failed to load params for " + missile_model + ": " + e.what());
        return ParamStore{};
    }
}

// ─── Constructor ──────────────────────────────────────────────────────────────

MModelA::MModelA(
    const std::string& uid,
    const std::string& missile_model,
    TeamColor color,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& friend_obj,
    const std::shared_ptr<SimulatedObject>& target,
    double dt
) noexcept
    : Missile(uid, missile_model, color, parent, friend_obj, target, dt),
      radar_pitch(0.0),
      radar_yaw(0.0),
      guide_cmd_valid(true),
      losstime(0.0),
      loss(false),
      _before_loss_real_last_known_target_pos{0.0, 0.0, 0.0},
      L_beta(std::nullopt),
      L_eps(std::nullopt),
      _dbeta_filtered(std::nullopt),
      params_(_make_params(missile_model)),   // params_ first
      fdm_(params_, dt),                      // fdm_ second (holds ref to params_)
      _search_started(false),
      _distance_pre(std::numeric_limits<double>::infinity()),
      _left_t(static_cast<int>(1.0 / dt))
{
    for (int i = 0; i < 20; ++i) _distance_increment.push_back(false);

    double init_pitch = 0.0, init_yaw = 0.0;

    if (parent->Type == SOT::Aircraft) {
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(parent);
        check(aircraft, "dynamic cast failed");
        init_pitch = aircraft->get_pitch();
        if (prevent_low_loft) {
            init_pitch = std::max(init_pitch, 0.0);
        }
        init_yaw   = aircraft->get_heading();
    } else if (parent->Type == SOT::AA) {
        auto aa = std::dynamic_pointer_cast<AA>(parent);
        check(aa, "dynamic cast failed");
        check(target->Type == SOT::Aircraft, "MModelA target must be Aircraft when fired from AA");
        auto target_aircraft = std::dynamic_pointer_cast<Aircraft>(target);
        check(target_aircraft, "dynamic cast failed");
        auto vel = aa->get_launch_velocity(target_aircraft);
        auto [roll_v, pitch_v, heading_v] = velocity_to_euler(vel);
        init_pitch = pitch_v;
        init_yaw   = heading_v;
        velocity   = vel;
    } else {
        check(false, "MModelA must be parented by an Aircraft or AA");
    }

    std::map<std::string, std::any> init_state;
    init_state["position"] = std::array<double,3>{position[0], position[1], position[2]};
    init_state["velocity"] = std::array<double,3>{velocity[0], velocity[1], velocity[2]};
    init_state["pitch"]    = double(init_pitch);
    init_state["yaw"]      = double(init_yaw);
    init_state["roll"]     = double(0.0);
    fdm_.reset(init_state);
}

bool MModelA::_can_track_from(const std::shared_ptr<SimulatedObject>& friend_) const noexcept {
    if (!friend_ || !target || friend_->Type != SOT::Aircraft) {
        return false;
    }

    auto aircraft = std::dynamic_pointer_cast<Aircraft>(friend_);
    if (!aircraft || !aircraft->is_alive || !aircraft->radar) {
        return false;
    }

    for (const auto& [locked_uid, _] : aircraft->radar->get_data()) {
        if (locked_uid == target->uid) {
            return true;
        }
    }

    return false;
}

bool MModelA::can_track_target() noexcept {
    if (!target) {
        radar_on = false;
        guide_cmd_valid = false;
        return false;
    }

    const bool enable_precise_cue = params_.get_bool_("enable_precise_cue");
    const bool enable_search = params_.get_bool_("enable_search");
    const bool enable_guide_cmd = params_.get_bool_("enable_guide_cmd");
    const bool enable_INS_guide = params_.get_bool_("enable_INS_guide");

    bool precise_cue = false;
    double elapsed = fdm_.get_elapsed_time();
    check(elapsed >= 0.0f, "get_elapsed_time() < 0.0f");
    if (enable_precise_cue && elapsed < 2 * dt) {
        precise_cue = true;
    }

    if (losstime > 0.1 && !radar_on) {
        if (!loss) {
            _before_loss_real_last_known_target_pos = last_known_target_pos;
            loss = true;
        }
        if (enable_INS_guide) {
            _loss_update_target_info();
        }
    } else {
        loss = false;
    }

    guide_cmd_valid = enable_guide_cmd && (_can_track_from(parent) || _can_track_from(friend_obj));

    const double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    Vector3 nose_vec = Vector3(velocity);
    if (nose_vec.get_module() > 1e-6 && distance > 1e-6) {
        Vector3 rel_vec(
            target->position[0] - position[0],
            target->position[1] - position[1],
            target->position[2] - position[2]
        );
        auto gba = nose_vec.normalize().get_rotate_angle_fix();
        rel_vec.rev_rotate_xyz_fix(gba[0], gba[1], gba[2]);
        auto angles = rel_vec.get_rotate_angle_fix();
        radar_pitch = angles[1];
        radar_yaw   = angles[2];
    } else {
        radar_pitch = 0.0;
        radar_yaw   = 0.0;
    }

    if (!_search_started) {
        const double est_distance = linalg_norm({
            last_known_target_pos[0] - position[0],
            last_known_target_pos[1] - position[1],
            last_known_target_pos[2] - position[2]
        });
        if (est_distance < params_.get_double_("search_start_range")) {
            _search_started = true;
        }
    }

    if (enable_search && _search_started && distance < params_.get_double_("search_range")) {
        auto heading = velocity;
        auto rel = std::array<double, 3>{
            target->position[0] - position[0],
            target->position[1] - position[1],
            target->position[2] - position[2]
        };
        const double heading_norm = linalg_norm(heading);
        const double denom = distance * heading_norm + 1e-8;
        const double dot_prod = heading[0] * rel[0] + heading[1] * rel[1] + heading[2] * rel[2];
        const double attack_angle = std::acos(std::clamp(dot_prod / denom, -1.0, 1.0));

        if (attack_angle < params_.get_double_("track_gimbal_limit")) {
            if (guide_cmd_valid) {
                radar_on = true;
            } else if (precise_cue) {
                radar_on = true;
            } else if (attack_angle < params_.get_double_("search_fov")) {
                radar_on = true;
            } else {
                Vector3 to_last_known(
                    last_known_target_pos[0] - position[0],
                    last_known_target_pos[1] - position[1],
                    last_known_target_pos[2] - position[2]
                );
                Vector3 to_target(rel[0], rel[1], rel[2]);
                const double search_angle = to_last_known.get_angle(to_target);
                radar_on = (search_angle < params_.get_double_("search_fov"));
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
    }

    losstime += dt;
    return false;
}

void MModelA::_loss_update_target_info() noexcept {
    if (!loss) {
        return;
    }

    const double t_max = params_.get_double_("t_max");
    const double time_factor = std::min({losstime, std::pow(losstime, 0.95), t_max / 6.0});
    last_known_target_pos[0] = _before_loss_real_last_known_target_pos[0] + time_factor * last_known_target_vel[0];
    last_known_target_pos[1] = _before_loss_real_last_known_target_pos[1] + time_factor * last_known_target_vel[1];
    last_known_target_pos[2] = _before_loss_real_last_known_target_pos[2] + time_factor * last_known_target_vel[2];
}

double MModelA::K_func(double range_to_target) const noexcept {
    const double elapsed = fdm_.get_elapsed_time();
    const double t_max = params_.get_double_("t_max");
    const double t_thrust = params_.get_double_("t_thrust") + dt;
    const double K = params_.get_double_("K");

    const double base_K = std::max(K * (t_max - elapsed) / t_max, 0.5);
    if (radar_on || elapsed < t_thrust) {
        return K;
    }

    (void)range_to_target;
    return base_K;
}

double MModelA::calculate_min_distance(
    const std::array<double, 3>& missile_pos,
    const std::array<double, 3>& missile_vel,
    const std::array<double, 3>& aircraft_pos,
    const std::array<double, 3>& aircraft_vel,
    double delta_t
) const noexcept {
    const double dx = aircraft_pos[0] - missile_pos[0];
    const double dy = aircraft_pos[1] - missile_pos[1];
    const double dz = aircraft_pos[2] - missile_pos[2];

    const double dvx = aircraft_vel[0] - missile_vel[0];
    const double dvy = aircraft_vel[1] - missile_vel[1];
    const double dvz = aircraft_vel[2] - missile_vel[2];

    const double a = dvx * dvx + dvy * dvy + dvz * dvz;
    if (a < 1e-12) {
        return std::sqrt(dx * dx + dy * dy + dz * dz);
    }

    const double dot = dx * dvx + dy * dvy + dz * dvz;
    const double t0 = -dot / a;

    double distance_sq = 0.0;
    if (t0 <= 0.0) {
        distance_sq = dx * dx + dy * dy + dz * dz;
    } else if (t0 >= delta_t) {
        const double dx_end = dx + dvx * delta_t;
        const double dy_end = dy + dvy * delta_t;
        const double dz_end = dz + dvz * delta_t;
        distance_sq = dx_end * dx_end + dy_end * dy_end + dz_end * dz_end;
    } else {
        distance_sq = (dx * dx + dy * dy + dz * dz) - (dot * dot) / a;
    }

    return std::sqrt(std::max(distance_sq, 0.0));
}

// ─── Step ─────────────────────────────────────────────────────────────────────

void MModelA::step() noexcept {
    if (!is_alive) return;
    if (!target)   return;

    update_target_info();

    // Use current (pre-step) position for termination checks
    double distance = linalg_norm({
        target->position[0] - position[0],
        target->position[1] - position[1],
        target->position[2] - position[2]
    });

    _distance_increment.push_back(distance > _distance_pre);
    _distance_pre = distance;

    double elapsed  = fdm_.get_elapsed_time();
    double speed    = fdm_.get_speed();
    double t_max    = params_.get_double_("t_max");
    double t_thrust = params_.get_double_("t_thrust");
    double v_min    = get_mps(params_.get_double_("mach_min"), position[2]);
    double Rc       = params_.get_double_("Rc");

    bool timeout             = elapsed > t_max;
    bool crash               = position[2] < 0.0;
    bool too_slow            = (elapsed > t_thrust && speed < v_min);
    bool farther_and_farther = (_distance_increment.size() == _distance_increment.max_size() &&
                                std::count(_distance_increment.begin(), _distance_increment.end(), true) >=
                                static_cast<int>(_distance_increment.max_size()));
    bool target_down         = !(target && target->is_alive);

    if (distance < Rc && target && target->is_alive) {
        if (target->Type == SOT::Aircraft) {
            auto aircraft = std::dynamic_pointer_cast<Aircraft>(target);
            check(aircraft, "[MModelA] dynamic cast failed");
            aircraft->hit();
        } else if (target->Type == SOT::GroundUnit) {
            auto ground = std::dynamic_pointer_cast<GroundUnit>(target);
            check(ground, "[MModelA] dynamic cast failed");
            if (ground->check_collision(position)) ground->hit();
            else ground->hit(10.0);
        }
        is_success = true;
        is_done    = true;
        log_done_reason = "hit";
    } else if (timeout || crash || too_slow || farther_and_farther || target_down) {
        is_success = false;
        is_done    = true;
        if (timeout)              log_done_reason = "timeout";
        else if (crash)           log_done_reason = "crash";
        else if (too_slow)        log_done_reason = "too_slow " + std::to_string(speed) + " < " + std::to_string(v_min);
        else if (farther_and_farther) log_done_reason = "farther_and_farther_away";
        else if (target_down)     log_done_reason = "target_down";
    } else {
        auto [cmd_beta, cmd_eps] = update_guidance();
        fdm_.step({{"ny", cmd_beta}, {"nz", cmd_eps}});

        // Sync FDM state into SimulatedObject base AFTER physics step
        auto fdm_pos = fdm_.get_position();
        auto fdm_vel = fdm_.get_velocity();
        position[0] = fdm_pos[0]; position[1] = fdm_pos[1]; position[2] = fdm_pos[2];
        velocity[0] = fdm_vel[0]; velocity[1] = fdm_vel[1]; velocity[2] = fdm_vel[2];
    }

    if (is_done) is_alive = false;
}

std::pair<double, double> MModelA::update_guidance() noexcept {
    const bool enable_INS_guide = params_.get_bool_("enable_INS_guide");
    if (loss && !enable_INS_guide) {
        return {0.0, 0.0};
    }

    const bool enable_angle_navigation = params_.get_bool_("enable_angle_navigation");

    const double x_t = last_known_target_pos[0];
    const double y_t = last_known_target_pos[1];
    const double z_t = last_known_target_pos[2];

    const double x_m = position[0];
    const double y_m = position[1];
    const double z_m = position[2];
    const double dx_m = velocity[0];
    const double dy_m = velocity[1];
    const double dz_m = velocity[2];
    const double v_m = linalg_norm(velocity);

    if (v_m < 1e-6) {
        radar_pitch = 0.0;
        radar_yaw = 0.0;
        return {0.0, 0.0};
    }

    const double elapsed = fdm_.get_elapsed_time();
    const double t_thrust = params_.get_double_("t_thrust") + dt;
    const double g = params_.get_double_("g");
    const double nyz_max = params_.get_double_("nyz_max");

    const double pitch_m = std::atan2(-dz_m, std::sqrt(dx_m * dx_m + dy_m * dy_m));
    const double climb_angle_m = -pitch_m;

    const double range_to_target = linalg_norm({x_m - x_t, y_m - y_t, z_t - z_m});
    const double beta = std::atan2(y_t - y_m, x_t - x_m);
    const double eps = std::atan2(z_t - z_m, linalg_norm(std::array<double, 2>{x_t - x_m, y_t - y_m}));

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

    if (params_.get_bool_("enable_loft") && !radar_on && elapsed < 4.0) {
        const double min_val = std::min(meters_to_nm(range_to_target), 10.0);
        if (rad2deg(fdm_.get_pitch()) < min_val) {
            deps = std::max(deps, 0.1);
        }
    }

    const double phi = std::atan2(dy_m, dx_m);
    // const double angle_error = norm_pi(phi - norm_pi(beta - pi));
    const double angle_error = norm_pi(beta - phi);

    double desired_dbeta = dbeta;
    if (radar_on && range_to_target < feet_to_meters(5000.0)) {
        desired_dbeta = dbeta;
    } else if (enable_angle_navigation && elapsed < t_thrust) {
        const double angle_blend_min = 0.0;
        const double angle_gain = 0.1;
        const double max_cmd_rate = 0.5;
        const double blend = std::max((t_thrust - elapsed) / t_thrust, angle_blend_min);
        double desired_dbeta_from_angle = angle_gain * -1.0 * angle_error;
        desired_dbeta_from_angle = std::clamp(desired_dbeta_from_angle, -max_cmd_rate, max_cmd_rate);
        desired_dbeta = blend * desired_dbeta_from_angle + (1.0 - blend) * dbeta;
    } else {
        desired_dbeta = dbeta;
    }

    double ny = K_func(range_to_target) * v_m / g * std::cos(climb_angle_m) * desired_dbeta;
    double nz = K_func(range_to_target) * v_m / g * deps + std::cos(climb_angle_m);

    ny = std::clamp(ny, -nyz_max, nyz_max);
    nz = std::clamp(nz, -nyz_max, nyz_max);

    (void)calculate_min_distance(position, velocity, last_known_target_pos, last_known_target_vel, dt);
    return {ny, nz};
}

std::array<double, 3> MModelA::get_rpy() const noexcept {
    return fdm_.get_rpy();
}

} // namespace bvr_sim
