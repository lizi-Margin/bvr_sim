#include "core_aircraft.hxx"
#include "unit_factory.hxx"
#include "aircraft/fighter.hxx"
#include "aircraft/catalog.hxx"
#include "missile/base.hxx"
#include "bomb/mk82.hxx"
#include "data_obj.hxx"
#include "global_config.hxx"
#include "bsl_pool.hxx"
#include "so_pool.hxx"
#include "resource_paths.hxx"
#include <cmath>
#include <stdexcept>
namespace bvr_sim {
void reset_core_world(std::uint32_t seed) {
    BaselinePool::instance().clear();SOPool::instance().clear();cfg::sim_time=0;
    SimulatedObject::set_uuid_seed(seed);DataObj::set_noise_seed(seed);
}
void spawn_core_aircraft(const AircraftSpawnSpec& s) {
    aircraft_definition(s.model);
    const auto errors=validate_loadout(s.model,s.loadout);
    if(!errors.empty())throw std::invalid_argument(errors.front());
    if(s.uid.empty()||SOPool::instance().has(s.uid))throw std::invalid_argument("Aircraft UID must be unique and nonempty");
    if(s.team!="blue"&&s.team!="red")throw std::invalid_argument("Team must be blue or red");
    if(s.fdm!="simple"&&s.fdm!="jsbsim"&&s.fdm!="yasim")throw std::invalid_argument("Invalid FDM");
    if(s.fdm=="yasim"&&!std::filesystem::is_regular_file(resource_paths::get_resource_path("aircraft/"+s.model+"/fdm.xml")))
        throw std::invalid_argument("No YASim source for this aircraft");
    for(auto v:s.position)if(!std::isfinite(v))throw std::invalid_argument("Invalid spawn position");
    double speed=0;for(auto v:s.velocity){if(!std::isfinite(v))throw std::invalid_argument("Invalid spawn velocity");speed+=v*v;}
    if(s.position[2]<=0||speed<1)throw std::invalid_argument("Aircraft must spawn airborne with nonzero velocity");
    json::JSON j=json::Object();j["unit_spec"]=json::String(s.model);j["color"]=json::String(s.team);
    j["fdm_type"]=json::String(s.fdm);j["radar_type"]=json::String(s.radar?"radar":"none");
    j["position"]=json::Array(s.position[0],s.position[1],s.position[2]);
    j["velocity"]=json::Array(s.velocity[0],s.velocity[1],s.velocity[2]);
    j["pylon_mounts"]=json::Object();for(const auto& [id,w]:s.loadout)j["pylon_mounts"][id]=json::String(w);
    auto aircraft=UnitFactory::create_unit(s.uid,j);
    if(!aircraft)throw std::runtime_error("Cannot create aircraft: "+s.model);
    SOPool::instance().add(aircraft);
}
std::vector<CoreObjectState> core_objects() {
    std::vector<CoreObjectState> result;
    for(const auto& o:SOPool::instance().get_all_ever_existed()) {
        CoreObjectState s;s.uid=o->uid;s.position=o->position;s.velocity=o->velocity;s.orientation=o->get_rpy();s.alive=o->is_alive;
        if(auto a=std::dynamic_pointer_cast<Aircraft>(o)){s.kind="aircraft";s.model=a->aircraft_model;s.health=a->bloods;s.pylons=a->pylon_manager.get_all_mounts();}
        else if(auto m=std::dynamic_pointer_cast<Missile>(o)){s.kind="missile";s.model=m->missile_model;s.owner=m->parent?m->parent->uid:"";s.target=m->target?m->target->uid:"";s.done=m->is_done;s.success=m->is_success;s.seeker_active=m->radar_on||m->ir_on;}
        else if(auto b=std::dynamic_pointer_cast<Mk82Bomb>(o)){s.kind="bomb";s.model="Mk-82";s.owner=b->owner;s.done=b->impacted;}
        else if(auto ground=std::dynamic_pointer_cast<GroundUnit>(o)){s.kind="ground";s.model=ground->model_id();s.health=ground->health();}
        else continue;
        result.push_back(std::move(s));
    }
    return result;
}
std::string core_acquire_ir_target(const std::string& uid,const std::string& weapon,const Terrain& terrain) {
    auto own=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(uid));
    auto target=own?acquire_infrared_target(*own,weapon,terrain):nullptr;
    return target?target->uid:"";
}
WeaponLaunchCheck core_check_launch(const std::string& uid,const std::string& weapon,const std::string& target,const std::string& station) {
    auto a=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(uid));
    if(!a)return {false,"Unknown aircraft","",0,0};
    return check_weapon_launch(*a,weapon,SOPool::instance().get(target),station);
}
bool core_launch_weapon(const std::string& uid,const std::string& weapon,const std::string& target,const std::string& station) {
    auto a=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(uid));
    return a&&launch_weapon(*a,weapon,SOPool::instance().get(target),station);
}
bool core_release_weapon(const std::string& uid,const std::string& weapon,std::shared_ptr<const Terrain> terrain,const std::string& station) {
    auto a=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(uid));
    return a&&release_bomb(*a,weapon,std::move(terrain),station);
}
std::optional<std::array<double,3>> core_predict_bomb(const std::string& uid,const Terrain& terrain) {
    auto a=std::dynamic_pointer_cast<Aircraft>(SOPool::instance().get(uid));
    if(!a||!a->is_alive)return std::nullopt;
    return predict_ballistic_impact(a->position,a->velocity,terrain,a->dt,6000,true);
}
}
