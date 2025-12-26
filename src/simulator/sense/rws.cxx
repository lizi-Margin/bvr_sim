#include "rws.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "../aircraft/base.hxx"
#include "../missile/base.hxx"

namespace bvr_sim {

RadarWarningSystem::RadarWarningSystem(
    const std::shared_ptr<Aircraft>& parent,
    double noise_std_position
) noexcept : SensorBase(parent),
    noise_std_position(noise_std_position),
    noise_std_velocity(0.0) {
}

void RadarWarningSystem::update() {
    data_dict.clear();

    for (const auto& enemy : parent->enemies) {
        if (!enemy->is_alive) {
            continue;
        }
        if (enemy->Type != SOT::Aircraft) {
            continue;
        }

        // Get enemy aircraft
        auto enemy_aircraft = std::dynamic_pointer_cast<Aircraft>(enemy);
        if (!enemy_aircraft) {
            colorful::printHONG("RWS: enemy dynamic cast failed");
            std::abort();
        }

        // Check if enemy's radar has locked onto parent
        if (!enemy_aircraft->radar) {
            continue;
        }

        // Check if parent is in enemy's lock list
        const auto& enemy_locks = enemy_aircraft->enemies_lock;
        bool parent_locked = false;
        for (const auto& locked_aircraft : enemy_locks) {
            if (locked_aircraft->uid == parent->uid) {
                parent_locked = true;
                break;
            }
        }

        if (parent_locked) {
            // Enemy radar is tracking us - detect via RWR
            auto warning_info = std::make_shared<DataObj>(
                enemy,
                noise_std_position,
                noise_std_velocity
            );
            data_dict[enemy->uid] = warning_info;
        }
    }
}

MissileWarningSystem::MissileWarningSystem(
    const std::shared_ptr<Aircraft>& parent,
    double noise_std_position
) noexcept : SensorBase(parent),
    noise_std_position(noise_std_position) {
}

void MissileWarningSystem::update() {
    data_dict.clear();

    // Filter for enemy missiles that are alive
    for (const auto& missile : parent->under_missiles) {
        if (!missile->is_alive) {
            continue;
        }
        if (!missile->radar_on) {
            continue;
        }
        if (missile->color == parent->color) {
            SL::get().print("[RWS] Warning: missile is from same team");
        }

        auto warning_info = std::make_shared<DataObj>(
            missile,
            noise_std_position,
            0.0  // MWS doesn't provide velocity
        );
        data_dict[missile->uid] = warning_info;
    }
}

}