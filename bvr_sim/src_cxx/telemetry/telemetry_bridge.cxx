#include "telemetry_bridge.hxx"
#include "global_config.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "so_pool.hxx"

#include <chrono>

namespace bvr_sim {

TelemetryBridge::TelemetryBridge()
    : running_(false),
      latest_snapshot_(std::make_shared<WorldSnapshot>()) {
}

TelemetryBridge::~TelemetryBridge() {
    stop();
}

void TelemetryBridge::start() noexcept {
    if (running_.load()) {
        return;
    }
    running_ = true;
    sample_once();
    worker_thread_ = std::thread(&TelemetryBridge::run_loop, this);
}

void TelemetryBridge::stop() noexcept {
    if (!running_.load()) {
        return;
    }
    running_ = false;
    if (worker_thread_.joinable()) {
        worker_thread_.join();
    }
}

bool TelemetryBridge::is_running() const noexcept {
    return running_.load();
}

void TelemetryBridge::refresh_once() noexcept {
    sample_once();
}

std::shared_ptr<const WorldSnapshot> TelemetryBridge::get_latest_snapshot() const noexcept {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    return latest_snapshot_;
}

void TelemetryBridge::set_latest_snapshot(std::shared_ptr<const WorldSnapshot> snapshot) noexcept {
    std::lock_guard<std::mutex> lock(snapshot_mutex_);
    latest_snapshot_ = std::move(snapshot);
}

void TelemetryBridge::submit_command(const TelemetryCommand& command) {
    command_queue_.push(command);
}

std::optional<TelemetryCommand> TelemetryBridge::try_pop_command() {
    return command_queue_.try_pop();
}

void TelemetryBridge::run_loop() noexcept {
    while (running_.load()) {
        sample_once();
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void TelemetryBridge::sample_once() noexcept {
    auto snapshot = std::make_shared<WorldSnapshot>(
        TelemetrySnapshotBuilder::make_empty_snapshot(cfg::sim_time, cfg::dt, running_.load(), false));

    for (const auto& object : SOPool::instance().get_all()) {
        if (!object) {
            colorful::printHONG("[TelemetryBridge] null object found in SOPool during sampling");
            SL::get().print("[TelemetryBridge] null object found in SOPool during sampling");
            check(false, "TelemetryBridge::sample_once encountered null object in SOPool");
        }
        snapshot->objects.push_back(TelemetrySnapshotBuilder::build_object_state(object->get_register()));
    }

    set_latest_snapshot(snapshot);
}

}
