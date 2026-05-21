#include "sensor_manager.hxx"
#include "base.hxx"
#include "../data_obj.hxx"

namespace bvr_sim {

SensorManager::SensorManager(SimulatedObject* owner_) noexcept
    : owner(owner_) {
}

bool SensorManager::add_sensor(const std::string& name, const std::shared_ptr<SensorBase>& sensor) noexcept {
    if (!sensor || sensors.find(name) != sensors.end()) {
        return false;
    }
    sensors[name] = sensor;
    return true;
}

std::shared_ptr<SensorBase> SensorManager::get_sensor(const std::string& name) const noexcept {
    auto it = sensors.find(name);
    if (it == sensors.end()) {
        return nullptr;
    }
    return it->second;
}

void SensorManager::update_all() noexcept {
    for (auto& [name, sensor] : sensors) {
        if (sensor) {
            sensor->update();
        }
    }
    rebuild_tracks();
}

void SensorManager::rebuild_tracks() noexcept {
    tracks.clear();

    for (const auto& [sensor_name, sensor] : sensors) {
        if (!sensor) {
            continue;
        }

        const auto level = sensor->get_detection_level();
        for (const auto& [uid, data_obj] : sensor->get_data()) {
            if (!data_obj) {
                continue;
            }

            auto& track = tracks[uid];
            if (track.uid.empty()) {
                track.uid = uid;
                track.source = data_obj->source;
            }
            track.observations_by_sensor[sensor_name] = data_obj;

            if (static_cast<int>(level) > static_cast<int>(track.best_level)) {
                track.best_level = level;
                track.best_observation = data_obj;
                track.best_sensor_name = sensor_name;
                track.source = data_obj->source;
            }
        }
    }
}

void SensorManager::clear() noexcept {
    for (auto& [name, sensor] : sensors) {
        if (sensor) {
            sensor->clean_up();
        }
    }
    sensors.clear();
    tracks.clear();
}

const SensorTrack* SensorManager::get_track(const std::string& uid) const noexcept {
    auto it = tracks.find(uid);
    if (it == tracks.end()) {
        return nullptr;
    }
    return &it->second;
}

std::shared_ptr<DataObj> SensorManager::get_best_observation(const std::string& uid) const noexcept {
    const auto* track = get_track(uid);
    if (!track) {
        return nullptr;
    }
    return track->best_observation;
}

}
