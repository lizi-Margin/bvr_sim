#include "weapon_factory.hxx"
#include "simulator/missile/aim120c.hxx"
#include "simulator/missile/mmodelA.hxx"
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

WeaponFactory::WeaponModelType WeaponFactory::parse_weapon_name(const std::string& weapon_name) noexcept {
    if (weapon_name.empty()) {
        return WeaponModelType::Unknown;
    }
    const static std::map<std::string, WeaponModelType> MAP = {
        {"AIM-120", WeaponModelType::AIM120C},
        {"AIM-120C", WeaponModelType::AIM120C},
        {"AIM-120C5", WeaponModelType::AIM120C},
        {"AIM-120C7", WeaponModelType::AIM120C},
        {"AIM-120C-MModelA", WeaponModelType::MModelA},
        {"AIM-120C-MModelA-Poor", WeaponModelType::MModelA},
        {"AIM-9", WeaponModelType::MModelA},
        {"AIM-9M", WeaponModelType::MModelA},
        {"AIM-9M-Omni", WeaponModelType::MModelA},
    };

    auto it = MAP.find(weapon_name);
    if (it == MAP.end()) {
        return WeaponModelType::Unknown;
    }
    return it->second;
}

std::shared_ptr<Missile> WeaponFactory::create_missile(
    const std::string& weapon_name,
    const std::shared_ptr<SimulatedObject>& parent,
    const std::shared_ptr<SimulatedObject>& target
) noexcept {
    WeaponModelType type = parse_weapon_name(weapon_name);
    const std::string& uid = parent->uid + parent->get_new_uuid();
    TeamColor color = parent->color;
    std::shared_ptr<SimulatedObject> friend_obj = parent->partners.size() > 0 ? parent->partners[0] : nullptr;
    double dt = parent->dt;
    std::optional<double> t_thrust_override = std::nullopt;

    switch (type) {
        case WeaponModelType::AIM120C:
            return std::make_shared<AIM120C>(
                uid,
                weapon_name,
                color,
                parent,
                friend_obj,
                target,
                dt,
                t_thrust_override
            );

        case WeaponModelType::MModelA:
            return std::make_shared<MModelA>(
                uid,
                weapon_name,
                color,
                parent,
                friend_obj,
                target,
                dt
            );

        case WeaponModelType::Unknown:
        default:
            return nullptr;
    }
}

}
