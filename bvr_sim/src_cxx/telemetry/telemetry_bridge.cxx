#include "telemetry_bridge.hxx"

namespace bvr_sim {

TelemetryBridge::TelemetryBridge()
    : running_(false),
      latest_snapshot_(std::make_shared<WorldSnapshot>()) {
}

void TelemetryBridge::start() noexcept {
    running_ = true;
}

void TelemetryBridge::stop() noexcept {
    running_ = false;
}

bool TelemetryBridge::is_running() const noexcept {
    return running_.load();
}

std::shared_ptr<const WorldSnapshot> TelemetryBridge::get_latest_snapshot() const noexcept {
    return latest_snapshot_;
}

void TelemetryBridge::set_latest_snapshot(std::shared_ptr<const WorldSnapshot> snapshot) noexcept {
    latest_snapshot_ = std::move(snapshot);
}

void TelemetryBridge::submit_command(const TelemetryCommand& command) {
    command_queue_.push(command);
}

std::optional<TelemetryCommand> TelemetryBridge::try_pop_command() {
    return command_queue_.try_pop();
}

}
