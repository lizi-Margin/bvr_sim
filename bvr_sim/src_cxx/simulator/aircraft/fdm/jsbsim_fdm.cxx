#include "jsbsim_fdm.hxx"
#include "c3utils/c3utils.hxx"
#include "funcs.hxx"
#include "support/SL.hxx"
#include "support/colorful.hxx"
#include "support/set_env.hxx"
#include "simulator.hxx"
#include "vector.hxx"
#include <array>
#include <cmath>
#include <iostream>
#include <stdexcept>
#include <sstream>
#include <any>
#include <stdlib.h>
#include <string>
#include <filesystem>
#include <algorithm>
#include <optional>
#include <fstream>
#include "FGFCS.h"
#include "input_output/FGLog.h"
#include "resource_paths.hxx"
#include "simulator/aircraft/catalog.hxx"

namespace bvr_sim {

namespace {
std::string fdm_source_model(const std::string& model) {
    const auto& definitions=aircraft_definitions();
    auto entry=definitions.find(model);
    return entry==definitions.end() ? model : entry->second.fdm_model;
}
}

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
    Property ic_psi_true_deg("ic/psi-true-deg", "", -36000, 36000);
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
    // Property fcs_g_load_command("fcs/g-load-command", "", -2.0, 8.0);
    Property fcs_rudder_cmd_norm("fcs/rudder-cmd-norm", "", -1, 1);
    Property fcs_throttle_cmd_norm("fcs/throttle-cmd-norm", "", 0, 1.0);
    Property fcs_mixture_cmd_norm("fcs/mixture-cmd-norm", "", 0, 1);

    Property propulsion_set_running("propulsion/set-running", "", -1.0, 10.0, "W", false);

    void add_jsbsim_props(const std::vector<std::string>& props) noexcept {
        // for (const std::string& prop : props) {
        //     std::cout << "Not Implemented yet, can not add JSBSim property: " << prop << std::endl;
        // }
    }
}

JSBSimFDM::JSBSimFDM(double dt, const std::map<std::string, std::string>& kwargs)
    : AircraftFDM(dt),
      aircraft_model("F16"),
      jsbsim_exec(nullptr),
      initialized(false),
    //   jsbsim_dt_max(0.025),
      jsbsim_dt_max(0.02),
      jsbsim_inner_dt(dt),
      jsbsim_inner_steps(1),
      fc(dt, aircraft_model),
      fc_delta_heading_filter({0.25, 0.0}),
      fc_delta_pitch_filter({0.25, 0.0}),
      mach(0.0),
      delta_heading(0.0),
      delta_pitch(0.0),
      fix_vec(std::array<double, 3>{1.0, 0.0, 0.0}),
      _nav_point_uuid(SimulatedObject::get_new_uuid())
{
    auto it = kwargs.find("aircraft_model");
    if (it != kwargs.end()) {
        aircraft_model = it->second;
        const bool imported=std::filesystem::is_regular_file(resource_paths::get_resource_path("aircraft/"+fdm_source_model(aircraft_model)+"/fdm.xml"));
        fc = StdFlightController(jsbsim_inner_dt, imported ? "F16" : aircraft_model);
        if(imported)SL::optional().print("Imported JSBSim aircraft uses approximate F16 host flight controller: "+aircraft_model);
    }

    if (this->dt > jsbsim_dt_max) {
        jsbsim_inner_steps = static_cast<int>(this->dt / jsbsim_dt_max) + 1;
        jsbsim_inner_dt = this->dt / jsbsim_inner_steps;
    }
    set_env("JSBSIM_DEBUG", std::to_string(jsb_debug_level));  // disable init log in CTOR
}

