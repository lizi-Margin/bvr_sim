#include "pylon_manager.hxx"
#include "support/SL.hxx"
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

bool PylonManager::weapon_matches_exact(const std::string& weapon_name, const std::string& query) const noexcept {
    if (weapon_name.empty()) {
        return false;
    }
    if (query.empty()) {
        return true; // make empty query get all weapon num (except "")
    }
    return weapon_name == query;
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

int PylonManager::num_frozen_weapons_exact(const std::string& weapon_query) const noexcept {
    if (!frozen) {
        std::cout << "[PylonManager] Error: PylonManager is not frozen, cannot count frozen weapons" << std::endl;
        SL::get().print("[PylonManager] Error: PylonManager is not frozen, cannot count frozen weapons");
        return 0;
    }

    int count = 0;
    for (const auto& [pylon, weapon] : pylon_mounts_frozen) {
        if (weapon_matches_exact(weapon, weapon_query)) {
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

int PylonManager::num_left_weapons_exact(const std::string& weapon_query) const noexcept {
    int count = 0;
    for (const auto& [pylon, weapon] : pylon_mounts) {
        if (weapon_matches_exact(weapon, weapon_query)) {
            count++;
        }
    }
    return count;
}

std::string PylonManager::release_weapon(const std::string& weapon_query) noexcept {
    if (weapon_query.empty()) {
        std::cout << "[PylonManager] Warning: Cannot release weapon '" << weapon_query
                << "' - no such weapon mounted on any pylon" << std::endl;
        return "";
    }

    // Find first pylon with the specified weapon (using prefix matching)
    for (auto& [pylon, weapon] : pylon_mounts) {
        if (weapon_matches(weapon, weapon_query)) {
            std::string released_weapon = std::move(weapon);
            weapon = "";  // Clear the pylon
            check(!released_weapon.empty(), "released_weapon.empty() == true");
            return released_weapon;
        }
    }

    std::cout << "[PylonManager] Warning: Cannot release weapon '" << weapon_query
              << "' - no such weapon mounted on any pylon" << std::endl;
    return "";
}

}
