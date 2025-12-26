#include "weapon_factory.hxx"
#include "simulator/missile/aim120c.hxx"
#include <stdexcept>

namespace bvr_sim {

// std::string WeaponFactory::normalize_weapon_name(const std::string& weapon_name) noexcept {
//     std::string normalized = weapon_name;

//     std::transform(normalized.begin(), normalized.end(), normalized.begin(),
//                    [](unsigned char c) { return std::tolower(c); });

//     normalized.erase(std::remove(normalized.begin(), normalized.end(), '-'), normalized.end());
//     normalized.erase(std::remove(normalized.begin(), normalized.end(), ' '), normalized.end());

//     return normalized;
// }

WeaponFactory::WeaponType WeaponFactory::parse_weapon_name(const std::string& weapon_name) noexcept {
    if (weapon_name.empty()) {
        return WeaponType::Unknown;
    }
    const static std::map<std::string, WeaponType> MAP = {
        {"AIM-120", WeaponType::AIM120C},
        {"AIM-120C", WeaponType::AIM120C},
        {"AIM-120C5", WeaponType::AIM120C},
        {"AIM-120C7", WeaponType::AIM120C},
    };

    auto it = MAP.find(weapon_name);
    if (it == MAP.end()) {
        return WeaponType::Unknown;
    }
    return it->second;
}

std::shared_ptr<Missile> WeaponFactory::create_missile(
    const std::string& weapon_name,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& target
) noexcept {
    WeaponType type = parse_weapon_name(weapon_name);
    const std::string& uid = parent->uid + parent->get_new_uuid();
    TeamColor color = parent->color;
    std::shared_ptr<SimulatedObject> friend_obj = parent->partners.size() > 0 ? parent->partners[0] : nullptr;
    double dt = parent->dt;
    std::optional<double> t_thrust_override = std::nullopt;

    switch (type) {
        case WeaponType::AIM120C:
            return std::make_shared<AIM120C>(
                uid,
                color,
                parent,
                friend_obj,
                target,
                dt,
                t_thrust_override
            );

        case WeaponType::Unknown:
        default:
            return nullptr;
    }
}

}