void JSBSimFDM::initialize_jsbsim() {
    set_env("JSBSIM_DEBUG", std::to_string(jsb_debug_level));

    if (jsbsim_exec != nullptr) {
        jsbsim_exec->ResetToInitialConditions(0x2);
    }
    else {
        jsbsim_exec = std::make_unique<JSBSim::FGFDMExec>(nullptr, nullptr);

        const static std::string AircraftPath = "aircraft";
        const static std::string EnginePath = "engine";
        const static std::string SystemsPath = "systems";

        std::filesystem::path JSBSim_dir;
        try {
            JSBSim_dir = resource_paths::get_jsbsim_dir();
        } catch (const std::exception& e) {
            SL::optional().print(std::string("Error: ") + e.what());
            return;
        }

        // std::string jsbsim_aircraft_model = aircraft_model;
        // std::transform(
        //     jsbsim_aircraft_model.begin(), jsbsim_aircraft_model.end(),
        //     jsbsim_aircraft_model.begin(), [](unsigned char c){ return std::tolower(c); }
        // );
        const static std::map<std::string, std::string> jsbsim_model_mapping = {
            {"F16", "f16"},
            {"F15", "f15"},
            {"F15_original", "f15"},
            {"F18", "f18"},
            {"F18_original", "f18_original"},
            {"F4N", "F4N"},
            {"F4N_original", "F4N"},
            {"AJ37", "AJ37"},
            {"JA37", "JA37"},
            {"F22", "f22"},
            {"F22_original", "f22_original"},
        };
        jsbsim_exec->SetRootDir(SGPath(JSBSim_dir));
        jsbsim_exec->SetDebugLevel(jsb_debug_level);
        const auto source_model=fdm_source_model(aircraft_model);
        auto source_defaults=resource_paths::get_resource_path("aircraft/"+source_model+"/jsbsim_initial_properties.json");
        if(std::filesystem::is_regular_file(source_defaults)){
            std::ifstream file(source_defaults);std::stringstream text;text<<file.rdbuf();auto defaults=json::JSON::Load(text.str());
            for(const auto& [key,value]:defaults.ObjectRange())if(!jsbsim_exec->GetPropertyManager()->HasNode(key))
                jsbsim_exec->SetPropertyValue(key,value.JSONType()==json::JSON::Class::Integral?double(value.ToInt()):value.ToFloat());
        }
        auto host_properties=resource_paths::get_resource_path("aircraft/"+source_model+"/host_properties.json");
        host_control_inputs.clear();
        if(std::filesystem::is_regular_file(host_properties)){
            std::ifstream file(host_properties);std::stringstream text;text<<file.rdbuf();
            auto data=json::JSON::Load(text.str());
            if(data.hasKey("external_inputs"))for(const auto& value:data["external_inputs"].ArrayRange()){
                auto key=value.ToString();
                if(!jsbsim_exec->GetPropertyManager()->HasNode(key))jsbsim_exec->SetPropertyValue(key,0);
                // These are declared external normalized stick inputs, normally
                // supplied by FlightGear/Nasal. Never overwrite trims, faults,
                // internal FCS outputs or arbitrary properties by substring.
                auto canonical=key;
                if(!canonical.empty()&&canonical.front()=='/')canonical.erase(0,1);
                for(const auto& axis:std::array<std::pair<std::string,int>,3>{{{"aileron",0},{"elevator",1},{"rudder",2}}}){
                    auto base="controls/flight/"+axis.first;
                    if(canonical==base||canonical==base+"-sum"||canonical==base+"[0]"||canonical==base+"[1]")
                        host_control_inputs.emplace_back(key,axis.second);
                }
                for(int i=0;i<8;++i){
                    auto engine="controls/engines/engine"+(i?"["+std::to_string(i)+"]":std::string(""))+"/throttle";
                    if(canonical==engine||canonical=="controls/engines/engine[0]/throttle"){
                        host_control_inputs.emplace_back(key,3);break;
                    }
                }
            }
            if(data.hasKey("defaults"))for(const auto& [key,value]:data["defaults"].ObjectRange()){
                auto absolute="/"+key;
                if(!jsbsim_exec->GetPropertyManager()->HasNode(absolute))
                    jsbsim_exec->SetPropertyValue(absolute,value.JSONType()==json::JSON::Class::Integral?double(value.ToInt()):value.ToFloat());
            }
        }
        auto imported=resource_paths::get_resource_path("aircraft/"+source_model);
        bool loaded=false;
        try {
        if(std::filesystem::is_regular_file(imported/"fdm.xml")) {
            loaded=jsbsim_exec->LoadModel(SGPath(imported),SGPath(imported/"Engines"),SGPath(imported/"Systems"),"fdm",false);
        } else {
            if(source_model.rfind("FG-",0)==0)
                throw std::runtime_error("Missing catalog JSBSim source: "+source_model);
            auto mapping=jsbsim_model_mapping.find(aircraft_model);
            if(mapping==jsbsim_model_mapping.end())throw std::invalid_argument("Unknown JSBSim aircraft: "+aircraft_model);
            loaded=jsbsim_exec->LoadModel(SGPath(AircraftPath),SGPath(EnginePath),SGPath(SystemsPath),mapping->second,true);
        }
        } catch(const JSBSim::LogException& error) {
            throw std::runtime_error(error.what());
        } catch(const std::string& error) { throw std::runtime_error(error); }
        catch(const char* error) { throw std::runtime_error(error); }
        if(!loaded){jsbsim_exec.reset();throw std::runtime_error("JSBSim failed to load aircraft: "+aircraft_model);}

        std::string props = jsbsim_exec->QueryPropertyCatalog("");
        std::vector<std::string> prop_list;
        std::stringstream ss(props);
        std::string line;
        while (std::getline(ss, line)) {
            prop_list.push_back(line);
        }
        Catalog::add_jsbsim_props(prop_list);

        // std::cout << "\033[31m" << "JSBSim dt: " << jsbsim_inner_dt << "\033[0m" << std::endl;
        SL::optional().print("JSBSim dt: " + std::to_string(jsbsim_inner_dt));
        jsbsim_exec->Setdt(jsbsim_inner_dt);
    }
    

    // clear_default_condition();
}

