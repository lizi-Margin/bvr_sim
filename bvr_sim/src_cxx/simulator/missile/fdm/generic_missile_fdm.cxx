#include "generic_missile_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>
#include <tuple>

namespace bvr_sim {

using c3utils::get_mps;
using c3utils::linalg_norm;
using c3utils::rad2deg;
namespace c3u = c3utils;

namespace {

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

}

GenericMissileFDM::GenericMissileFDM(const ParamStore& params, double dt) noexcept
    : BaseFDM(dt), params_(params),
      t_(0.0), m_(0.0), t_thrust_cached_(0.0),
      m0_(0.0), dm_(0.0), thrust_(0.0), S_ref_(0.0),
      mach_min_(0.0), nyz_max_(0.0), g_(9.81),
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
    nyz_max_        = params_.get_double_("nyz_max");
    g_              = params_.get_double_("g");
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

    t_ = 0.0;
    m_ = m0_;
    dtheta_ = 0.0;
    dphi_ = 0.0;
    terminate = false;
}

void GenericMissileFDM::step(const std::map<std::string, double>& action) {
    double ny = 0.0, nz = 0.0;
    if (action.count("ny")) ny = action.at("ny");
    if (action.count("nz")) nz = action.at("nz");

    ny = std::clamp(ny, -nyz_max_, nyz_max_);
    nz = std::clamp(nz, -nyz_max_, nyz_max_);

    _update_propulsion(dt);
    _integrate(ny, nz);

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

    double sound_speed = get_mps(1.0, altitude);
    double mach = speed / sound_speed;
    mach = std::max(mach, mach_min_);

    double cx = params_.get_interp_table_("cx_total_table")->interpolate(mach);
    double rho = c3u::get_standard_atmosphere_density(altitude);
    return 0.5 * rho * speed * speed * cx * S_ref_;
}

void GenericMissileFDM::_integrate(double ny, double nz) noexcept {
    double v = get_speed();
    if (v < 1e-6) {
        return;
    }

    double theta_0 = pitch;
    double phi_0 = yaw;
    auto pos_0 = position;
    double v_0 = v;

    auto derivatives = [&](const std::array<double, 3>& pos, double vel_mag, double theta, double phi)
        -> std::tuple<std::array<double, 3>, double, double, double> {
        std::array<double, 3> vel_vec = {
            vel_mag * std::cos(theta) * std::cos(phi),
            -vel_mag * std::cos(theta) * std::sin(phi),
            vel_mag * std::sin(theta)
        };

        double angle = c3u::deg2rad(-std::copysign(1.0, pos[2]) *
                                    signed_angle(vel_vec, {vel_vec[0], vel_vec[1], 0.0}));

        double drag = _compute_drag_force(vel_mag, pos[2]);
        double thrust = (t_ < t_thrust_cached_) ? thrust_ : 0.0;
        double gravity = m_ * g_ * std::sin(angle);

        double nx = (thrust - drag + gravity) / (m_ * g_);
        double dv = g_ * (nx - std::sin(theta));
        double dphi = g_ / vel_mag * (ny / std::cos(theta));
        double dtheta = g_ / vel_mag * (nz - std::cos(theta));

        return {vel_vec, dv, dphi, dtheta};
    };

    auto [vel_k1, dv_k1, dphi_k1, dtheta_k1] = derivatives(pos_0, v_0, theta_0, phi_0);

    auto pos_k2 = std::array<double, 3>{
        pos_0[0] + 0.5 * dt * vel_k1[0],
        pos_0[1] + 0.5 * dt * vel_k1[1],
        pos_0[2] + 0.5 * dt * vel_k1[2]
    };
    double v_k2 = v_0 + 0.5 * dt * dv_k1;
    double theta_k2 = theta_0 + 0.5 * dt * dtheta_k1;
    double phi_k2 = phi_0 + 0.5 * dt * dphi_k1;

    auto [vel_k2, dv_k2, dphi_k2, dtheta_k2] = derivatives(pos_k2, v_k2, theta_k2, phi_k2);

    auto pos_k3 = std::array<double, 3>{
        pos_0[0] + 0.5 * dt * vel_k2[0],
        pos_0[1] + 0.5 * dt * vel_k2[1],
        pos_0[2] + 0.5 * dt * vel_k2[2]
    };
    double v_k3 = v_0 + 0.5 * dt * dv_k2;
    double theta_k3 = theta_0 + 0.5 * dt * dtheta_k2;
    double phi_k3 = phi_0 + 0.5 * dt * dphi_k2;

    auto [vel_k3, dv_k3, dphi_k3, dtheta_k3] = derivatives(pos_k3, v_k3, theta_k3, phi_k3);

    auto pos_k4 = std::array<double, 3>{
        pos_0[0] + dt * vel_k3[0],
        pos_0[1] + dt * vel_k3[1],
        pos_0[2] + dt * vel_k3[2]
    };
    double v_k4 = v_0 + dt * dv_k3;
    double theta_k4 = theta_0 + dt * dtheta_k3;
    double phi_k4 = phi_0 + dt * dphi_k3;

    auto [vel_k4, dv_k4, dphi_k4, dtheta_k4] = derivatives(pos_k4, v_k4, theta_k4, phi_k4);

    position[0] = pos_0[0] + (dt / 6.0) * (vel_k1[0] + 2.0 * vel_k2[0] + 2.0 * vel_k3[0] + vel_k4[0]);
    position[1] = pos_0[1] + (dt / 6.0) * (vel_k1[1] + 2.0 * vel_k2[1] + 2.0 * vel_k3[1] + vel_k4[1]);
    position[2] = pos_0[2] + (dt / 6.0) * (vel_k1[2] + 2.0 * vel_k2[2] + 2.0 * vel_k3[2] + vel_k4[2]);

    double v_new = v_0 + (dt / 6.0) * (dv_k1 + 2.0 * dv_k2 + 2.0 * dv_k3 + dv_k4);
    double theta_new = theta_0 + (dt / 6.0) * (dtheta_k1 + 2.0 * dtheta_k2 + 2.0 * dtheta_k3 + dtheta_k4);
    double phi_new = phi_0 + (dt / 6.0) * (dphi_k1 + 2.0 * dphi_k2 + 2.0 * dphi_k3 + dphi_k4);

    dphi_ = (phi_new - phi_0) / dt;
    dtheta_ = (theta_new - theta_0) / dt;

    velocity[0] = v_new * std::cos(theta_new) * std::cos(phi_new);
    velocity[1] = -v_new * std::cos(theta_new) * std::sin(phi_new);
    velocity[2] = v_new * std::sin(theta_new);

    roll = 0.0;
    pitch = theta_new;
    yaw = phi_new;
}

} // namespace bvr_sim
