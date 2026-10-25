#include "weapon_launch.hxx"
#include "weapon_catalog.hxx"
#include "weapon_factory.hxx"
#include "aircraft/base.hxx"
#include "aircraft/fighter.hxx"
#include "missile/base.hxx"
#include "bomb/mk82.hxx"
#include "param_store.hxx"
#include "resource_paths.hxx"
#include "so_pool.hxx"
#include "global_config.hxx"
#include <algorithm>
#include <cmath>
namespace bvr_sim {
bool release_bomb(Aircraft& own,const std::string& weapon,std::shared_ptr<const Terrain> environment,
    const std::string& station) {
    const auto* d=find_weapon(weapon);
    if(!own.is_alive||!environment||!d||d->category!="bomb")return false;
    const auto mount=own.pylon_manager.find_station(weapon,station);
    if(mount.empty())return false;
    auto bomb=WeaponFactory::create_bomb(weapon,own.shared_from_this(),std::move(environment));
    if(!bomb||!own.pylon_manager.consume(mount,weapon))return false;
    SOPool::instance().add(bomb);return true;
}
WeaponLaunchCheck check_weapon_launch(const Aircraft& own,const std::string& weapon,
    const std::shared_ptr<SimulatedObject>& target,const std::string& station) {
    WeaponLaunchCheck r;
    const auto reject=[&](const std::string& reason){r.reason=reason;return r;};
    const auto* definition=find_weapon(weapon);
    if(!definition||definition->category!="missile")return reject("Unknown missile");
    if(!own.is_alive||!target||!target->is_alive||target->Type!=SOT::Aircraft||target->color==own.color)
        return reject("A live hostile aircraft is required");
    r.station=own.pylon_manager.find_station(weapon,station);
    if(r.station.empty())return reject("Selected weapon is not mounted on this station");
    if(!own.can_shoot())return reject("Weapon cooling down");
    double dot=0;
    const auto rpy=own.get_rpy();
    const std::array<double,3> nose={std::cos(rpy[1])*std::cos(rpy[2]),std::cos(rpy[1])*std::sin(rpy[2]),std::sin(rpy[1])};
    for(int i=0;i<3;++i){const double d=target->position[i]-own.position[i];r.range+=d*d;dot+=d*nose[i];}
    r.range=std::sqrt(r.range);
    if(r.range<1)return reject("Target too close");
    r.angle=std::acos(std::clamp(dot/r.range,-1.,1.));
    if(definition->seeker=="infrared") {
        // Existing MModelA acquisition cone/range approximation. No heat/flare model is implied.
        static std::map<std::string,ParamStore> profiles;
        auto it=profiles.find(weapon);
        if(it==profiles.end())it=profiles.emplace(weapon,ParamStore::from_file(resource_paths::get_resource_path(definition->parameter_file).string())).first;
        const auto& p=it->second;
        if(r.range>p.get_double_("search_range"))return reject("IR target outside acquisition range");
        if(r.angle>p.get_double_("search_fov"))return reject("IR seeker is not on target");
    } else {
        if(!own.can_shoot_enm(target))return reject("Radar contact is required");
        if(r.angle>1.0471975512)return reject("Target outside launch cone");
    }
    r.allowed=true;r.reason="Ready";return r;
}
bool launch_weapon(Aircraft& own,const std::string& weapon,const std::shared_ptr<SimulatedObject>& target,
    const std::string& station) {
    const auto check=check_weapon_launch(own,weapon,target,station);
    if(!check.allowed)return false;
    auto missile=WeaponFactory::create_missile(weapon,own.shared_from_this(),target);
    if(!missile)return false;
    // Construct first. Creation failure must not consume an attached weapon.
    if(!own.pylon_manager.consume(check.station,weapon))return false;
    own.launched_missiles.push_back(missile);SOPool::instance().add(missile);
    if(auto aircraft=std::dynamic_pointer_cast<Aircraft>(target))aircraft->under_missiles.push_back(missile);
    if(auto fighter=dynamic_cast<Fighter*>(&own))fighter->last_shoot_time=cfg::sim_time;
    return true;
}
}