// void JSBSimFDM::clear_default_condition() noexcept {
//     set_property_value(Catalog::ic_long_gc_deg, 120.0);
//     set_property_value(Catalog::ic_lat_geod_deg, 60.0);
//     set_property_value(Catalog::ic_h_sl_ft, 20000);
//     set_property_value(Catalog::ic_psi_true_deg, 0.0);
//     set_property_value(Catalog::ic_u_fps, 800.0);
//     set_property_value(Catalog::ic_v_fps, 0.0);
//     set_property_value(Catalog::ic_w_fps, 0.0);
//     // set_property_value(Catalog::ic_p_rad_sec, 0.0);
//     // set_property_value(Catalog::ic_q_rad_sec, 0.0);
//     // set_property_value(Catalog::ic_r_rad_sec, 0.0);
//     // set_property_value(Catalog::ic_roc_fpm, 0.0);
//     // set_property_value(Catalog::ic_terrain_elevation_ft, 12000);
// }

void JSBSimFDM::reset(const std::map<std::string, std::any>& initial_state) try {
    terminate=false;
    auto pos_any = initial_state.at("position");
    std::array<double, 3> pos_arr;
    if (pos_any.type() == typeid(std::array<double, 3>)) {
        pos_arr = std::any_cast<std::array<double, 3>>(pos_any);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset position with type " << pos_any.type().name() << std::endl;
        SL::optional().print("[JSBSimFDM] Error: Cannot reset position with type " + std::string(pos_any.type().name()));
        pos_arr = {0.0, 0.0, 0.0};
    }

    auto vel_any = initial_state.at("velocity");
    std::array<double, 3> vel_arr;
    if (vel_any.type() == typeid(std::array<double, 3>)) {
        vel_arr = std::any_cast<std::array<double, 3>>(vel_any);
    } else {
        std::cout << "[JSBSimFDM] Error: Cannot reset velocity with type " << vel_any.type().name() << std::endl;
        SL::optional().print("[JSBSimFDM] Error: Cannot reset velocity with type " + std::string(vel_any.type().name()));
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
            SL::optional().print("[JSBSimFDM] Error: Cannot reset yaw with type " + std::string(yaw_it->second.type().name()));
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

    // set_property_value(Catalog::propulsion_set_running, -1.0);
    // for (int i = 0; i < n_engines; ++i) {
    //     jsbsim_exec->SetPropertyValue("propulsion/engine[" + std::to_string(i) + "]/set-running", 1.0);   
    // }
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

    jsbsim_exec->Run();
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
              
    SL::optional().print(ss.str());
    // colorful::printLAN(ss.str());
} catch(const std::string& error) { throw std::runtime_error(error); }
catch(const char* error) { throw std::runtime_error(error); }

void JSBSimFDM::step_surfaces(const FlightSurfaceControls& controls) {
    validate_surface_controls(controls);
    if(!initialized)throw std::runtime_error("JSBSimFDM must be reset before stepping");
    // Bypass the AI filters/controller, sharing the same source FCS/actuators,
    // engines, aerodynamic forces and integrator.
    for(int i=0;i<jsbsim_inner_steps&&!terminate;++i){
        set_jsbsim_controls({controls.aileron,controls.elevator,controls.rudder,controls.throttle});
        if(!jsbsim_exec->Run())throw std::runtime_error("JSBSim direct surface step failed");
        update_properties();
    }
}
FlightMeasurements JSBSimFDM::flight_measurements() const {
    auto m=AircraftFDM::flight_measurements();
    m.reference_frame="legacy_position_map_velocity_attitude_local_nwu";
    if(!jsbsim_exec)return m;
    auto get=[&](const char* name)->std::optional<double>{
        if(!jsbsim_exec->GetPropertyManager()->HasNode(name))return std::nullopt;
        return jsbsim_exec->GetPropertyValue(name);
    };
    auto p=get("velocities/p-rad_sec"),q=get("velocities/q-rad_sec"),r=get("velocities/r-rad_sec");
    if(p&&q&&r)m.body_rates=std::array<double,3>{*p,*q,*r};
    m.alpha=get("aero/alpha-rad");m.beta=get("aero/beta-rad");m.normal_g=get("accelerations/Nz");
    if(auto density=get("atmosphere/rho-slugs_ft3"))m.density=*density*515.3788183931961;
    return m;
}

FlightMeasurements JSBSimFDM::world_flight_measurements() const {
    auto m=flight_measurements();
    if(!jsbsim_exec)return m;
    using V=std::array<double,3>;
    constexpr double radians=3.14159265358979323846/180.;
    auto basis=[](double lon,double lat){
        const double sl=std::sin(lon),cl=std::cos(lon),sp=std::sin(lat),cp=std::cos(lat);
        return std::array<V,3>{{{-sp*cl,-sp*sl,cp},{sl,-cl,0},{cp*cl,cp*sl,sp}}};
    };
    const auto origin=basis(REFERENCE_LON*radians,REFERENCE_LAT*radians);
    const auto local=basis(jsbsim_exec->GetPropertyValue("position/long-gc-deg")*radians,
                           jsbsim_exec->GetPropertyValue("position/lat-geod-deg")*radians);
    auto dot=[](const V& a,const V& b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];};
    auto rotate=[&](const V& value){
        V ecef{},world{};
        for(int i=0;i<3;++i)for(int j=0;j<3;++j)ecef[j]+=value[i]*local[i][j];
        for(int i=0;i<3;++i)world[i]=dot(ecef,origin[i]);
        return world;
    };
    const auto [roll,pitch,yaw]=m.orientation;
    const V f{std::cos(yaw)*std::cos(pitch),std::sin(yaw)*std::cos(pitch),-std::sin(pitch)};
    const V right{std::sin(yaw),-std::cos(yaw),0};
    const V up{std::cos(yaw)*std::sin(pitch),std::sin(yaw)*std::sin(pitch),std::cos(pitch)};
    V body_up{};for(int i=0;i<3;++i)body_up[i]=up[i]*std::cos(roll)+right[i]*std::sin(roll);
    const auto world_f=rotate(f),world_up=rotate(body_up);
    const double world_yaw=std::atan2(world_f[1],world_f[0]);
    const double world_pitch=std::atan2(-world_f[2],std::hypot(world_f[0],world_f[1]));
    const V reference_right{std::sin(world_yaw),-std::cos(world_yaw),0};
    const V reference_up{std::cos(world_yaw)*std::sin(world_pitch),std::sin(world_yaw)*std::sin(world_pitch),std::cos(world_pitch)};
    m.orientation={std::atan2(dot(world_up,reference_right),dot(world_up,reference_up)),world_pitch,world_yaw};
    m.velocity=rotate(m.velocity);m.gravity_up=rotate({0,0,1});m.reference_frame="map_nwu";
    // Source forces, integration, body rates, speed and legacy getters are
    // untouched. Only the new typed player's reference basis is converted.
    return m;
}

