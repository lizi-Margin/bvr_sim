#pragma once

#include "base.hxx"
#include "../fc/fc_old.hxx"
#include "rubbish_can/filter.hxx"
#include "extern/jsbsim/src/FGFDMExec.h"
#include "extern/jsbsim/src/models/FGPropulsion.h"
#include "extern/jsbsim/src/simgear/misc/sg_path.hxx"
#include <string>
#include <memory>
#include <tuple>
#include <functional>

namespace bvr_sim {

std::tuple<double, double, double> NWU2LLA(double north, double west, double up) noexcept;
std::tuple<double, double, double> LLA2NWU(double lon, double lat, double alt) noexcept;

struct Property {
    std::string name_jsbsim;
    std::string description;
    double min;
    double max;
    std::string access;
    bool clipped;
    std::function<void(class JSBSimFDM*)> update;

    Property(const std::string& name_jsbsim_,
             const std::string& description_ = "",
             double min_ = -std::numeric_limits<double>::infinity(),
             double max_ = std::numeric_limits<double>::infinity(),
             const std::string& access_ = "RW",
             bool clipped_ = true,
             std::function<void(JSBSimFDM*)> update_ = nullptr) noexcept
        : name_jsbsim(name_jsbsim_),
          description(description_),
          min(min_),
          max(max_),
          access(access_),
          clipped(clipped_),
          update(update_) {}
};

namespace Catalog {
    extern Property ic_long_gc_deg;
    extern Property ic_lat_geod_deg;
    extern Property ic_h_sl_ft;
    extern Property ic_psi_true_deg;
    extern Property ic_u_fps;
    extern Property ic_v_fps;
    extern Property ic_w_fps;
    extern Property ic_p_rad_sec;
    extern Property ic_q_rad_sec;
    extern Property ic_r_rad_sec;
    extern Property ic_roc_fpm;
    extern Property ic_terrain_elevation_ft;

    extern Property position_long_gc_deg;
    extern Property position_lat_geod_deg;
    extern Property position_h_sl_meters;

    extern Property attitude_roll_rad;
    extern Property attitude_pitch_rad;
    extern Property attitude_heading_true_rad;

    // extern Property velocities_v_north_mps;
    // extern Property velocities_v_east_mps;
    // extern Property velocities_v_down_mps;
    extern Property velocities_v_north_fps;
    extern Property velocities_v_east_fps;
    extern Property velocities_v_down_fps;
    extern Property velocities_mach;

    extern Property fcs_aileron_cmd_norm;
    extern Property fcs_elevator_cmd_norm;
    extern Property fcs_rudder_cmd_norm;
    extern Property fcs_throttle_cmd_norm;
    extern Property fcs_mixture_cmd_norm;

    void add_jsbsim_props(const std::vector<std::string>& props) noexcept;
}

class JSBSimFDM : public BaseFDM {
private:
    std::string JSBSim_dir;
    std::string aircraft_model;

    std::unique_ptr<JSBSim::FGFDMExec> jsbsim_exec;
    bool initialized;

    double jsbsim_dt_max;
    double jsbsim_inner_dt;
    int jsbsim_inner_steps;

    StdFlightController fc;
    SimpleScalarFilter fc_delta_heading_filter;
    SimpleScalarFilter fc_delta_pitch_filter;

    double mach;
    double delta_heading;
    double delta_pitch;

public:
    explicit JSBSimFDM(double dt = 0.1, const std::map<std::string, std::string>& kwargs = {}) noexcept;

    ~JSBSimFDM() noexcept override = default;

    void reset(const std::map<std::string, std::any>& initial_state) override;

    void step(const std::map<std::string, double>& action) override;

    double get_mach() const noexcept;

    void set_property_value(const Property& prop, double value) noexcept;

    double get_property_value(const Property& prop) noexcept;

    std::vector<double> get_property_values(const std::vector<Property*>& props) noexcept;

private:
    void initialize_jsbsim() noexcept;

    void clear_default_condition() noexcept;

    void run_jsbsim_step(const std::map<std::string, double>& action) noexcept;

    void set_jsbsim_controls(const std::array<double, 4>& controls) noexcept;

    void set_jsbsim_initial_conditions(double lon, double lat, double alt,
                                      double speed, double roll, double pitch, double yaw) noexcept;

    void update_properties() noexcept;
};

}
