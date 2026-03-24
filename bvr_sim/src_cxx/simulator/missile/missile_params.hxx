#pragma once

#include <memory>
#include <string>
#include "rubbish_can/interp_table.hxx"

namespace bvr_sim {

/// Generic missile parameter container for multi-model missile framework.
/// Replaces hardcoded MissileParameter in AIM120C.
/// Factory method get_missile_params() loads params from hardcoded tables or future config.
/// DEBUG: Added search_fov, search_range, search_start_range, track_gimbal_limit
struct MissileParams {
    // Physical parameters
    double m0;              // initial mass (kg)
    double dm;              // mass flow rate (kg/s)
    double thrust;          // thrust (N)
    double t_max;           // max thrust time (s)
    double t_thrust;        // actual thrust duration (s)
    double length;          // missile length (m)
    double diameter;        // missile diameter (m)
    double nyz_max;         // max lateral acceleration (g)
    double g;               // gravity (m/s^2)

    // Aerodynamic parameters
    std::shared_ptr<const InterpTable> cx_total_table;  // Mach -> Cx_total (no AOA compensation)
    double S_ref;           // reference area (m^2)
    double Rc;              // min climb radius (m, SI)
    double mach_min;        // minimum Mach number

    // Guidance parameters
    double K;               // proportional navigation gain
    double search_fov;      // search field of view (rad, converted)
    double search_range;    // search range (m, converted)
    double search_start_range;  // search start range threshold (m, converted)
    double track_gimbal_limit;  // track gimbal limit (rad, converted)

    // State machine parameters
    bool enable_search;     // enable search phase
    bool enable_track;      // enable track phase
    bool enable_loft;       // enable loft maneuver
    double loss_time_threshold;  // signal loss threshold (s)

    // ===== 静态工厂方法 =====
    static MissileParams get_missile_params(const std::string& missile_model);
};

} // namespace bvr_sim
