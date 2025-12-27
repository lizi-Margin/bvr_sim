#include "jsbsim_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include "funcs.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/colorful.hxx"
#include "rubbish_can/set_env.hxx"
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <any>
#include <stdlib.h>


namespace bvr_sim {

const static int jsb_debug_level = 0;

// using namespace c3utils;
using c3utils::pi;
using c3utils::deg2rad;
using c3utils::norm_pi;
using c3utils::rad2deg;
using c3utils::feet_to_meters;
using c3utils::meters_to_feet;
using c3utils::norm;

namespace Catalog {
    Property ic_long_gc_deg("ic/long-gc-deg", "", -180, 180);
    Property ic_lat_geod_deg("ic/lat-geod-deg", "", -90, 90);
    Property ic_h_sl_ft("ic/h-sl-ft", "", -1400, 85000);
    Property ic_psi_true_deg("ic/psi-true-deg", "", 0, 360);
    Property ic_u_fps("ic/u-fps", "", -2200, 2200);
    Property ic_v_fps("ic/v-fps", "", -2200, 2200);
    Property ic_w_fps("ic/w-fps", "", -2200, 2200);
    Property ic_p_rad_sec("ic/p-rad_sec", "", -2*pi, 2*pi);
    Property ic_q_rad_sec("ic/q-rad_sec", "", -2*pi, 2*pi);
    Property ic_r_rad_sec("ic/r-rad_sec", "", -2*pi, 2*pi);
    Property ic_roc_fpm("ic/roc-fpm", "");
    Property ic_terrain_elevation_ft("ic/terrain-elevation-ft", "");

    Property position_long_gc_deg("position/long-gc-deg", "", -180, 180);
    Property position_lat_geod_deg("position/lat-geod-deg", "", -90, 90);
    Property position_h_sl_meters("position/h-sl-meters", "");

    Property attitude_roll_rad("attitude/roll-rad", "", -pi, pi, "R");
    Property attitude_pitch_rad("attitude/pitch-rad", "", -0.5*pi, 0.5*pi, "R");
    Property attitude_heading_true_rad("attitude/heading-true-rad", "", 0, 2*pi, "R");

    // Property velocities_v_north_mps("velocities/v-north-mps", "", -2200, 2200, "R");
    // Property velocities_v_east_mps("velocities/v-east-mps", "", -2200, 2200, "R");
    // Property velocities_v_down_mps("velocities/v-down-mps", "", -2200, 2200, "R");
    Property velocities_v_north_fps("velocities/v-north-fps", "", -8000, 8000, "R");
    Property velocities_v_east_fps("velocities/v-east-fps", "", -8000, 8000, "R");
    Property velocities_v_down_fps("velocities/v-down-fps", "", -8000, 8000, "R");
    Property velocities_mach("velocities/mach", "", 0, 10, "R");

    Property fcs_aileron_cmd_norm("fcs/aileron-cmd-norm", "", -1, 1);
    Property fcs_elevator_cmd_norm("fcs/elevator-cmd-norm", "", -1, 1);
    Property fcs_rudder_cmd_norm("fcs/rudder-cmd-norm", "", -1, 1);
    Property fcs_throttle_cmd_norm("fcs/throttle-cmd-norm", "", 0, 1.0);
    Property fcs_mixture_cmd_norm("fcs/mixture-cmd-norm", "", 0, 1);

