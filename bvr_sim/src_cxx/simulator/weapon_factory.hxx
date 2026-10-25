#pragma once

#include "simulator/missile/base.hxx"
#include "simulator/missile/aim120c.hxx"
#include "simulator/missile/mmodelA.hxx"
#include <string>
#include <memory>
#include <cctype>
#include <algorithm>

namespace bvr_sim {

class SimulatedObject;
class Mk82Bomb;
struct Terrain;

class WeaponFactory {
public:
    enum class WeaponModelType {
        Unknown,
        AIM120C,
        MModelA
    };

    static WeaponModelType parse_weapon_name(const std::string& weapon_name) noexcept;
    static std::shared_ptr<Mk82Bomb> create_bomb(const std::string& weapon_name,
        const std::shared_ptr<SimulatedObject>& parent,std::shared_ptr<const Terrain> environment);

    static std::shared_ptr<Missile> create_missile(
        const std::string& weapon_name,
        const std::shared_ptr<SimulatedObject>& parent,
        const std::shared_ptr<SimulatedObject>& target
    ) noexcept;
};

}
