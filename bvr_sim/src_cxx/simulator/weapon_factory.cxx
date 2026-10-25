#include "weapon_factory.hxx"
#include "simulator/missile/aim120c.hxx"
#include "simulator/missile/mmodelA.hxx"
#include "weapon_catalog.hxx"
#include "bomb/mk82.hxx"
#include <stdexcept>

namespace bvr_sim {

std::shared_ptr<Mk82Bomb> WeaponFactory::create_bomb(const std::string& name,
    const std::shared_ptr<SimulatedObject>& parent,std::shared_ptr<const Terrain> environment) {
    const auto* d=find_weapon(name);
    if(!d||d->category!="bomb"||d->backend!="mk82"||!parent||!environment)return nullptr;
    return std::make_shared<Mk82Bomb>(parent->uid+parent->get_new_uuid(),*parent,std::move(environment),parent->dt);
}

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
    const auto* definition=find_weapon(weapon_name);
    if(!definition)return WeaponModelType::Unknown;
    if(definition->backend=="aim120c")return WeaponModelType::AIM120C;
    if(definition->backend=="mmodelA")return WeaponModelType::MModelA;
    return WeaponModelType::Unknown;
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