    void add_jsbsim_props(const std::vector<std::string>& props) noexcept {
        // for (const std::string& prop : props) {
        //     std::cout << "Not Implemented yet, can not add JSBSim property: " << prop << std::endl;
        // }
    }
}

static std::string get_root_dir() noexcept {
    std::string root_dir = std::string(__FILE__).substr(0, std::string(__FILE__).find_last_of("\\/"));
    for (auto& c : root_dir) {
        if (c == '\\') {
            c = '/';
        }
    }
    return root_dir;
}

JSBSimFDM::JSBSimFDM(double dt, const std::map<std::string, std::string>& kwargs) noexcept
    : BaseFDM(dt),
      JSBSim_dir(get_root_dir() + "/jsbsim"),
      aircraft_model("f16"),
      jsbsim_exec(nullptr),
      initialized(false),
      jsbsim_dt_max(0.025),
      jsbsim_inner_dt(dt),
      jsbsim_inner_steps(1),
      fc(dt),
      fc_delta_heading_filter({0.10, 0.0}),
      fc_delta_pitch_filter({0.10, 0.0}),
      mach(0.0),
      delta_heading(0.0),
      delta_pitch(0.0) {

    auto it = kwargs.find("aircraft_model");
    if (it != kwargs.end()) {
        aircraft_model = it->second;
        for (auto& c : aircraft_model) {
            c = std::tolower(c);
        }
    }

    if (this->dt > jsbsim_dt_max) {
        jsbsim_inner_steps = static_cast<int>(this->dt / jsbsim_dt_max) + 1;
        jsbsim_inner_dt = this->dt / jsbsim_inner_steps;
    }

    fc = StdFlightController(jsbsim_inner_dt);
    set_env("JSBSIM_DEBUG", std::to_string(jsb_debug_level));  // disable init log in COT
}

void JSBSimFDM::initialize_jsbsim() noexcept {
    set_env("JSBSIM_DEBUG", std::to_string(jsb_debug_level));  // disable init log in COT

    if (jsbsim_exec != nullptr) {
        jsbsim_exec->ResetToInitialConditions(0x2);
    }
    else {
        jsbsim_exec = std::make_unique<JSBSim::FGFDMExec>(nullptr, nullptr);

        const static std::string AircraftPath = "aircraft";
        const static std::string EnginePath = "engine";
        const static std::string SystemsPath = "systems";

        jsbsim_exec->SetRootDir(SGPath(JSBSim_dir));
        jsbsim_exec->SetDebugLevel(jsb_debug_level);
        jsbsim_exec->LoadModel(SGPath(AircraftPath), SGPath(EnginePath), SGPath(SystemsPath), aircraft_model, true);

        std::string props = jsbsim_exec->QueryPropertyCatalog("");
        std::vector<std::string> prop_list;
        std::stringstream ss(props);
        std::string line;
        while (std::getline(ss, line)) {
            prop_list.push_back(line);
        }
        Catalog::add_jsbsim_props(prop_list);

        // std::cout << "\033[31m" << "JSBSim dt: " << jsbsim_inner_dt << "\033[0m" << std::endl;
        SL::get().print("JSBSim dt: " + std::to_string(jsbsim_inner_dt));
        jsbsim_exec->Setdt(jsbsim_inner_dt);
    }
    

    clear_default_condition();
}

void JSBSimFDM::clear_default_condition() noexcept {
    set_property_value(Catalog::ic_long_gc_deg, 120.0);
    set_property_value(Catalog::ic_lat_geod_deg, 60.0);
    set_property_value(Catalog::ic_h_sl_ft, 20000);
    set_property_value(Catalog::ic_psi_true_deg, 0.0);
    set_property_value(Catalog::ic_u_fps, 800.0);
    set_property_value(Catalog::ic_v_fps, 0.0);
    set_property_value(Catalog::ic_w_fps, 0.0);
    // set_property_value(Catalog::ic_p_rad_sec, 0.0);
    // set_property_value(Catalog::ic_q_rad_sec, 0.0);
    // set_property_value(Catalog::ic_r_rad_sec, 0.0);
    // set_property_value(Catalog::ic_roc_fpm, 0.0);
    // set_property_value(Catalog::ic_terrain_elevation_ft, 12000);
}

void JSBSimFDM::reset(const std::map<std::string, std::any>& initial_state) {
    auto pos_any = initial_state.at("position");
    std::array<double, 3> pos_arr;
    if (pos_any.type() == typeid(std::array<double, 3>)) {
        pos_arr = std::any_cast<std::array<double, 3>>(pos_any);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset position with type " << pos_any.type().name() << std::endl;
        SL::get().print("[JSBSimFDM] Error: Cannot reset position with type " + std::string(pos_any.type().name()));
        pos_arr = {0.0, 0.0, 0.0};
    }

    auto vel_any = initial_state.at("velocity");
    std::array<double, 3> vel_arr;
    if (vel_any.type() == typeid(std::array<double, 3>)) {
        vel_arr = std::any_cast<std::array<double, 3>>(vel_any);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset velocity with type " << vel_any.type().name() << std::endl;
        SL::get().print("[JSBSimFDM] Error: Cannot reset velocity with type " + std::string(vel_any.type().name()));
        vel_arr = {100.0, 0.0, 0.0};
    }

    auto [lon, lat, alt] = NWU2LLA(pos_arr[0], pos_arr[1], pos_arr[2]);

    double yaw_val;
    if (c3u::linalg_norm(vel_arr) > 1e-6) {
        yaw_val = std::atan2(vel_arr[1], vel_arr[0]);
    } else {
        auto yaw_it = initial_state.find("yaw");
        if (yaw_it != initial_state.end()) {
            yaw_val = std::any_cast<double>(yaw_it->second);
        } else {
            std::cout << "[JSBSimFDM] Error: Cannot reset yaw with type " << yaw_it->second.type().name() << std::endl;
            SL::get().print("[JSBSimFDM] Error: Cannot reset yaw with type " + std::string(yaw_it->second.type().name()));
            yaw_val = 0.0;
        }
    }

    double speed = c3u::linalg_norm(vel_arr);

    double roll_val = 0.0;
    auto roll_it = initial_state.find("roll");
    if (roll_it != initial_state.end()) {
        roll_val = std::any_cast<double>(roll_it->second);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset roll with type " << roll_it->second.type().name() << std::endl;
        roll_val = 0.0;
    }

    double pitch_val = 0.0;
    auto pitch_it = initial_state.find("pitch");
    if (pitch_it != initial_state.end()) {
        pitch_val = std::any_cast<double>(pitch_it->second);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset pitch with type " << pitch_it->second.type().name() << std::endl;
        pitch_val = 0.0;
    }

    position = pos_arr;
    velocity = vel_arr;
    roll = roll_val;
    pitch = pitch_val;
    yaw = yaw_val;

    fc_delta_heading_filter.reset();
    fc_delta_pitch_filter.reset();
    initialize_jsbsim();
    set_jsbsim_initial_conditions(lon, lat, alt, speed, roll, pitch, yaw);

    auto propulsion = jsbsim_exec->GetPropulsion();
    int n_engines = propulsion->GetNumEngines();
    for (int i = 0; i < n_engines; ++i) {
        propulsion->GetEngine(i)->InitRunning();
    }
    propulsion->GetSteadyState();

    // std::cout << "Before Update: " << std::endl;
    // std::cout << "\033[32m" << "JSBSim " << aircraft_model
    //           << " reset at (" << lon << " E, " << lat << " N, N" << position[0]
    //           << ", W" << position[1] << ", U(true alt)" << alt << "m, "
    //           << meters_to_feet(alt) << "ft, " << rad2deg(yaw) << " deg)"
    //           << "\033[0m" << std::endl;

    update_properties();
    initialized = true;

    auto [lon2, lat2, alt2] = NWU2LLA(position[0], position[1], position[2]);
    std::stringstream ss;
    ss << "JSBSim " << aircraft_model << " reset at ";
    ss << std::fixed << std::setprecision(6);
    ss << lon2 << " E, " << lat2 << " N, N" << position[0]
              << ", W" << position[1] << ", U(true alt)" << alt2 << "m, "
              << meters_to_feet(alt2) << "ft, " << rad2deg(yaw) << " deg)"
              << std::endl;
              
    SL::get().print(ss.str());
}

double JSBSimFDM::get_mach() const noexcept {
    return mach;
}

void JSBSimFDM::run_jsbsim_step(const std::map<std::string, double>& action) noexcept {
    // double delta_heading_raw = norm(action.at("delta_heading"), -1, 1) * deg2rad(100);
    double delta_heading_raw = norm(action.at("delta_heading"), -1, 1) * deg2rad(80);
    double delta_heading_filt = fc_delta_heading_filter.update(delta_heading_raw);
    delta_heading = delta_heading_filt;

    double delta_pitch_raw = -norm(action.at("delta_altitude"), -1, 1) * deg2rad(80);
    double delta_pitch_filt = fc_delta_pitch_filter.update(delta_pitch_raw);
    delta_pitch = delta_pitch_filt;

    // if (position[2] < c3utils::feet_to_meters(20000)) {
    //     if (delta_pitch > 0) {
    //         delta_pitch = -deg2rad(80);
    //     }
    // }

    Vector3 fix_vec = get_heading_vec();
    fix_vec[2] = 0;
    fix_vec.rotate_zyx_self(0, delta_pitch, delta_heading);

    double mach_current = get_mach();
    double intent_mach = mach_current + action.at("delta_speed");
    // double intent_mach = 1.2;

    for (int step = 0; step < jsbsim_inner_steps; ++step) {
        if (terminate) {
            break;
        }

        mach_current = get_mach();

        Vector3 heading_vec = Vector3(1, 0, 0).rotate_zyx_self(roll, -pitch, -yaw);
        FighterState fake_fighter{
            roll,
            -pitch,
            -yaw,
            mach_current,
            -velocity[2],
            position[2],
            heading_vec
        };

        Vector3 fix_vec_neu = fix_vec;
        fix_vec_neu[1] = -fix_vec_neu[1];

        auto control_commands = fc.direct_LU_flight_controler(
            fake_fighter,
            fix_vec_neu,
            intent_mach,
            -1
        );

        set_jsbsim_controls(control_commands);

        bool result = jsbsim_exec->Run();
        if (!result) {
            colorful::printHONG("JSBSim step failed");
        }

        update_properties();
    }
}

void JSBSimFDM::step(const std::map<std::string, double>& action) {
    if (!initialized) {
        throw std::runtime_error("JSBSimFDM must be reset before stepping");
    }

    run_jsbsim_step(action);
}

void JSBSimFDM::set_property_value(const Property& prop, double value) noexcept {
    if (value < prop.min) {
        value = prop.min;
    } else if (value > prop.max) {
        value = prop.max;
    }

    jsbsim_exec->SetPropertyValue(prop.name_jsbsim, value);

    if (prop.access.find("W") != std::string::npos) {
        if (prop.update) {
            prop.update(this);
        }
    }
}

double JSBSimFDM::get_property_value(const Property& prop) noexcept {
    if (prop.access == "R") {
        if (prop.update) {
            prop.update(this);
        }
    }
    return jsbsim_exec->GetPropertyValue(prop.name_jsbsim);
}

std::vector<double> JSBSimFDM::get_property_values(const std::vector<Property*>& props) noexcept {
    std::vector<double> values;
    values.reserve(props.size());
    for (const auto* prop : props) {
        values.push_back(get_property_value(*prop));
    }
    return values;
}

void JSBSimFDM::set_jsbsim_controls(const std::array<double, 4>& controls) noexcept {
    set_property_value(Catalog::fcs_aileron_cmd_norm, controls[0]);
    set_property_value(Catalog::fcs_elevator_cmd_norm, controls[1]);
    set_property_value(Catalog::fcs_rudder_cmd_norm, controls[2]);
    set_property_value(Catalog::fcs_throttle_cmd_norm, controls[3]);
    set_property_value(Catalog::fcs_mixture_cmd_norm, controls[3]);
}

void JSBSimFDM::set_jsbsim_initial_conditions(double lon, double lat, double alt,
                                             double speed, double roll_val, double pitch_val, double yaw_val) noexcept {
    double alt_ft = meters_to_feet(alt);

    // double v_nwu_n = velocity[0];
    // double v_nwu_w = velocity[1];
    // double v_nwu_u = velocity[2];

    // double v_ned_n = v_nwu_n;
    // double v_ned_e = -v_nwu_w;
    // double v_ned_d = -v_nwu_u;

    // Vector3 v_ned_vector(v_ned_n, v_ned_e, v_ned_d);
    // Vector3 body_velocity_vector = v_ned_vector;
    // body_velocity_vector.rev_rotate_zyx_self(roll_val, pitch_val, yaw_val);

    // double u_body = body_velocity_vector[0];
    // double v_body = body_velocity_vector[1];
    // double w_body = body_velocity_vector[2];

    // double u_body_fps = meters_to_feet(u_body);
    double u_body_fps = meters_to_feet(speed);
    // double v_body_fps = meters_to_feet(v_body);
    // double w_body_fps = meters_to_feet(w_body);

    set_property_value(Catalog::ic_long_gc_deg, lon);
    set_property_value(Catalog::ic_lat_geod_deg, lat);
    set_property_value(Catalog::ic_h_sl_ft, alt_ft);
    set_property_value(Catalog::ic_psi_true_deg, rad2deg(-yaw_val));
    set_property_value(Catalog::ic_u_fps, u_body_fps);
    // set_property_value(Catalog::ic_v_fps, v_body_fps);
    // set_property_value(Catalog::ic_w_fps, w_body_fps);
    // set_property_value(Catalog::ic_p_rad_sec, 0.0);
    // set_property_value(Catalog::ic_q_rad_sec, 0.0);
    // set_property_value(Catalog::ic_r_rad_sec, 0.0);
    // set_property_value(Catalog::ic_roc_fpm, 0.0);
    // set_property_value(Catalog::ic_terrain_elevation_ft, 0);

    bool success = jsbsim_exec->RunIC();
    if (!success) {
        colorful::printHONG("JSBSim failed to initialize simulation conditions");
    }
}

void JSBSimFDM::update_properties() noexcept {
    std::vector<Property*> geodetic_props = {
        &Catalog::position_long_gc_deg,
        &Catalog::position_lat_geod_deg,
        &Catalog::position_h_sl_meters
    };
    auto geodetic = get_property_values(geodetic_props);
    double lon = geodetic[0];
    double lat = geodetic[1];
    double alt_m = geodetic[2];

    auto [n, w, u] = LLA2NWU(lon, lat, alt_m);
    // std::array<double, 3> old_position = position;
    position = {n, w, u};


    std::vector<Property*> velocity_props = {
        &Catalog::velocities_v_north_fps,
        &Catalog::velocities_v_east_fps,
        &Catalog::velocities_v_down_fps
    };
    auto velocity_ned_fps = get_property_values(velocity_props);
    double v_n_fps = velocity_ned_fps[0];
    double v_w_fps = -1 * velocity_ned_fps[1];
    double v_u_fps = -1 *velocity_ned_fps[2];
    velocity = {
        feet_to_meters(v_n_fps),
        feet_to_meters(v_w_fps),
        feet_to_meters(v_u_fps)
    };


    std::vector<Property*> posture_props = {
        &Catalog::attitude_roll_rad,
        &Catalog::attitude_pitch_rad,
        &Catalog::attitude_heading_true_rad
    };
    auto posture = get_property_values(posture_props);
    roll = posture[0];
    pitch = -posture[1];
    yaw = -norm_pi(posture[2]);

    // std::array<double, 3> vel_est;
    // vel_est[0] = (position[0] - old_position[0]) / jsbsim_inner_dt;
    // vel_est[1] = (position[1] - old_position[1]) / jsbsim_inner_dt;
    // vel_est[2] = (position[2] - old_position[2]) / jsbsim_inner_dt;

    // //print the est and true vel
    // SL::get().printf("[JSBSimFDM] vel_est: %f, %f, %f\n", vel_est[0], vel_est[1], vel_est[2]);
    // SL::get().printf("[JSBSimFDM] vel_true: %f, %f, %f\n", velocity[0], velocity[1], velocity[2]);

    mach = get_property_value(Catalog::velocities_mach);

    if (alt_m < 25) {
        SL::get().printf("[JSBSimFDM] Altitude below 25m, terminating simulation\n");
        terminate = true;
        return;
    }

    auto state = get_state_dict();
    for (const auto& [key, value] : state) {
        if (value.type() == typeid(double)) {
            double v = std::any_cast<double>(value);
            if (std::isnan(v)) {
                terminate = true;
                SL::get().printf("[JSBSimFDM] NaN (%s) value found for %s, terminating simulation\n", std::to_string(v).c_str(), key.c_str());
                break;
            }
        } else if (value.type() == typeid(std::array<double, 3>)) {
            auto arr = std::any_cast<std::array<double, 3>>(value);
            for (double v : arr) {
                if (std::isnan(v)) {
                    SL::get().printf("[JSBSimFDM] NaN (%s) value found for %s (std::array<double, 3>), terminating simulation\n", std::to_string(v).c_str(), key.c_str());
                    terminate = true;
                    break;
                }
            }
            if (terminate) break;
        }
    }
}

}
