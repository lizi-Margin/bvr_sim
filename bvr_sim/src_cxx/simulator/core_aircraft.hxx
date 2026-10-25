#pragma once
#include "weapon_catalog.hxx"
#include "weapon_launch.hxx"
#include "environment.hxx"
#include <cstdint>
namespace bvr_sim {
struct AircraftSpawnSpec {
    std::string uid, model="F16", team="blue", fdm="simple";
    std::array<double,3> position{0,0,3000},velocity{250,0,0};
    LoadoutSpec loadout;
    bool radar=true;
};
struct CoreObjectState {
    std::string uid, kind, model, owner, target;
    std::array<double,3> position{},velocity{},orientation{};
    LoadoutSpec pylons;
    bool alive=false,done=false,success=false,seeker_active=false;
    double health=0;
};
void reset_core_world(std::uint32_t seed);
void spawn_core_aircraft(const AircraftSpawnSpec& spec);
std::vector<CoreObjectState> core_objects();
WeaponLaunchCheck core_check_launch(const std::string& uid,const std::string& weapon,const std::string& target,const std::string& station="");
bool core_launch_weapon(const std::string& uid,const std::string& weapon,const std::string& target,const std::string& station="");
bool core_release_weapon(const std::string& uid,const std::string& weapon,std::shared_ptr<const Terrain> terrain,const std::string& station="");
std::optional<std::array<double,3>> core_predict_bomb(const std::string& uid,const Terrain& terrain);
}
