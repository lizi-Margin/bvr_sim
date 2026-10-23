#pragma once
#include "player_flight_types.hxx"
#include <algorithm>

namespace bvr_sim {
namespace player_math {
using V=std::array<double,3>;
inline double dot(V a,V b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];}
inline V add(V a,V b){return {a[0]+b[0],a[1]+b[1],a[2]+b[2]};}
inline V scale(V a,double x){return {a[0]*x,a[1]*x,a[2]*x};}
inline V cross(V a,V b){return {a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]};}
inline V unit(V a,V fallback={1,0,0}){double n=std::sqrt(dot(a,a));return n>1e-10?scale(a,1/n):fallback;}
inline double angle(V a,V b){return std::acos(std::clamp(dot(unit(a),unit(b)),-1.,1.));}
inline double move(double a,double b,double rate){return a+std::clamp(b-a,-rate,rate);}
inline std::array<V,3> axes(V rpy){
    double r=rpy[0],p=rpy[1],y=rpy[2];
    V f{std::cos(y)*std::cos(p),std::sin(y)*std::cos(p),-std::sin(p)};
    V right{std::sin(y),-std::cos(y),0},up{std::cos(y)*std::sin(p),std::sin(y)*std::sin(p),std::cos(p)};
    return {f,add(scale(right,std::cos(r)),scale(up,-std::sin(r))),add(scale(up,std::cos(r)),scale(right,std::sin(r)))};
}
}

