#pragma once
#include <memory>
#include <string>
namespace bvr_sim {
class Aircraft;
class SimulatedObject;
struct Terrain;
struct WeaponLaunchCheck {
    bool allowed=false;
    std::string reason, station;
    double range=0, angle=0;
};
// Own seeker acquisition, independent of aircraft radar, weapon cooldown and
// the HUD. Uses the existing missile acquisition cone/range and shared LOS.
WeaponLaunchCheck check_infrared_acquisition(const Aircraft& own,const std::string& weapon,
    const std::shared_ptr<SimulatedObject>& target);
std::shared_ptr<SimulatedObject> acquire_infrared_target(const Aircraft& own,const std::string& weapon,
    const Terrain& terrain,const std::string& preferred="");
WeaponLaunchCheck check_weapon_launch(const Aircraft& own,const std::string& weapon,
    const std::shared_ptr<SimulatedObject>& target,const std::string& station="");
bool launch_weapon(Aircraft& own,const std::string& weapon,const std::shared_ptr<SimulatedObject>& target,
    const std::string& station="");
bool release_bomb(Aircraft& own,const std::string& weapon,std::shared_ptr<const Terrain> environment,
    const std::string& station="");
}
