#include "weapon_catalog.hxx"
#include "resource_paths.hxx"
#include "support/json.hpp"
#include <algorithm>
#include <fstream>
#include <stdexcept>

namespace bvr_sim {
namespace {
json::JSON read_catalog(const std::string& file) {
    std::ifstream input(resource_paths::get_resource_path(file));
    if (!input) throw std::runtime_error("Missing developer catalog: " + file);
    return json::JSON::Load(std::string(std::istreambuf_iterator<char>(input), {}));
}
}
const std::vector<WeaponDefinition>& weapon_catalog() {
    static const auto entries = [] {
        std::vector<WeaponDefinition> result;
        const auto document=read_catalog("weapon_catalog.json");
        for (const auto& w : document.at("weapons").ArrayRange()) {
            WeaponDefinition d;
            d.id=w.at("id").ToString();d.name=w.at("name").ToString();
            d.category=w.at("category").ToString();d.seeker=w.at("seeker").ToString();
            d.description=w.at("description").ToString();d.backend=w.at("backend").ToString();
            d.selectable=w.at("selectable").ToBool();
            if(w.hasKey("parameter_file"))d.parameter_file=w.at("parameter_file").ToString();
            if (std::any_of(result.begin(),result.end(),[&](const auto& x){return x.id==d.id;}))
                throw std::runtime_error("Duplicate weapon ID: "+d.id);
            result.push_back(std::move(d));
        }
        return result;
    }();
    return entries;
}
const WeaponDefinition* find_weapon(const std::string& id) noexcept {
    for(const auto& w:weapon_catalog())if(w.id==id)return &w;
    return nullptr;
}
std::vector<WeaponDefinition> selectable_weapons() {
    std::vector<WeaponDefinition> result;
    for(const auto& w:weapon_catalog())if(w.selectable)result.push_back(w);
    return result;
}
AircraftStations aircraft_stations(const std::string& aircraft) {
    static const auto definitions=[] {
        std::map<std::string,AircraftStations> result;
        const auto document=read_catalog("aircraft_stations.json");
        for(const auto& a:document.at("aircraft").ArrayRange()) {
            AircraftStations d;d.aircraft=a.at("id").ToString();
            d.source=a.at("source").ToString();d.limitations=a.at("limitations").ToString();
            for(const auto& s:a.at("stations").ArrayRange()) {
                StationDefinition p;p.id=s.at("id").ToString();p.name=s.at("name").ToString();
                p.mirror=s.at("mirror").ToString();
                p.diagram={s.at("diagram").at(0).ToFloat(),s.at("diagram").at(1).ToFloat()};
                for(const auto& w:s.at("weapons").ArrayRange()) {
                    const auto id=w.ToString();const auto* def=find_weapon(id);
                    if(!def||!def->selectable)throw std::runtime_error("Invalid station weapon: "+id);
                    p.weapons.push_back(id);
                }
                if(std::any_of(d.stations.begin(),d.stations.end(),[&](const auto& x){return x.id==p.id;}))
                    throw std::runtime_error("Duplicate station: "+p.id);
                d.stations.push_back(std::move(p));
            }
            for(const auto& [name,mounts]:a.at("presets").ObjectRange()) {
                auto& preset=d.presets[name]; // retain intentionally empty/clean presets
                for(const auto& [station,weapon]:mounts.ObjectRange())preset[station]=weapon.ToString();
            }
            result.emplace(d.aircraft,std::move(d));
        }
        return result;
    }();
    auto found=definitions.find(aircraft);
    if(found==definitions.end())return {aircraft,"","No developer-authored weapon stations; unarmed only.",{},{{"unarmed",{}}}};
    return found->second;
}
std::vector<std::string> validate_loadout(const std::string& aircraft,const LoadoutSpec& loadout) {
    const auto d=aircraft_stations(aircraft);std::vector<std::string> errors;
    for(const auto& [id,weapon]:loadout) {
        auto s=std::find_if(d.stations.begin(),d.stations.end(),[&](const auto& x){return x.id==id;});
        if(s==d.stations.end()){errors.push_back("Unknown station: "+id);continue;}
        if(weapon.empty())continue;
        if(std::find(s->weapons.begin(),s->weapons.end(),weapon)==s->weapons.end())
            errors.push_back(id+": incompatible weapon "+weapon);
    }
    return errors;
}
LoadoutSpec loadout_preset(const std::string& aircraft,const std::string& preset) {
    auto d=aircraft_stations(aircraft);auto p=d.presets.find(preset);
    if(p==d.presets.end())throw std::invalid_argument("Unknown loadout preset: "+preset);
    const auto errors=validate_loadout(aircraft,p->second);
    if(!errors.empty())throw std::runtime_error(errors.front());
    return p->second;
}
} // namespace bvr_sim
