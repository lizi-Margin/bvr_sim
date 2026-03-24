#pragma once

#include "simulator/aircraft/fdm/base.hxx"
#include "simulator/param_store.hxx"
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

// ParamStore already brings in ::InterpTable via using ::InterpTable

/// Generic missile flight dynamics model.
/// Handles aerodynamics (Mach-indexed drag), kinematics (Euler integration),
/// and propulsion (thrust + mass burn).
/// Receives ny/nz acceleration commands via step() — applied directly.
///
/// Gravity convention: nz is the aerodynamic normal load factor (g-units).
/// Gravity (-g in NWU Z) is applied separately as a world-frame constant.
///
/// Lifetime contract: the ParamStore reference must outlive this object.
/// Satisfied when both are owned by the same Missile class.
class GenericMissileFDM : public BaseFDM {
public:
    explicit GenericMissileFDM(const ParamStore& params, double dt = 0.1) noexcept;

    void reset(const std::map<std::string, std::any>& initial_state) override;

    /// action keys:
    ///   "ny" (double) — lateral acceleration command (g-units)
    ///   "nz" (double) — longitudinal/normal acceleration command (g-units)
    void step(const std::map<std::string, double>& action) override;

    double get_current_mass()  const noexcept { return m_; }
    double get_elapsed_time()  const noexcept { return t_; }
    bool   is_thrusting()      const noexcept { return t_ < t_thrust_cached_; }

private:
    const ParamStore& params_;

    // Propulsion state
    double t_;               // elapsed time (s) — incremented at end of step()
    double m_;               // current mass (kg)
    double t_thrust_cached_; // cached from params (hot path)

    // Cached params (extracted once in _cache_params for hot path)
    double m0_, dm_, thrust_, S_ref_, mach_min_, nyz_max_, g_;

    void   _cache_params() noexcept;
    void   _update_propulsion(double dt_step) noexcept;
    double _compute_drag_accel() const noexcept;
    void   _integrate(double ny, double nz) noexcept;
};

} // namespace bvr_sim
