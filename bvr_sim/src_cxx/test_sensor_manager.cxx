#include "test_main.hxx"
#include "simulator/sense/sensor_manager.hxx"
#include "simulator/sense/base.hxx"
#include "simulator/simulator.hxx"
#include "simulator/data_obj.hxx"

using namespace bvr_sim;

namespace {

class DummyObject : public SimulatedObject {
public:
    DummyObject(const std::string& uid, TeamColor color)
        : SimulatedObject(uid, color, {0.0, 0.0, 0.0}, {1.0, 0.0, 0.0}, 0.1, SOT::Aircraft) {
    }

    void step() override {
    }

    std::string log() noexcept override {
        return "";
    }
};

class DummySensor : public SensorBase {
private:
    SensorDetectionLevel level;

public:
    explicit DummySensor(SensorDetectionLevel level_)
        : SensorBase(nullptr), level(level_) {
    }

    void set_detection(const std::shared_ptr<SimulatedObject>& source) {
        data_dict[source->uid] = std::make_shared<DataObj>(source);
    }

    void update() override {
    }

    std::string log_suffix() const noexcept override {
        return "";
    }

    SensorDetectionLevel get_detection_level() const noexcept override {
        return level;
    }
};

}

TEST(SensorManager, KeepsHighestLevelTrackPerTarget) {
    auto owner = std::make_shared<DummyObject>("owner", TeamColor::Blue);
    auto target = std::make_shared<DummyObject>("target", TeamColor::Red);
    auto detection_sensor = std::make_shared<DummySensor>(SensorDetectionLevel::Detection);
    auto tracking_sensor = std::make_shared<DummySensor>(SensorDetectionLevel::Tracking);

    detection_sensor->set_detection(target);
    tracking_sensor->set_detection(target);

    ASSERT(owner->add_sensor("detection", detection_sensor));
    ASSERT(owner->add_sensor("tracking", tracking_sensor));

    owner->update_sensors();

    const auto* track = owner->sensor_manager().get_track("target");
    ASSERT(track != nullptr);
    ASSERT(static_cast<int>(track->best_level) == static_cast<int>(SensorDetectionLevel::Tracking));
    ASSERT(track->best_sensor_name == "tracking");
    ASSERT(track->best_observation != nullptr);
    ASSERT(track->observations_by_sensor.size() == 2);
}

TEST(SensorNoise, SeedReplaysNonzeroPositionAndVelocityNoise) {
    auto source=std::make_shared<DummyObject>("noise_source",TeamColor::Red);
    DataObj::set_noise_seed(7);
    DataObj a(source,200,3), b(source,200,3);
    ASSERT(a.position != source->position);
    ASSERT(a.velocity != source->velocity);
    ASSERT(a.position != b.position);
    DataObj::set_noise_seed(7);
    DataObj again(source,200,3), second(source,200,3);
    ASSERT(a.position == again.position); ASSERT(a.velocity == again.velocity);
    ASSERT(b.position == second.position); ASSERT(b.velocity == second.velocity);
    DataObj::set_noise_seed(8);
    DataObj changed(source,200,3);
    ASSERT(a.position != changed.position);
    DataObj::set_noise_seed(std::nullopt);
}
