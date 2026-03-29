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

using c3utils::linalg_norm;
using c3utils::get_mps;
// Note: velocity_to_euler is in bvr_sim namespace (from simulator.hxx), not c3utils

// ─── Parameter factory ────────────────────────────────────────────────────────

ParamStore MModelA::_make_params(const std::string& missile_model) noexcept {
    if (missile_model == "AIM-120C7" || missile_model == "AIM-120C" ||
        missile_model == "AIM-120C5" || missile_model == "AIM-120") {

        const std::string json_str = R"({
            "doubles": {
                "m0":                    161.48,
                "dm":                    6.41,
                "thrust":                16325.0,
                "t_thrust":              8.0,
                "t_max":                 300.0,
                "S_ref":                 0.0248719,
                "mach_min":              0.8,
                "nyz_max":               100.0,
                "g":                     9.81,
                "Rc":                    152.4,
                "K":                     3.0,
                "search_fov":            0.349066,
                "search_range":          27780.0,
                "search_start_range":    18520.0,
                "track_gimbal_limit":    1.5708,
                "loss_time_threshold":   1.0
            },
            "strings": {
                "enable_search": "true",
                "enable_track":  "true",
                "enable_loft":   "false"
            },
            "tables": {
                "cx_total_table": {
                    "x": [0.0,  0.2,   0.4,   0.6,   0.8,   1.0,   1.2,   1.4,
                          1.6,  1.8,   2.0,   2.2,   2.4,   2.6,   2.8,   3.0,
                          3.2,  3.4,   3.6,   3.8,   4.0,   4.2,   4.4,   4.6,
                          4.8,  5.0],
                    "y": [0.468, 0.468, 0.468, 0.468, 0.479, 0.751, 0.88,  0.8572,
                          0.8132,0.7645,0.7205,0.6808,0.6447,0.6119,0.582, 0.5545,
                          0.5292,0.5057,0.4838,0.4633,0.4439,0.4256,0.4083,0.3921,
                          0.377, 0.364]
                }
            }
        })";
        return ParamStore::from_string(json_str);
    }
    if (missile_model == "AIM-9M" || missile_model == "AIM9M") {
        const std::string json_str = R"({
            "doubles": {
                "m0":                    84.0,
                "dm":                    6.0,
                "thrust":                7063.2,
                "t_thrust":              5.0,
                "t_max":                 180.0,
                "S_ref":                 0.0126677,
                "mach_min":              0.8,
                "nyz_max":               60.0,
                "g":                     9.81,
                "Rc":                    152.4,
                "K":                     5.0,
                "search_fov":            0.349066,
                "search_range":          27780.0,
                "search_start_range":    18520.0,
                "track_gimbal_limit":    1.5708,
                "loss_time_threshold":   1.0
            },
            "strings": {
                "enable_search": "true",
                "enable_track":  "true",
                "enable_loft":   "false"
            },
            "tables": {
                "cx_total_table": {
                    "x": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2, 1.4, 1.6, 1.8, 2.0, 2.2, 2.4, 2.6, 2.8, 3.0, 3.2, 3.4, 3.6, 3.8, 4.0, 4.2, 4.4, 4.6, 4.8, 5.0],
                    "y": [0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5]
                }
            }
        })";
        return ParamStore::from_string(json_str);
    }
    colorful::printHONG("[MModelA] Unknown missile model: " + missile_model + ", returning empty ParamStore");
    return ParamStore{};
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
      params_(_make_params(missile_model)),   // params_ first
      fdm_(params_, dt),                      // fdm_ second (holds ref to params_)
      radar_pitch(0.0),
      radar_yaw(0.0),
      guide_cmd_valid(true),
      losstime(0.0),
      loss(false),
      _search_started(false),
      _distance_pre(std::numeric_limits<double>::infinity()),
      _left_t(static_cast<int>(1.0 / dt)),
      _before_loss_real_last_known_target_pos{0.0, 0.0, 0.0}
{
    for (int i = 0; i < 20; ++i) _distance_increment.push_back(false);

    double init_pitch = 0.0, init_yaw = 0.0;

    if (parent->Type == SOT::Aircraft) {
        auto aircraft = std::dynamic_pointer_cast<Aircraft>(parent);
        check(aircraft, "dynamic cast failed");
        init_pitch = aircraft->get_pitch();
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
    init_state["pitch"]    = double(-init_pitch);
    init_state["yaw"]      = double(-init_yaw);
    init_state["roll"]     = double(0.0);
    fdm_.reset(init_state);
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
    // TODO: Implement proportional navigation guidance
    return {0.0, 0.0};
}

} // namespace bvr_sim
