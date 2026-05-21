#pragma once

#include <map>
#include <memory>
#include <string>

namespace bvr_sim {

class DataObj;
class SensorBase;
class SimulatedObject;

enum class SensorDetectionLevel {
    None = 0,
    Detection = 1,
    Localization = 2,
    Tracking = 3
};

struct SensorTrack {
    std::string uid;
    std::shared_ptr<SimulatedObject> source;
    std::map<std::string, std::shared_ptr<DataObj>> observations_by_sensor;
    std::shared_ptr<DataObj> best_observation;
    std::string best_sensor_name;
    SensorDetectionLevel best_level = SensorDetectionLevel::None;
};

class SensorManager {
private:
    SimulatedObject* owner;
    std::map<std::string, std::shared_ptr<SensorBase>> sensors;
    std::map<std::string, SensorTrack> tracks;

public:
    explicit SensorManager(SimulatedObject* owner_) noexcept;
    ~SensorManager() noexcept = default;

    bool add_sensor(const std::string& name, const std::shared_ptr<SensorBase>& sensor) noexcept;
    std::shared_ptr<SensorBase> get_sensor(const std::string& name) const noexcept;
    const std::map<std::string, std::shared_ptr<SensorBase>>& get_sensors() const noexcept { return sensors; }

    void update_all() noexcept;
    void rebuild_tracks() noexcept;
    void clear() noexcept;

    const std::map<std::string, SensorTrack>& get_tracks() const noexcept { return tracks; }
    const SensorTrack* get_track(const std::string& uid) const noexcept;
    std::shared_ptr<DataObj> get_best_observation(const std::string& uid) const noexcept;
};

}
