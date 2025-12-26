#pragma once

#include <string>
#include <map>
#include <iostream>

namespace bvr_sim {

class PylonManager {
private:
    std::map<std::string, std::string> pylon_mounts;

    bool frozen;
    std::map<std::string, std::string> pylon_mounts_frozen;

    // Check if weapon_name matches query prefix
    bool weapon_matches(const std::string& weapon_name, const std::string& query) const noexcept;

public:
    PylonManager() : frozen(false) {}
    ~PylonManager() noexcept = default;

    // Set weapon on specific pylon
    void add_weapon(const std::string& pylon_name, const std::string& weapon_name) noexcept;
    // Freeze pylon mounts
    void freeze() noexcept;

    // Count frozen max weapons of specific type (with prefix matching)
    int num_frozen_weapons(const std::string& weapon_query) const noexcept;
    // Count remaining weapons of specific type (with prefix matching)
    int num_left_weapons(const std::string& weapon_query) const noexcept;

    // Release weapon of specific type (with prefix matching)
    bool release_weapon(const std::string& weapon_query) noexcept;

    // Get all pylon mounts
    const std::map<std::string, std::string>& get_all_mounts() const noexcept { return pylon_mounts; }
};

}