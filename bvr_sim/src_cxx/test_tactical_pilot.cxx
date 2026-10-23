#include "test_main.hxx"
#include "simulator/aircraft/tactical_pilot.hxx"
using namespace bvr_sim;
TEST(AirTacticalPilot, NoTrackMeansSearchWithoutInventedTarget) {
    AirTacticalPilot p;TacticalObservation o;o.position={0,0,8500};o.altitude_agl=8000;o.missiles=6;
    auto intent=p.decide(o,0,3.141592653589793,8500);
    ASSERT(intent.phase=="search");ASSERT(!intent.fire);ASSERT(intent.target_uid.empty());ASSERT(intent.heading==3.141592653589793);
}
TEST(AirTacticalPilot, ObservedLaunchSupportDefendReacquire) {
    AirTacticalPilot p;TacticalObservation o;o.position={0,0,8500};o.altitude_agl=8000;o.missiles=6;
    o.tracks.push_back({"observed",{20000,0,8500},{-250,0,0}});
    auto c=p.decide(o,0,0,8500);ASSERT(c.fire);ASSERT(c.target_uid=="observed");p.launched(0);
    o.weapon_supporting=true;c=p.decide(o,1,0,8500);ASSERT(c.phase=="support");ASSERT(!c.fire);
    o.missile_warning=true;o.threat_bearing=.4;c=p.decide(o,2,0,8500);ASSERT(c.phase=="defend");ASSERT(!c.fire);
    o.missile_warning=false;o.weapon_supporting=false;c=p.decide(o,30,0,8500);ASSERT(c.fire);
    o.tracks.clear();c=p.decide(o,60,0,8500);ASSERT(c.phase=="search");ASSERT(!c.fire);
}
