#pragma once
#include <array>
#include <cmath>
#include <optional>
#include <stdexcept>
#include <string>

namespace bvr_sim {
// Public axes: world north/west/up. Body rates: right roll, nose-up pitch,
// right yaw, rad/s. Positive public pitch stick pulls up in every control mode.
enum class PlayerFlightMode { Assisted, RawManual };
struct PlayerFlightIntent {
    std::array<double,3> direction{1,0,0};
    double throttle=.85,pitch_input=0,roll_input=0,yaw_input=0;
    bool manual_pitch=false,manual_roll=false,manual_yaw=false,protection=true;
    PlayerFlightMode mode=PlayerFlightMode::Assisted;
    bool fire=false,drop_bomb=false,lock=false;
    std::string target_uid,weapon="AIM-120C7";
};
struct FlightMeasurements {
    std::array<double,3> position{},velocity{},orientation{};
    std::optional<std::array<double,3>> body_rates;
    std::optional<double> alpha,beta,normal_g,density;
    double speed=0;
};
struct FlightSurfaceControls {double aileron=0,elevator=0,rudder=0,throttle=0;};
inline void validate_surface_controls(const FlightSurfaceControls& c){
    for(double v:{c.aileron,c.elevator,c.rudder})
        if(!std::isfinite(v)||std::abs(v)>1)throw std::invalid_argument("Surface inputs must be finite normalized axes in[-1,1]");
    if(!std::isfinite(c.throttle)||c.throttle<0||c.throttle>1)throw std::invalid_argument("Throttle must be finite in[0,1]");
}
// Defaults deliberately do not constitute a usable aircraft profile. Resolve a
// versioned data profile and validate before activating the player controller.
struct PlayerFlightProfile {
    std::string id,version,source_hash;
    double heading_gain=0,bank_gain=0,roll_rate_gain=0,pitch_gain=0,pitch_rate_gain=0;
    double yaw_damping=0,sideslip_gain=0,trim_gain=0,trim_limit=0;
    double max_bank=0,max_roll_rate=0,max_pitch_rate=0,max_turn_rate=0;
    double max_alpha=0,min_alpha=0,max_g=0,min_g=0,protection_gain=0;
    double reference_speed=0,min_speed=0,schedule_min=0,schedule_max=0;
    double surface_rate=0,release_seconds=0,target_response=0,bank_response=0;
    double energy_horizon=0,recovery_speed_ratio=0,recovery_pitch=0;
    double reference_density=0;
    void validate() const {
        const double positive[]={heading_gain,bank_gain,roll_rate_gain,pitch_gain,pitch_rate_gain,
            max_bank,max_roll_rate,max_pitch_rate,max_turn_rate,max_alpha,max_g,protection_gain,
            reference_speed,min_speed,schedule_min,schedule_max,surface_rate,release_seconds,
            target_response,bank_response,energy_horizon,recovery_speed_ratio,reference_density};
        for(double v:positive)if(!std::isfinite(v)||v<=0)throw std::invalid_argument("Player flight profile requires finite positive gains/limits/time constants");
        for(double v:{yaw_damping,sideslip_gain,trim_gain,trim_limit,min_alpha,min_g,recovery_pitch})
            if(!std::isfinite(v))throw std::invalid_argument("Nonfinite player flight profile");
        if(id.empty()||version.empty()||max_bank>1.5||max_alpha>.8||min_alpha>=max_alpha||
           min_g>=max_g||max_g>15||min_g< -5||min_speed>=reference_speed||schedule_min>schedule_max||
           trim_limit<0||trim_limit>1||yaw_damping<0||sideslip_gain<0||trim_gain<0||
           recovery_speed_ratio<=1||recovery_speed_ratio>2||energy_horizon>60||recovery_pitch>=0||recovery_pitch<-.5||reference_density>2)
            throw std::invalid_argument("Invalid player flight profile bounds/version");
    }
};
struct PlayerFlightState {
    bool configured=false,active=false,protecting=false,saturated=false,energy_limited=false;
    FlightMeasurements measured;
    FlightSurfaceControls controls;
    std::array<double,3> target_direction{1,0,0};
    std::array<double,3> limited_direction{1,0,0};
    double direction_error=0,body_direction_error=0,target_bank=0,roll_error=0;
    double desired_roll_rate=0,desired_pitch_rate=0,pitch_manual_weight=0,roll_manual_weight=0;
    double pitch_trim=0;
    std::string profile_id,profile_hash,mode="inactive";
};
inline void validate_player_intent(const PlayerFlightIntent& x) {
    double length=0;
    for(double v:x.direction){if(!std::isfinite(v))throw std::invalid_argument("Nonfinite player direction");length+=v*v;}
    if(!std::isfinite(length)||length<1e-12)throw std::invalid_argument("Player direction must be a finite nonzero NWU vector");
    for(double v:{x.throttle,x.pitch_input,x.roll_input,x.yaw_input})
        if(!std::isfinite(v))throw std::invalid_argument("Nonfinite player input axis");
    if(x.mode!=PlayerFlightMode::Assisted&&x.mode!=PlayerFlightMode::RawManual)
        throw std::invalid_argument("Unknown player flight mode");
}
} // namespace bvr_sim
