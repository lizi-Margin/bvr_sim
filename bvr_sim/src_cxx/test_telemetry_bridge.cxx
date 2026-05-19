#include "test_main.hxx"
#include "global_config.hxx"
#include "support/SL.hxx"
#include "so_pool.hxx"
#include "telemetry/telemetry_bridge.hxx"

#include <chrono>
#include <thread>

namespace {

void ensure_test_logger() {
    static bool initialized = false;
    if (!initialized) {
        SL::init_instance("test_telemetry_bridge.log", false);
        initialized = true;
    }
}

class DummyGroundObject : public bvr_sim::SimulatedObject {
public:
    DummyGroundObject()
        : bvr_sim::SimulatedObject(
            "dummy_ground",
            bvr_sim::TeamColor::Blue,
            {10.0, 20.0, 0.0},
            {0.0, 0.0, 0.0},
            0.1,
            bvr_sim::SOT::GroundUnit) {
        write_register();
    }

    void step() override {
    }

    std::string log() noexcept override {
        return "";
    }
};

class BrokenRegisterObject : public bvr_sim::SimulatedObject {
public:
    BrokenRegisterObject()
        : bvr_sim::SimulatedObject(
            "broken_ground",
            bvr_sim::TeamColor::Blue,
            {0.0, 0.0, 0.0},
            {0.0, 0.0, 0.0},
            0.1,
            bvr_sim::SOT::GroundUnit) {
        write_register();
        get_mutable_register().pop("uid");
    }

    void step() override {
    }

    std::string log() noexcept override {
        return "";
    }

private:
    bvr_sim::Register& get_mutable_register() {
        return const_cast<bvr_sim::Register&>(get_register());
    }
};

}

TEST(TelemetryBridge, StartAndStopLifecycle) {
    ensure_test_logger();
    bvr_sim::TelemetryBridge bridge;
    ASSERT(!bridge.is_running());

    bridge.start();
    ASSERT(bridge.is_running());

    bridge.stop();
    ASSERT(!bridge.is_running());
}

TEST(TelemetryBridge, PublishesSnapshotFromSOPool) {
    ensure_test_logger();
    bvr_sim::SOPool::instance().clear();
    bvr_sim::cfg::dt = 0.1;
    bvr_sim::cfg::sim_time = 1.5;

    auto object = std::make_shared<DummyGroundObject>();
    bvr_sim::SOPool::instance().add(object);

    bvr_sim::TelemetryBridge bridge;
    bridge.start();
    std::this_thread::sleep_for(std::chrono::milliseconds(30));

    auto snapshot = bridge.get_latest_snapshot();

    bridge.stop();
    bvr_sim::SOPool::instance().clear();

    ASSERT(snapshot != nullptr);
    ASSERT_EQ(snapshot->sim_time, 1.5);
    ASSERT_EQ(snapshot->dt, 0.1);
    ASSERT_EQ(static_cast<double>(snapshot->objects.size()), 1.0);
    ASSERT(snapshot->objects[0].uid == "dummy_ground");
}

TEST(TelemetryBridge, SkipsObjectWhoseRegisterLostUidDuringCleanup) {
    ensure_test_logger();
    bvr_sim::SOPool::instance().clear();
    bvr_sim::cfg::dt = 0.1;
    bvr_sim::cfg::sim_time = 2.0;

    auto valid_object = std::make_shared<DummyGroundObject>();
    auto broken_object = std::make_shared<BrokenRegisterObject>();
    bvr_sim::SOPool::instance().add(valid_object);
    bvr_sim::SOPool::instance().add(broken_object);

    bvr_sim::TelemetryBridge bridge;
    bridge.refresh_once();
    auto snapshot = bridge.get_latest_snapshot();

    bvr_sim::SOPool::instance().clear();

    ASSERT(snapshot != nullptr);
    ASSERT_EQ(static_cast<double>(snapshot->objects.size()), 1.0);
    ASSERT(snapshot->objects[0].uid == "dummy_ground");
}
