#include "pylon_manager.hxx"
#include "rubbish_can/SL.hxx"
#include <algorithm>

namespace bvr_sim {

bool PylonManager::weapon_matches(const std::string& weapon_name, const std::string& query) const noexcept {
    if (weapon_name.empty()) {
        return false;
    }
    if (query.empty() /*&& !weapon_name.empty()*/) {
        return true; // make empty query get all weapon num (except "")
    }

    // Check if weapon_name starts with query (prefix matching)
    // e.g., query "AIM-120C" matches "AIM-120C7"
    return weapon_name.substr(0, query.length()) == query;
}

void PylonManager::add_weapon(const std::string& pylon_name, const std::string& weapon_name) noexcept {
    if (frozen) {
        std::cout << "[PylonManager] Warning: PylonManager is frozen, cannot add weapon" << std::endl;
        return;
    }

    if (pylon_mounts.find(pylon_name) != pylon_mounts.end()) {
        if (pylon_mounts[pylon_name] != "") {
            std::cout << "[PylonManager] Warning: Pylon '" << pylon_name
                      << "' already has a weapon mounted" << std::endl;
            return;
        }
    }
    pylon_mounts[pylon_name] = weapon_name;
}

void PylonManager::freeze() noexcept {
    if (frozen) {
        std::cout << "[PylonManager] Warning: PylonManager is already frozen" << std::endl;
        SL::get().print("[PylonManager] Warning: PylonManager is already frozen");
        return;
    }
    frozen = true;
    SL::get().print("[PylonManager] start copy map");
    pylon_mounts_frozen = pylon_mounts;
    SL::get().print("[PylonManager] freeze() success");
}

// std::string PylonManager::get(const std::string& pylon_name) const noexcept {
//     auto it = pylon_mounts.find(pylon_name);
//     if (it != pylon_mounts.end()) {
//         return it->second;
//     }
//     return "";
// }

int PylonManager::num_frozen_weapons(const std::string& weapon_query) const noexcept {
    if (!frozen) {
        std::cout << "[PylonManager] Error: PylonManager is not frozen, cannot count frozen weapons" << std::endl;
        SL::get().print("[PylonManager] Error: PylonManager is not frozen, cannot count frozen weapons");
        return 0;
    }

    int count = 0;
    for (const auto& [pylon, weapon] : pylon_mounts_frozen) {
        if (weapon_matches(weapon, weapon_query)) {
            count++;
        }
    }
    return count;
}

int PylonManager::num_left_weapons(const std::string& weapon_query) const noexcept {
    int count = 0;
    for (const auto& [pylon, weapon] : pylon_mounts) {
        if (weapon_matches(weapon, weapon_query)) {
            count++;
        }
    }
    return count;
}

bool PylonManager::release_weapon(const std::string& weapon_query) noexcept {
    if (weapon_query.empty()) {
        std::cout << "[PylonManager] Warning: Cannot release weapon '" << weapon_query
                << "' - no such weapon mounted on any pylon" << std::endl;
        return false;
    }

    // Find first pylon with the specified weapon (using prefix matching)
    for (auto& [pylon, weapon] : pylon_mounts) {
        if (weapon_matches(weapon, weapon_query)) {
            weapon = "";  // Clear the pylon
            return true;
        }
    }

    std::cout << "[PylonManager] Warning: Cannot release weapon '" << weapon_query
              << "' - no such weapon mounted on any pylon" << std::endl;
    return false;
}

}