double JSBSimFDM::get_mach() const noexcept {
    return mach;
}

std::map<std::string,double> JSBSimFDM::visual_properties() const {
    std::map<std::string,double> result;
    if(!jsbsim_exec)return result;
    const std::map<std::string,std::string> aliases={
        {"controls/flight/aileron","fcs/aileron-cmd-norm"},
        {"controls/flight/elevator","fcs/elevator-cmd-norm"},
        {"controls/flight/rudder","fcs/rudder-cmd-norm"},
        {"surface-positions/left-aileron-pos-norm","fcs/left-aileron-pos-norm"},
        {"surface-positions/right-aileron-pos-norm","fcs/right-aileron-pos-norm"},
        {"surface-positions/elevator-pos-norm","fcs/elevator-pos-norm"},
        {"surface-positions/rudder-pos-norm","fcs/rudder-pos-norm"},
        {"surface-positions/flap-pos-norm","fcs/flap-pos-norm"},
        {"gear/gear[0]/position-norm","gear/gear-pos-norm"},
        {"gear/gear[1]/position-norm","gear/gear-pos-norm"},
        {"gear/gear[2]/position-norm","gear/gear-pos-norm"},
        {"controls/gear/gear-down","gear/gear-cmd-norm"}
    };
    for(const auto& [dest,source]:aliases)
        if(jsbsim_exec->GetPropertyManager()->HasNode(source))result[dest]=jsbsim_exec->GetPropertyValue(source);
    for(int i=0;i<jsbsim_exec->GetPropulsion()->GetNumEngines();++i){
        auto key="controls/engines/engine"+(i==0?std::string(""):"["+std::to_string(i)+"]")+"/throttle";
        auto source="fcs/throttle-cmd-norm["+std::to_string(i)+"]";
        if(jsbsim_exec->GetPropertyManager()->HasNode(source))result[key]=jsbsim_exec->GetPropertyValue(source);
    }
    return result;
}

