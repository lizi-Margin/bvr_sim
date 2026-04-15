#pragma once

#include "telemetry_command_queue.hxx"
#include "telemetry_types.hxx"
#include <atomic>
#include <memory>

namespace bvr_sim {

class TelemetryBridge {
public:
    TelemetryBridge();

    void start() noexcept;
    void stop() noexcept;

    bool is_running() const noexcept;

    std::shared_ptr<const WorldSnapshot> get_latest_snapshot() const noexcept;
    void set_latest_snapshot(std::shared_ptr<const WorldSnapshot> snapshot) noexcept;

    void submit_command(const TelemetryCommand& command);
    std::optional<TelemetryCommand> try_pop_command();

private:
    std::atomic<bool> running_;
    std::shared_ptr<const WorldSnapshot> latest_snapshot_;
    TelemetryCommandQueue command_queue_;
};

}
