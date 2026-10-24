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
    bool recovering_=false;
    double bank_=0,trim_=0,manual_trim_=0,pitch_weight_=0,roll_weight_=0,last_pitch_=0,last_roll_=0;
    player_math::V filtered_target_{1,0,0};
    player_math::V filtered_up_{0,0,1};
    FlightSurfaceControls previous_;
    PlayerFlightState state_;
public:
    void configure(const PlayerFlightProfile& profile){
        profile.validate();profile_=profile;configured_=true;
        // Reset only this player's finite controller state on safe reload.
        initialized_=false;recovering_=false;trim_=manual_trim_=0;pitch_weight_=roll_weight_=0;previous_={};
        state_={};state_.configured=true;state_.profile_id=profile.id;state_.profile_hash=profile.source_hash;
    }
    const PlayerFlightProfile& profile() const {if(!configured_)throw std::logic_error("Player profile not configured");return profile_;}
    PlayerFlightState state() const{return state_;}
    void deactivate(){state_.active=false;state_.mode="inactive";}
    FlightSurfaceControls update(const FlightMeasurements& m,const PlayerFlightIntent& intent,double dt){
        using namespace player_math;
        if(!configured_)throw std::logic_error("Configure a player flight profile before submitting player intent");
        validate_player_intent(intent);
        if(m.reference_frame!="map_nwu")throw std::invalid_argument("Player flight control requires world_flight_measurements in map_nwu");
        if(!std::isfinite(dt)||dt<=0||dt>.1)throw std::invalid_argument("Player controller dt must be in(0,0.1]");
        const auto& p=profile_;const auto body=axes(m.orientation);
        const auto f=body[0],right=body[1],up=body[2];
        auto target=unit(intent.direction);
        if(!initialized_){filtered_target_=f;filtered_up_=up;bank_=m.orientation[0];initialized_=true;}
        // Rotate on a sphere; a normalized linear mix stalls at exactly180deg.
        double theta=angle(filtered_target_,target),fraction=1-std::exp(-dt/p.target_response);
        if(theta>1e-7){
            auto tangent=add(target,scale(filtered_target_,-dot(target,filtered_target_)));
            if(dot(tangent,tangent)<1e-12)tangent=cross({0,0,1},filtered_target_);
            if(dot(tangent,tangent)<1e-12)tangent=cross({0,1,0},filtered_target_);
            filtered_target_=unit(add(scale(filtered_target_,std::cos(theta*fraction)),scale(unit(tangent),std::sin(theta*fraction))));
        }
        target=filtered_target_;state_.measured=m;state_.target_direction=target;
        state_.active=true;state_.protecting=false;state_.saturated=false;state_.energy_limited=false;
        state_.limited_direction=target;
        state_.mode=intent.mode==PlayerFlightMode::RawManual?"raw_manual":"assisted";
        state_.direction_error=angle(target,unit(m.velocity,f));state_.body_direction_error=angle(target,f);
        FlightSurfaceControls out;out.throttle=std::clamp(intent.throttle,0.,1.);
        if(intent.mode==PlayerFlightMode::RawManual){
            out.aileron=std::clamp(intent.roll_input,-1.,1.);out.elevator=-std::clamp(intent.pitch_input,-1.,1.);
            out.rudder=std::clamp(intent.yaw_input,-1.,1.);trim_=manual_trim_=0;pitch_weight_=roll_weight_=1;
        }else{
            double speed=std::max(m.speed,1.);
            double density=m.density.value_or(p.reference_density);
            double equivalent_speed=speed*std::sqrt(std::max(.001,density)/p.reference_density);
            double minimum_tas=p.min_speed*speed/std::max(1.,equivalent_speed);
            double heading=std::atan2(target[1],target[0]);
            double low=std::clamp((equivalent_speed-p.min_speed)/(p.reference_speed-p.min_speed),0.,1.);
            double target_elevation=std::atan2(target[2],std::hypot(target[0],target[1]));
            const double flight_elevation=std::atan2(m.velocity[2],std::hypot(m.velocity[0],m.velocity[1]));
            // A steep mouse target cannot supply energy. Reduce only the
            // assisted flight-path demand before kinetic energy is exhausted.
            // Preserve the raw target; raw manual bypasses this entire layer.
            if(intent.protection && !intent.manual_pitch){
                if(speed<minimum_tas)recovering_=true;
                else if(speed>minimum_tas*p.recovery_speed_ratio)recovering_=false;
                // Hysteresis controls exit from recovery, not the speed where
                // level flight becomes forbidden. The old expression forced
                // a steady descent above min_speed merely for missing reserve.
                double available=std::clamp((speed-minimum_tas)/(9.80665*p.energy_horizon),-1.,1.);
                double ceiling=recovering_?p.recovery_pitch:std::asin(available);
                double limited=std::min(target_elevation,ceiling);
                state_.energy_limited=limited<target_elevation;state_.protecting|=state_.energy_limited;
                target_elevation=limited;
                state_.limited_direction={std::cos(limited)*std::cos(heading),std::cos(limited)*std::sin(heading),std::sin(limited)};
            }
            double target_pitch_error=target_elevation-flight_elevation;
            // Geometric path steering has no Euler heading jump at a vertical
            // attitude. Request curvature, then orient lift against gravity.
            // Only measured own velocity/attitude enter this computation.
            auto velocity_direction=unit(m.velocity,f),limited=state_.limited_direction;
            auto rotation=cross(velocity_direction,limited);
            auto fallback_axis=unit(cross(velocity_direction,{0,1,0}),{0,0,1});
            if(std::hypot(velocity_direction[0],velocity_direction[1])>.2)fallback_axis={0,0,1};
            auto omega=scale(unit(rotation,fallback_axis),angle(velocity_direction,limited)*p.pitch_gain);
            double turn_limit=std::min(p.max_turn_rate,9.80665*std::tan(p.max_bank)/speed)*(.25+.75*low);
            omega[2]=std::clamp(omega[2]*p.heading_gain/p.pitch_gain,-turn_limit,turn_limit);
            double vertical_rate=std::hypot(omega[0],omega[1]);
            if(vertical_rate>p.max_pitch_rate){omega[0]*=p.max_pitch_rate/vertical_rate;omega[1]*=p.max_pitch_rate/vertical_rate;}
            omega=add(omega,scale(velocity_direction,-dot(omega,velocity_direction)));
            auto acceleration=add(scale(cross(omega,velocity_direction),speed),scale(m.gravity_up,9.80665));
            auto reference_right=unit(cross(f,{0,0,1}),right);
            auto reference_up=unit(cross(reference_right,f),up);
            // A large downward curvature may exceed the permitted negative
            // lift. Choose its positive-lift roll solution using the upright
            // reference, not current bank, so starting the roll cannot cancel
            // the decision halfway through the manoeuvre.
            bool negative_lift_limited=intent.protection&&!intent.manual_pitch&&
                std::max(std::abs(f[2]),std::abs(velocity_direction[2]))>.5&&
                dot(acceleration,reference_up)<9.80665*p.min_g;
            double pole=std::clamp((std::max(std::abs(f[2]),std::abs(velocity_direction[2]))-.5)/.3,0.,1.);
            auto bank_acceleration=acceleration;
            // In ordinary flight a pitch-down correction must not reverse
            // the bank reference through180deg. That made high-speed level
            // captures roll repeatedly instead of letting the pitch loop
            // unload. Use positive vertical support for bank steering, fading
            // to the full geometric lift vector as the path nears vertical.
            if(bank_acceleration[2]<9.80665)
                bank_acceleration[2]=9.80665+(bank_acceleration[2]-9.80665)*(negative_lift_limited?1.:pole);
            auto desired_up=unit(add(bank_acceleration,scale(f,-dot(bank_acceleration,f))),up);
            // Recovering from a steep climb can require pushing rather than
            // pulling. Do not demand an abrupt half-roll just because that
            // signed pitch curvature makes the required lift vector reverse.
            // Flat inverted flight still requests the normal upright recovery.
            // During energy recovery a half-roll can be necessary: positive
            // lift can bend a steep ballistic climb down sooner than the
            // aircraft's small permitted negative-alpha lift. Let the full
            // geometric lift solution perform that manoeuvre when limited.
            if(!state_.energy_limited&&!negative_lift_limited&&(std::abs(f[2])>.5||std::abs(velocity_direction[2])>.5)&&
               std::abs(omega[2])<.1*std::max(.001,std::hypot(omega[0],omega[1]))&&dot(desired_up,up)<0)
                desired_up=scale(desired_up,-1.);
            double desired_bank=std::atan2(dot(desired_up,reference_right),dot(desired_up,reference_up));
            // Bank about world-up ceases to be meaningful near a vertical
            // forward axis. Fade that limit, retaining vector roll feedback.
            double bank_limit=p.max_bank+(3.14159265358979323846-p.max_bank)*std::clamp((std::abs(f[2])-.7)/.25,0.,1.);
            if(negative_lift_limited)bank_limit=3.14159265358979323846;
            bank_=std::clamp(desired_bank,-bank_limit,bank_limit);
            desired_up=add(scale(reference_up,std::cos(bank_)),scale(reference_right,std::sin(bank_)));
            auto held_up=unit(add(filtered_up_,scale(f,-dot(filtered_up_,f))),up);
            double delta=std::atan2(dot(desired_up,cross(f,held_up)),dot(desired_up,held_up));
            double response=delta*(1-std::exp(-dt/p.bank_response));
            filtered_up_=unit(add(scale(held_up,std::cos(response)),scale(cross(f,held_up),std::sin(response))));
            double roll_error=std::atan2(dot(filtered_up_,right),dot(filtered_up_,up));
            double roll_demand=std::clamp(roll_error*p.bank_gain,-p.max_roll_rate,p.max_roll_rate);
            // Lateral intent owns bank. Until that bank is reached, projecting
            // the *desired* lateral curvature onto the *current* right axis
            // can demand negative G during a reversal. Preserve measured-bank
            // coordinated lift while tracking vertical flight-path error.
            // Blend to the full vector solution near the vertical pole, where
            // a gravity-referenced bank angle loses meaning.
            double cos_bank=std::clamp(dot(reference_up,up),-1.,1.);
            // World vertical path response contains q*cos(bank). Request the
            // inverse projection: multiplying by cos(bank) a second time made
            // the vertical loop four times weaker at60deg bank. Keep the sign
            // for inverted flight; the bounded denominator bridges knife-edge
            // attitudes until geometric pole steering / roll recovery takes over.
            double supported_cos=std::copysign(std::max(.25,std::abs(cos_bank)),cos_bank);
            double coordinated=9.80665/speed*(1-cos_bank*cos_bank)/supported_cos*std::cos(flight_elevation);
            double path_pitch=target_pitch_error*p.pitch_gain/supported_cos+coordinated;
            double pitch_demand=std::clamp(path_pitch*(1-pole)+dot(omega,right)*pole,-p.max_pitch_rate,p.max_pitch_rate);
            // Anticipate the normal acceleration implied by body pitch rate,
            // instead of waiting for an excessive measured G before reversing
            // the elevator. n ~= q*V/g + vertical component of body up.
            // This limits the *request*, never the resulting forces or pose.
            auto bounded_pitch_rate=[&](double demand){
                if(!intent.protection)return demand;
                double gravity_projection=dot(up,m.gravity_up);
                double lo=9.80665*(p.min_g-gravity_projection)/speed;
                double hi=9.80665*(p.max_g-gravity_projection)/speed;
                double result=std::clamp(demand,lo,hi);
                state_.protecting|=result!=demand;
                return result;
            };
            pitch_demand=bounded_pitch_rate(pitch_demand);
            auto rates=m.body_rates.value_or(V{});
            double schedule=std::clamp(std::pow(p.reference_speed/std::max(1.,equivalent_speed),2),p.schedule_min,p.schedule_max);
            double ail=(roll_demand-rates[0])*p.roll_rate_gain*schedule;
            if(intent.manual_pitch){
                if(pitch_weight_<1)manual_trim_=0;
                pitch_weight_=1;last_pitch_=std::clamp(intent.pitch_input,-1.,1.);trim_=0;
            }
            else pitch_weight_=std::max(0.,pitch_weight_-dt/p.release_seconds);
            if(intent.manual_roll){roll_weight_=1;last_roll_=std::clamp(intent.roll_input,-1.,1.);}
            else roll_weight_=std::max(0.,roll_weight_-dt/p.release_seconds);
            double pitch_rate_error=pitch_demand-rates[1];
            // Roll transients may suspend building trim, but must not prevent
            // its removal. Otherwise a captured turn keeps its several-G
            // elevator while the bank reverses, even when pitch demand is
            // negative. Allow only the opposing increment through that gate.
            bool unwinding_trim=trim_*pitch_rate_error<0;
            if(((std::abs(target_pitch_error)<.25&&std::abs(roll_error)<.3)||unwinding_trim)&&
               pitch_weight_==0&&std::abs(previous_.elevator)<.95){
                double next_trim=trim_+pitch_rate_error*p.trim_gain*dt;
                if(unwinding_trim&&std::abs(roll_error)>=.3&&trim_*next_trim<0)next_trim=0;
                trim_=std::clamp(next_trim,-p.trim_limit,p.trim_limit);
            }else if(pitch_weight_>0||std::abs(target_pitch_error)>.5){
                trim_*=std::exp(-dt/p.release_seconds);
            }
            // Hold the established aerodynamic trim through short roll
            // transients. Bleeding it on every reversal caused a persistent
            // downward flight-path bias during otherwise level manoeuvres.
            double pull=(pitch_demand-rates[1])*p.pitch_rate_gain*schedule+trim_;
            // Assisted keyboard pitch requests a bounded body pitch rate.
            // Full direct elevator followed by delayed alpha/G corrections
            // produced a violent pitch reversal while S was still held.
            // The same rate feedback damps takeover and its release; raw mode
            // retains exact direct surfaces for intentional full-stick tests.
            double manual_rate=pitch_weight_>0?bounded_pitch_rate(last_pitch_*p.max_pitch_rate):0;
            // A proportional rate loop alone has a permanent aerodynamic trim
            // error (notably while pushing). Integrate only the owned manual
            // axis; its bounded trim fades out with that axis on release.
            if(intent.manual_pitch&&std::abs(previous_.elevator)<.95)
                manual_trim_=std::clamp(manual_trim_+(manual_rate-rates[1])*p.trim_gain*dt,-p.trim_limit,p.trim_limit);
            double manual_pull=(manual_rate-rates[1])*p.pitch_rate_gain*schedule+manual_trim_;
            pull=pull*(1-pitch_weight_)+manual_pull*pitch_weight_;
            // Assisted roll owns a configured body-rate request, just like
            // assisted pitch. Direct full aileron could build several times
            // that rate on sensitive imported aircraft and keep rolling
            // through release. RawManual above still owns direct surfaces.
            double manual_roll_rate=last_roll_*p.max_roll_rate;
            double manual_ail=(manual_roll_rate-rates[0])*p.roll_rate_gain*schedule;
            ail=ail*(1-roll_weight_)+manual_ail*roll_weight_;
            if(intent.protection){
                bool surface_capped=false;
                if(m.alpha){
                    double hi=std::clamp((p.max_alpha-*m.alpha)*p.protection_gain,-1.,1.);
                    double lo=std::clamp((p.min_alpha-*m.alpha)*p.protection_gain,-1.,1.);
                    double capped=std::clamp(pull,lo,hi);surface_capped|=capped!=pull;pull=capped;
                }
                if(m.normal_g){
                    double hi=std::clamp((p.max_g-*m.normal_g)*p.protection_gain,-1.,1.);
                    double lo=std::clamp((p.min_g-*m.normal_g)*p.protection_gain,-1.,1.);
                    double capped=std::clamp(pull,lo,hi);surface_capped|=capped!=pull;pull=capped;
                }
                // Below the configured sustainable manoeuvre speed unload
                // rather than increasing engine thrust or aerodynamic lift.
                // Positive body pitch while inverted can point the path down
                // and recover energy. Do not suppress that recovery merely
                // because the same body-axis sign means climbing when upright.
                bool raises_path=intent.manual_pitch?(last_pitch_>0&&up[2]>0):(acceleration[2]>=9.80665);
                if(speed<minimum_tas&&pull>.1&&raises_path){pull=.1;surface_capped=true;}
                state_.protecting|=surface_capped;
                // Energy limiting already changes the rate demand upstream.
                // Its status alone must not continuously erase valid trim.
                if(surface_capped){trim_*=std::exp(-dt/p.release_seconds);manual_trim_*=std::exp(-dt/p.release_seconds);}
            }
            double rud=intent.manual_yaw?intent.yaw_input:-(m.beta.value_or(0)*p.sideslip_gain+rates[2]*p.yaw_damping);
            state_.saturated=std::abs(ail)>1||std::abs(pull)>1||std::abs(rud)>1;
            // Manual press owns the axis immediately. Release blends its last
            // value into the independent helper with no integral carry-over.
            out.aileron=move(previous_.aileron,std::clamp(ail,-1.,1.),p.surface_rate*dt);
            out.elevator=move(previous_.elevator,-std::clamp(pull,-1.,1.),p.surface_rate*dt);
            out.rudder=move(previous_.rudder,std::clamp(rud,-1.,1.),p.surface_rate*dt);
            state_.target_bank=bank_;state_.roll_error=roll_error;
            state_.desired_roll_rate=roll_demand*(1-roll_weight_)+manual_roll_rate*roll_weight_;state_.desired_pitch_rate=pitch_demand*(1-pitch_weight_)+manual_rate*pitch_weight_;
        }
        state_.pitch_manual_weight=pitch_weight_;state_.roll_manual_weight=roll_weight_;
        state_.pitch_trim=trim_*(1-pitch_weight_)+manual_trim_*pitch_weight_;
        previous_=state_.controls=out;return out;
    }
};
} // namespace bvr_sim
