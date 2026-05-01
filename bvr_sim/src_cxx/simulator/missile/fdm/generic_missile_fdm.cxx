#include "generic_missile_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>
#include <tuple>

namespace bvr_sim {

using c3utils::get_mps;
using c3utils::get_mach;
using c3utils::linalg_norm;
using c3utils::Vector3;
namespace c3u = c3utils;

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

GenericMissileFDM::GenericMissileFDM(const ParamStore& params, double dt) noexcept
    : FDM_API(dt), params_(params),
      t_(0.0), m_(0.0), t_thrust_cached_(0.0),
      m0_(0.0), dm_(0.0), thrust_(0.0), S_ref_(0.0),
      mach_min_(0.0), g_(9.81),
      ny_actual_(0.0), nz_actual_(0.0),
      dtheta_(0.0), dphi_(0.0)
{
    _cache_params();
    m_ = m0_;
}

void GenericMissileFDM::_cache_params() noexcept {
    m0_             = params_.get_double_("m0");
    dm_             = params_.get_double_("dm");
    thrust_         = params_.get_double_("thrust");
    t_thrust_cached_= params_.get_double_("t_thrust") + dt;
    S_ref_          = params_.get_double_("S_ref");
    mach_min_       = params_.get_double_("mach_min");
    g_              = params_.get_double_("g");
    n_available_table_ = params_.get_interp_table_("n_available_table");
    n_cmd_rate_limit_table_ = params_.get_interp_table_("n_cmd_rate_limit_table");
}

void GenericMissileFDM::reset(const std::map<std::string, std::any>& initial_state) {
    if (initial_state.count("position"))
        position = std::any_cast<std::array<double,3>>(initial_state.at("position"));
    if (initial_state.count("velocity"))
        velocity = std::any_cast<std::array<double,3>>(initial_state.at("velocity"));
    if (initial_state.count("pitch"))
        pitch = std::any_cast<double>(initial_state.at("pitch"));
    if (initial_state.count("yaw"))
        yaw = std::any_cast<double>(initial_state.at("yaw"));
    if (initial_state.count("roll"))
        roll = std::any_cast<double>(initial_state.at("roll"));

    if (linalg_norm(velocity) > kMinSpeed) {
        auto rpy = velocity_to_rpy_nwu(velocity);
        roll = rpy[0];
        pitch = rpy[1];
        yaw = rpy[2];
    }

    t_ = 0.0;
    m_ = m0_;
    ny_actual_ = 0.0;
    nz_actual_ = 0.0;
    dtheta_ = 0.0;
    dphi_ = 0.0;
}

void GenericMissileFDM::step(const std::map<std::string, double>& action) {
    double ny_cmd = 0.0, nz_cmd = 0.0;
    if (action.count("ny")) ny_cmd = action.at("ny");
    if (action.count("nz")) nz_cmd = action.at("nz");

    const double mach = std::max(get_mach(get_speed(), position[2]), mach_min_);
    const double n_available = std::max(0.0, n_available_table_->interpolate(mach));
    const double n_rate_limit = std::max(0.0, n_cmd_rate_limit_table_->interpolate(mach));
    const double gravity_bias = std::cos(pitch);

    double ny_target = ny_cmd;
    double nz_target = nz_cmd;
    const double n_lat = ny_target;
    const double n_ver = nz_target - gravity_bias;
    const double n_cmd_mag = std::sqrt(n_lat * n_lat + n_ver * n_ver);
    if (n_cmd_mag > n_available && n_cmd_mag > 1e-8) {
        const double scale = n_available / n_cmd_mag;
        ny_target = n_lat * scale;
        nz_target = n_ver * scale + gravity_bias;
    }

    double n_act_lat = ny_actual_;
    double n_act_ver = nz_actual_ - gravity_bias;
    const double dn_lat = ny_target - ny_actual_;
    const double dn_ver = (nz_target - gravity_bias) - n_act_ver;
    const double dn_mag = std::sqrt(dn_lat * dn_lat + dn_ver * dn_ver);
    if (dn_mag > 1e-8) {
        const double scale = std::min(1.0, n_rate_limit * dt / dn_mag);
        n_act_lat += dn_lat * scale;
        n_act_ver += dn_ver * scale;
    }

    ny_actual_ = n_act_lat;
    nz_actual_ = n_act_ver + gravity_bias;

    _update_propulsion(dt);
    _integrate(ny_actual_, nz_actual_);

    t_ += dt;  // increment AFTER physics (consistent with original MModelA _t += dt at step start)
}

void GenericMissileFDM::_update_propulsion(double dt_step) noexcept {
    if (t_ < t_thrust_cached_) {
        m_ = std::max(m_ - dm_ * dt_step, m0_ - dm_ * t_thrust_cached_);
    }
}

double GenericMissileFDM::_compute_drag_force(double speed, double altitude) const noexcept {
    if (speed < 1e-6) {
        return 0.0;
    }

    const double mach = std::max(get_mach(speed, altitude), mach_min_);
    double cx = params_.get_interp_table_("cx_total_table")->interpolate(mach);
    double rho = c3u::get_standard_atmosphere_density(altitude);
    return 0.5 * rho * speed * speed * cx * S_ref_;
}

void GenericMissileFDM::_integrate(double ny, double nz) noexcept {
    double v = get_speed();
    if (v < kMinSpeed) {
        return;
    }

    auto pos_0 = position;
    auto vel_0 = velocity;
    const auto rpy_0 = velocity_to_rpy_nwu(vel_0);
    const double theta_0 = rpy_0[1];
    const double phi_0 = rpy_0[2];

    auto derivatives = [&](const std::array<double, 3>& pos, const std::array<double, 3>& vel)
        -> std::tuple<std::array<double, 3>, std::array<double, 3>> {
        const double speed = linalg_norm(vel);
        if (speed < kMinSpeed) {
            return {vel, {0.0, 0.0, 0.0}};
        }

        const std::array<double, 3> forward = scale_vec(vel, 1.0 / speed);
        const auto rpy = velocity_to_rpy_nwu(vel);
        const double theta = rpy[1];
        const double phi = rpy[2];

        auto side = Vector3(0.0, 1.0, 0.0).rotate_zyx_self(0.0, theta, phi).get_list();
        auto normal_up = Vector3(0.0, 0.0, 1.0).rotate_zyx_self(0.0, theta, phi).get_list();

        double drag = _compute_drag_force(speed, pos[2]);
        double thrust = (t_ < t_thrust_cached_) ? thrust_ : 0.0;
        const double axial_accel = (thrust - drag) / m_;

        std::array<double, 3> accel = scale_vec(forward, axial_accel);
        accel = add_scaled_vec(accel, side, g_ * ny);
        accel = add_scaled_vec(accel, normal_up, g_ * nz);
        accel = add_scaled_vec(accel, kGravityNwu, g_);

        return {vel, accel};
    };

    auto [dpos_k1, dvel_k1] = derivatives(pos_0, vel_0);

    auto pos_k2 = add_scaled_vec(pos_0, dpos_k1, 0.5 * dt);
    auto vel_k2 = add_scaled_vec(vel_0, dvel_k1, 0.5 * dt);

    auto [dpos_k2, dvel_k2] = derivatives(pos_k2, vel_k2);

    auto pos_k3 = add_scaled_vec(pos_0, dpos_k2, 0.5 * dt);
    auto vel_k3 = add_scaled_vec(vel_0, dvel_k2, 0.5 * dt);

    auto [dpos_k3, dvel_k3] = derivatives(pos_k3, vel_k3);

    auto pos_k4 = add_scaled_vec(pos_0, dpos_k3, dt);
    auto vel_k4 = add_scaled_vec(vel_0, dvel_k3, dt);

    auto [dpos_k4, dvel_k4] = derivatives(pos_k4, vel_k4);

    for (size_t i = 0; i < 3; ++i) {
        position[i] = pos_0[i] + (dt / 6.0) *
            (dpos_k1[i] + 2.0 * dpos_k2[i] + 2.0 * dpos_k3[i] + dpos_k4[i]);
        velocity[i] = vel_0[i] + (dt / 6.0) *
            (dvel_k1[i] + 2.0 * dvel_k2[i] + 2.0 * dvel_k3[i] + dvel_k4[i]);
    }

    const auto rpy_new = velocity_to_rpy_nwu(velocity);
    dphi_ = normalize_angle(rpy_new[2] - phi_0) / dt;
    dtheta_ = normalize_angle(rpy_new[1] - theta_0) / dt;

    roll = rpy_new[0];
    pitch = rpy_new[1];
    yaw = rpy_new[2];
}

} // namespace bvr_sim