void JSBSimFDM::run_jsbsim_step(const ActionSpace& action) {
    auto aileron_override = action.aileron_cmd();
    auto elevator_override = action.elevator_cmd();
    auto rudder_override = action.rudder_cmd();
    auto throttle_override = action.throttle_cmd();

    double delta_heading_raw = norm(action.delta_heading(), -1, 1) * deg2rad(85);
    // double delta_heading_raw = norm(action.at("delta_heading"), -1, 1) * deg2rad(40);
    double delta_heading_filt = fc_delta_heading_filter.update(delta_heading_raw, jsbsim_inner_dt);
    delta_heading = delta_heading_filt;

    double delta_pitch_raw = -norm(action.delta_altitude(), -1, 1) * deg2rad(45);
    double delta_pitch_filt = fc_delta_pitch_filter.update(delta_pitch_raw, jsbsim_inner_dt);
    delta_pitch = delta_pitch_filt;
    // delta_pitch = -deg2rad(20);
    // delta_pitch = 0;

    // if (position[2] < c3utils::feet_to_meters(20000)) {
    //     if (delta_pitch > 0) {
    //         delta_pitch = -deg2rad(80);
    //     }
    // }

    fix_vec = c3u::Vector3(1, 0, 0);
    fix_vec.rotate_zyx_self(0, delta_pitch, delta_heading + yaw);

    double mach_current = get_mach();
    double intent_mach = mach_current + action.delta_speed();
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
            // -1
            -0.75
        );

        if (aileron_override.has_value()) {
            control_commands[0] = norm(aileron_override.value(), -1.0, 1.0);
        }
        if (elevator_override.has_value()) {
            control_commands[1] = norm(elevator_override.value(), -1.0, 1.0);
        }
        if (rudder_override.has_value()) {
            control_commands[2] = norm(rudder_override.value(), -1.0, 1.0);
        }
        if (throttle_override.has_value()) {
            control_commands[3] = norm(throttle_override.value(), -1.0, 1.0);
        }

        set_jsbsim_controls(control_commands);

        bool result = jsbsim_exec->Run();
        if (!result) {
            colorful::printHONG("JSBSim step failed");
        }

        update_properties();
    }
}

