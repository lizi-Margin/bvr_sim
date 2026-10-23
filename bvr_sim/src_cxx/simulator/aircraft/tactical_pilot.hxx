#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <optional>
#include <string>
#include <vector>

namespace bvr_sim {
// Value-only local observations. No object pool, hidden target pointers, renderer,
// gameplay headers or missile energy state can be accessed by this controller.
struct TacticalTrack { std::string uid;std::array<double,3> position{},velocity{}; };
struct TacticalObservation {
    std::array<double,3> position{},velocity{};
    double yaw=0,altitude_agl=0;
    std::vector<TacticalTrack> tracks;
    bool radar_warning=false,missile_warning=false,weapon_supporting=false;
    double threat_bearing=0;
    int missiles=0;
};
struct TacticalIntent {
    double heading=0,pitch=0,throttle=.9;
    std::string target_uid,phase="search";
    bool lock=false,fire=false;
};
class AirTacticalPilot {
    double last_decision_=-100,last_fire_=-100,last_seen_=-100;
    std::optional<TacticalTrack> track_;
    TacticalIntent held_;
    int side_;
public:
    explicit AirTacticalPilot(unsigned seed=7):side_((seed&1)?1:-1){}
    void launched(double now){last_fire_=now;}
    TacticalIntent decide(const TacticalObservation& o,double now,double search_heading,double cruise_altitude){
        constexpr double pi=3.14159265358979323846;
        if(now-last_decision_<.5){auto c=held_;c.fire=false;return c;}
        last_decision_=now;
        TacticalIntent c;c.heading=search_heading;c.throttle=.95;
        c.pitch=std::clamp((cruise_altitude-o.position[2])*.00008,-.06,.12);
        if(!o.tracks.empty()){
            const TacticalTrack* closest=&o.tracks.front();
            auto range=[&](const TacticalTrack& t){return std::hypot(t.position[0]-o.position[0],t.position[1]-o.position[1]);};
            for(const auto& t:o.tracks)if(range(t)<range(*closest))closest=&t;
            track_=*closest;last_seen_=now;
        }
        double range=1e20,bearing=search_heading;
        if(track_&&now-last_seen_<20){
            double age=now-last_seen_;
            double n=track_->position[0]+track_->velocity[0]*age-o.position[0];
            double w=track_->position[1]+track_->velocity[1]*age-o.position[1];
            range=std::hypot(n,w);bearing=std::atan2(w,n);
            c.heading=bearing;c.target_uid=track_->uid;c.phase="approach";c.lock=!o.tracks.empty();
        }
        if(o.missile_warning){
            c.phase="defend";c.heading=o.yaw+o.threat_bearing+side_*pi*.6;
            c.pitch=o.altitude_agl>1800?-.06:.14;c.throttle=1;
        }else if(o.weapon_supporting){
            c.phase="support";c.heading=bearing+side_*pi*.14;c.pitch=std::max(.015,c.pitch);
        }else if(o.radar_warning&&range<45000){
            c.phase="crank";c.heading=bearing+side_*pi*.12;
        }
        if(!o.tracks.empty()&&!o.weapon_supporting&&o.missiles>0&&now-last_fire_>20&&range<30000&&
           std::abs(std::remainder(bearing-o.yaw,2*pi))<pi/4&&!o.missile_warning){c.fire=true;c.phase="launch";}
        held_=c;return c;
    }
};
} // namespace bvr_sim