// Separate controller instance per Fighter, never an AI/RL controller or FDM.
// No target position/world query, no random calls, no pose/velocity mutations.
class PlayerFlightController {
    PlayerFlightProfile profile_;
    bool configured_=false,initialized_=false;
    double bank_=0,trim_=0,pitch_weight_=0,roll_weight_=0,last_pitch_=0,last_roll_=0;
    player_math::V filtered_target_{1,0,0};
    FlightSurfaceControls previous_;
    PlayerFlightState state_;
public:
    void configure(const PlayerFlightProfile& profile){
        profile.validate();profile_=profile;configured_=true;
        // Reset only this player's finite controller state on safe reload.
        initialized_=false;trim_=0;pitch_weight_=roll_weight_=0;previous_={};
        state_={};state_.configured=true;state_.profile_id=profile.id;state_.profile_hash=profile.source_hash;
    }
    const PlayerFlightProfile& profile() const {if(!configured_)throw std::logic_error("Player profile not configured");return profile_;}
    PlayerFlightState state() const{return state_;}
    void deactivate(){state_.active=false;state_.mode="inactive";}
    FlightSurfaceControls update(const FlightMeasurements& m,const PlayerFlightIntent& intent,double dt){
        using namespace player_math;
        if(!configured_)throw std::logic_error("Configure a player flight profile before submitting player intent");
        validate_player_intent(intent);
        if(!std::isfinite(dt)||dt<=0||dt>.1)throw std::invalid_argument("Player controller dt must be in(0,0.1]");
        const auto& p=profile_;const auto body=axes(m.orientation);
        const auto f=body[0],right=body[1],up=body[2];
        auto target=unit(intent.direction);
        if(!initialized_){filtered_target_=f;bank_=m.orientation[0];initialized_=true;}
        // Rotate on a sphere; a normalized linear mix stalls at exactly180deg.
        double theta=angle(filtered_target_,target),fraction=1-std::exp(-dt/p.target_response);
        if(theta>1e-7){
            auto tangent=add(target,scale(filtered_target_,-dot(target,filtered_target_)));
            if(dot(tangent,tangent)<1e-12)tangent=cross({0,0,1},filtered_target_);
            if(dot(tangent,tangent)<1e-12)tangent=cross({0,1,0},filtered_target_);
            filtered_target_=unit(add(scale(filtered_target_,std::cos(theta*fraction)),scale(unit(tangent),std::sin(theta*fraction))));
        }
        target=filtered_target_;state_.measured=m;state_.target_direction=target;
        state_.active=true;state_.protecting=false;state_.saturated=false;
        state_.mode=intent.mode==PlayerFlightMode::RawManual?"raw_manual":"assisted";
        state_.direction_error=angle(target,unit(m.velocity,f));state_.body_direction_error=angle(target,f);
        FlightSurfaceControls out;out.throttle=std::clamp(intent.throttle,0.,1.);
        if(intent.mode==PlayerFlightMode::RawManual){
            out.aileron=std::clamp(intent.roll_input,-1.,1.);out.elevator=-std::clamp(intent.pitch_input,-1.,1.);
            out.rudder=std::clamp(intent.yaw_input,-1.,1.);trim_=0;pitch_weight_=roll_weight_=1;
        }else{
            double speed=std::max(m.speed,1.);
            double heading=std::atan2(target[1],target[0]);
            double yaw_error=std::remainder(heading-m.orientation[2],2*3.14159265358979323846);
            // At a vertical target, horizontal azimuth has no meaning. Bank
            // demand fades continuously rather than selecting arbitrary yaw.
            double horizontal=std::hypot(target[0],target[1]);
            double low=std::clamp((speed-p.min_speed)/(p.reference_speed-p.min_speed),0.,1.);
            double turn=std::clamp(yaw_error*p.heading_gain,-p.max_turn_rate,p.max_turn_rate)*std::min(1.,horizontal/.2)*(.25+.75*low);
            double desired_bank=std::clamp(-std::atan(speed*turn/9.80665),-p.max_bank,p.max_bank);
            bank_+=std::remainder(desired_bank-bank_,2*3.14159265358979323846)*(1-std::exp(-dt/p.bank_response));
            auto reference_right=unit(cross(f,{0,0,1}),{std::sin(m.orientation[2]),-std::cos(m.orientation[2]),0});
            auto reference_up=unit(cross(reference_right,f),up);
            auto desired_up=add(scale(reference_up,std::cos(bank_)),scale(reference_right,std::sin(bank_)));
            double roll_error=std::atan2(dot(desired_up,right),dot(desired_up,up));
            double roll_demand=std::clamp(roll_error*p.bank_gain,-p.max_roll_rate,p.max_roll_rate);
            const double target_elevation=std::atan2(target[2],std::hypot(target[0],target[1]));
            const double flight_elevation=std::atan2(m.velocity[2],std::hypot(m.velocity[0],m.velocity[1]));
            double target_pitch_error=target_elevation-flight_elevation;
            // Pull only as the lift vector aligns with a lateral target. Pure
            // vertical aiming never asks for a180deg inverted bank.
            double bank=m.orientation[0];
            double coordination=9.80665/speed*std::sin(bank)*std::sin(bank)/std::max(.25,std::cos(bank))*std::cos(flight_elevation);
            double pitch_demand=std::clamp(target_pitch_error*p.pitch_gain*std::cos(bank)+coordination,-p.max_pitch_rate,p.max_pitch_rate);
            auto rates=m.body_rates.value_or(V{});
            double schedule=std::clamp(std::pow(p.reference_speed/speed,2),p.schedule_min,p.schedule_max);
            double ail=(roll_demand-rates[0])*p.roll_rate_gain*schedule;
            if(intent.manual_pitch){pitch_weight_=1;last_pitch_=std::clamp(intent.pitch_input,-1.,1.);trim_=0;}
            else pitch_weight_=std::max(0.,pitch_weight_-dt/p.release_seconds);
            if(intent.manual_roll){roll_weight_=1;last_roll_=std::clamp(intent.roll_input,-1.,1.);}
            else roll_weight_=std::max(0.,roll_weight_-dt/p.release_seconds);
            if(std::abs(target_pitch_error)<.25&&std::abs(roll_error)<.3&&pitch_weight_==0&&std::abs(previous_.elevator)<.95){
                trim_=std::clamp(trim_+target_pitch_error*p.trim_gain*dt,-p.trim_limit,p.trim_limit);
            }else trim_*=std::exp(-dt/p.release_seconds);
            double pull=(pitch_demand-rates[1])*p.pitch_rate_gain*schedule+trim_;
            pull=pull*(1-pitch_weight_)+last_pitch_*pitch_weight_;
            ail=ail*(1-roll_weight_)+last_roll_*roll_weight_;
            if(intent.protection){
                if(m.alpha){
                    double hi=std::clamp((p.max_alpha-*m.alpha)*p.protection_gain,-1.,1.);
                    double lo=std::clamp((p.min_alpha-*m.alpha)*p.protection_gain,-1.,1.);
                    double capped=std::clamp(pull,lo,hi);state_.protecting|=capped!=pull;pull=capped;
                }
                if(m.normal_g){
                    double hi=std::clamp((p.max_g-*m.normal_g)*p.protection_gain,-1.,1.);
                    double lo=std::clamp((p.min_g-*m.normal_g)*p.protection_gain,-1.,1.);
                    double capped=std::clamp(pull,lo,hi);state_.protecting|=capped!=pull;pull=capped;
                }
                // Below the configured sustainable manoeuvre speed unload
                // rather than increasing engine thrust or aerodynamic lift.
                if(speed<p.min_speed&&pull>.1){pull=.1;state_.protecting=true;}
                if(state_.protecting)trim_*=std::exp(-dt/p.release_seconds);
            }
            double rud=intent.manual_yaw?intent.yaw_input:-(m.beta.value_or(0)*p.sideslip_gain+rates[2]*p.yaw_damping);
            state_.saturated=std::abs(ail)>1||std::abs(pull)>1||std::abs(rud)>1;
            // Manual press owns the axis immediately. Release blends its last
            // value into the independent helper with no integral carry-over.
            out.aileron=move(previous_.aileron,std::clamp(ail,-1.,1.),p.surface_rate*dt);
            out.elevator=move(previous_.elevator,-std::clamp(pull,-1.,1.),p.surface_rate*dt);
            out.rudder=move(previous_.rudder,std::clamp(rud,-1.,1.),p.surface_rate*dt);
            state_.target_bank=bank_;state_.roll_error=roll_error;
            state_.desired_roll_rate=roll_demand;state_.desired_pitch_rate=pitch_demand;
        }
        state_.pitch_manual_weight=pitch_weight_;state_.roll_manual_weight=roll_weight_;
        previous_=state_.controls=out;return out;
    }
};
} // namespace bvr_sim
