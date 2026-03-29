#pragma once

#include "simulator/aircraft/fdm/base.hxx"
#include "simulator/param_store.hxx"
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

// ParamStore already brings in ::InterpTable via using ::InterpTable

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
    std::shared_ptr<InterpTable> n_available_table_;
    std::shared_ptr<InterpTable> n_cmd_rate_limit_table_;

    // Propulsion state
    double t_;               // elapsed time (s) — incremented at end of step()
    double m_;               // current mass (kg)
    double t_thrust_cached_; // cached from params (hot path)

    // Cached params (extracted once in _cache_params for hot path)
    double m0_, dm_, thrust_, S_ref_, mach_min_, g_;

    double ny_actual_;
    double nz_actual_;
    double dtheta_;
    double dphi_;

    void   _cache_params() noexcept;
    void   _update_propulsion(double dt_step) noexcept;
    double _compute_drag_force(double speed, double altitude) const noexcept;
    void   _integrate(double ny, double nz) noexcept;
};

} // namespace bvr_sim
