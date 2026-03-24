#include "generic_missile_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using c3utils::get_mps;
using c3utils::linalg_norm;

GenericMissileFDM::GenericMissileFDM(const ParamStore& params, double dt) noexcept
    : BaseFDM(dt), params_(params),
      t_(0.0), m_(0.0), t_thrust_cached_(0.0),
      m0_(0.0), dm_(0.0), thrust_(0.0), S_ref_(0.0),
      mach_min_(0.0), nyz_max_(0.0), g_(9.81)
{
    _cache_params();
    m_ = m0_;
}

void GenericMissileFDM::_cache_params() noexcept {
    m0_             = params_.get_double_("m0");
    dm_             = params_.get_double_("dm");
    thrust_         = params_.get_double_("thrust");
    t_thrust_cached_= params_.get_double_("t_thrust");
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

double GenericMissileFDM::_compute_drag_accel() const noexcept {
    double speed = get_speed();
    if (speed < 1e-6) return 0.0;

    double alt = position[2];
    double sound_speed = get_mps(1.0, alt);
    double mach = speed / sound_speed;
    mach = std::max(mach, mach_min_);

    double cx = params_.get_interp_table_("cx_total_table")->interpolate(mach);

    double rho = 1.225 * std::exp(-alt / 9300.0);
    double drag_force = 0.5 * rho * speed * speed * cx * S_ref_;
    return drag_force / m_;
}

void GenericMissileFDM::_integrate(double ny, double nz) noexcept {
    double speed = get_speed();
    if (speed < 1e-6) return;

    double cos_pitch = std::cos(pitch);
    double sin_pitch = std::sin(pitch);
    double cos_yaw   = std::cos(yaw);
    double sin_yaw   = std::sin(yaw);

    // Body-axis unit vectors (NWU frame)
    // Forward (longitudinal)
    std::array<double,3> fwd = {cos_pitch * cos_yaw, cos_pitch * sin_yaw, -sin_pitch};
    // Lateral (y-body, 90° from fwd in horizontal plane)
    std::array<double,3> lat = {-sin_yaw, cos_yaw, 0.0};
    // Normal (z-body = cross(fwd, lat))
    std::array<double,3> nrm = {sin_pitch * cos_yaw, sin_pitch * sin_yaw, cos_pitch};

    double thrust_acc = (t_ < t_thrust_cached_) ? thrust_ / m_ : 0.0;
    double drag_acc   = _compute_drag_accel();

    // Aerodynamic acceleration (body frame contributions → world frame)
    // ny/nz are aerodynamic load factors (g-units); gravity added separately below
    std::array<double,3> aero_accel = {
        fwd[0] * (thrust_acc - drag_acc) + lat[0] * (ny * g_) + nrm[0] * (nz * g_),
        fwd[1] * (thrust_acc - drag_acc) + lat[1] * (ny * g_) + nrm[1] * (nz * g_),
        fwd[2] * (thrust_acc - drag_acc) + lat[2] * (ny * g_) + nrm[2] * (nz * g_)
    };

    // Gravity: constant world-frame force (NWU: -Z is down)
    velocity[0] += (aero_accel[0])       * dt;
    velocity[1] += (aero_accel[1])       * dt;
    velocity[2] += (aero_accel[2] - g_)  * dt;  // gravity acts in -Z (NWU)

    position[0] += velocity[0] * dt;
    position[1] += velocity[1] * dt;
    position[2] += velocity[2] * dt;

    // Update attitude from velocity direction
    double vspeed = linalg_norm(velocity);
    if (vspeed > 1e-6) {
        yaw   = std::atan2(velocity[1], velocity[0]);
        pitch = std::asin(-velocity[2] / vspeed);
    }
}

} // namespace bvr_sim