void JSBSimFDM::step(const ActionSpace& action) try {
    if (!initialized) {
        throw std::runtime_error("JSBSimFDM must be reset before stepping");
    }

    run_jsbsim_step(action);
} catch(const std::string& error) { throw std::runtime_error(error); }
catch(const char* error) { throw std::runtime_error(error); }

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
    for(const auto& [property,axis]:host_control_inputs)
        jsbsim_exec->SetPropertyValue(property,controls[axis]);
    set_property_value(Catalog::fcs_aileron_cmd_norm, controls[0]);
    set_property_value(Catalog::fcs_elevator_cmd_norm, controls[1]);
    set_property_value(Catalog::fcs_rudder_cmd_norm, controls[2]);
    set_property_value(Catalog::fcs_throttle_cmd_norm, controls[3]);
    set_property_value(Catalog::fcs_mixture_cmd_norm, controls[3]);
    auto propulsion = jsbsim_exec->GetPropulsion();
    int n_engines = propulsion->GetNumEngines();
    for (int i = 0; i < n_engines; ++i) {
        jsbsim_exec->SetPropertyValue("fcs/throttle-cmd-norm[" + std::to_string(i) + "]", controls[3]);   
    }
}

void JSBSimFDM::set_jsbsim_initial_conditions(double lon, double lat, double alt,
                                             double speed, double roll_val, double pitch_val, double yaw_val) {
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
    // Explicit nonzero initial attitudes were previously discarded. Keep the
    // legacy zero-angle path identical, while allowing real inverted/pole
    // recovery validation. Core pitch is nose-down; JSBSim theta is nose-up.
    if(roll_val!=0)jsbsim_exec->SetPropertyValue("ic/phi-rad",roll_val);
    if(pitch_val!=0)jsbsim_exec->SetPropertyValue("ic/theta-rad",-pitch_val);
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

void JSBSimFDM::update_properties() {
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
    // SL::optional().printf("[JSBSimFDM] vel_est: %f, %f, %f\n", vel_est[0], vel_est[1], vel_est[2]);
    // SL::optional().printf("[JSBSimFDM] vel_true: %f, %f, %f\n", velocity[0], velocity[1], velocity[2]);

    mach = get_property_value(Catalog::velocities_mach);

    if (alt_m < 25) {
        SL::optional().printf("[JSBSimFDM] Altitude below 25m, terminating simulation\n");
        terminate = true;
        return;
    }

    auto state = get_state_dict();
    for (const auto& [key, value] : state) {
        if (value.type() == typeid(double)) {
            double v = std::any_cast<double>(value);
            if (std::isnan(v)) {
                terminate = true;
                SL::optional().printf("[JSBSimFDM] NaN (%s) value found for %s, terminating simulation\n", std::to_string(v).c_str(), key.c_str());
                break;
            }
        } else if (value.type() == typeid(std::array<double, 3>)) {
            auto arr = std::any_cast<std::array<double, 3>>(value);
            for (double v : arr) {
                if (std::isnan(v)) {
                    SL::optional().printf("[JSBSimFDM] NaN (%s) value found for %s (std::array<double, 3>), terminating simulation\n", std::to_string(v).c_str(), key.c_str());
                    terminate = true;
                    break;
                }
            }
            if (terminate) break;
        }
    }
}

std::string JSBSimFDM::log() const noexcept {
    auto nav_point_pos = c3u::Vector3(position) + fix_vec.normalize() * c3u::nm_to_meters(5.0);
    auto [block_lon, block_lat, block_alt] = NWU2LLA(nav_point_pos[0], nav_point_pos[1], nav_point_pos[2]);
    std::string color_str = "White";
    std::stringstream ss;
    ss << _nav_point_uuid << ",T=" << block_lon << "|" << block_lat << "|" << block_alt << ","
    << "Name=fc_target, Type=Navaid + Static, Radius=5, Color=" << color_str << ","
    << "Visible=" << 1 << "\n";
    return ss.str();
}

}
