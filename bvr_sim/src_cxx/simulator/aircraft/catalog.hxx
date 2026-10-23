#pragma once
#include "resource_paths.hxx"
#include "support/json.hpp"
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>

namespace bvr_sim {
struct AircraftDefinition {
    std::string id, simulation_model, fdm_type, fdm_model;
    int max_missiles = 0, max_bombs = 0;
};
inline const std::map<std::string, AircraftDefinition> &aircraft_definitions() {
    static const auto catalog = [] {
        std::ifstream input(resource_paths::get_resource_path("aircraft_catalog.json"));
        if (!input)
            throw std::runtime_error("Missing core aircraft_catalog.json");
        auto document = json::JSON::Load(std::string(std::istreambuf_iterator<char>(input), {}));
        std::map<std::string, AircraftDefinition> result;
        for (const auto &item : document.at("aircraft").ArrayRange()) {
            AircraftDefinition a;
            a.id = item.at("id").ToString();
            a.simulation_model = item.at("simulation_model").ToString();
            a.fdm_type = item.at("fdm").at("type").ToString();
            a.fdm_model = item.at("fdm").at("model").ToString();
            a.max_missiles = item.at("max_missiles").ToInt();
            a.max_bombs = item.at("max_bombs").ToInt();
            result.emplace(a.id, a);
        }
        return result;
    }();
    return catalog;
}
inline AircraftDefinition aircraft_definition(const std::string &id, bool library = false) {
    if (library) {
        if (id.empty() || id.find("..") != std::string::npos || id.find_first_of("/\\:") != std::string::npos)
            throw std::invalid_argument("Invalid imported aircraft ID");
        const auto source = resource_paths::get_resource_path("aircraft/" + id + "/source.json");
        const auto fdm = resource_paths::get_resource_path("aircraft/" + id + "/fdm.xml");
        std::ifstream input(source);
        if (!input || !std::filesystem::is_regular_file(fdm))
            throw std::invalid_argument("Imported FDM is not prepared: " + id);
        auto data = json::JSON::Load(std::string(std::istreambuf_iterator<char>(input), {}));
        std::string type = data.at("fdm_type").ToString();
        if (type == "jsb")
            type = "jsbsim";
        if (type != "jsbsim" && type != "yasim")
            throw std::invalid_argument("Unsupported imported backend: " + type);
        return {id, id, type, id, 0, 0};
    }
    const auto &definitions = aircraft_definitions();
    auto found = definitions.find(id);
    if (found == definitions.end())
        throw std::invalid_argument("Aircraft is not in the game catalog: " + id);
    return found->second;
}
} // namespace bvr_sim
