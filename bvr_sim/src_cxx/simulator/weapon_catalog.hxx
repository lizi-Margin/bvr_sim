#pragma once
#include <array>
#include <map>
#include <string>
#include <vector>

namespace bvr_sim {
// Developer-authored definitions. Players select IDs, never model backends or files.
struct WeaponDefinition {
    std::string id, name, category, seeker, description;
    std::string backend, parameter_file;
    bool selectable = false;
};
struct StationDefinition {
    std::string id, name, mirror;
    std::array<double, 2> diagram{}; // schematic UI coordinates, NOT physical launch offsets
    std::vector<std::string> weapons;
};
struct AircraftStations {
    std::string aircraft, source, limitations;
    std::vector<StationDefinition> stations;
    std::map<std::string, std::map<std::string, std::string>> presets;
};
using LoadoutSpec = std::map<std::string, std::string>;
const std::vector<WeaponDefinition>& weapon_catalog();
const WeaponDefinition* find_weapon(const std::string& id) noexcept;
std::vector<WeaponDefinition> selectable_weapons();
AircraftStations aircraft_stations(const std::string& aircraft);
std::vector<std::string> validate_loadout(const std::string& aircraft, const LoadoutSpec& loadout);
LoadoutSpec loadout_preset(const std::string& aircraft, const std::string& preset);
} // namespace bvr_sim
