#pragma once

#include "telemetry_command_queue.hxx"
#include "telemetry_snapshot_builder.hxx"
#include "telemetry_types.hxx"
#include <atomic>
#include <functional>
#include <mutex>
#include <memory>
#include <thread>

namespace bvr_sim {

class TelemetryBridge {
public:
    TelemetryBridge();
    ~TelemetryBridge();

    void start() noexcept;
    void stop() noexcept;

    bool is_running() const noexcept;
    void refresh_once() noexcept;

    std::shared_ptr<const WorldSnapshot> get_latest_snapshot() const noexcept;
    void set_latest_snapshot(std::shared_ptr<const WorldSnapshot> snapshot) noexcept;

    void submit_command(const TelemetryCommand& command);
    std::optional<TelemetryCommand> try_pop_command();
    void set_command_handler(std::function<TelemetryCommandResult(const TelemetryCommand&)> handler);

    json::JSON get_diagnostics() const;

private:
    void set_last_command_result(const TelemetryCommandResult& result);
    void sample_once() noexcept;
    void run_loop() noexcept;
    void process_commands() noexcept;

    std::atomic<bool> running_;
    std::thread worker_thread_;
    mutable std::mutex snapshot_mutex_;
    std::shared_ptr<const WorldSnapshot> latest_snapshot_;
    TelemetryCommandQueue command_queue_;
    mutable std::mutex command_handler_mutex_;
    std::function<TelemetryCommandResult(const TelemetryCommand&)> command_handler_;
    mutable std::mutex state_mutex_;
    std::string focus_uid_;
    json::JSON subscription_filter_ = json::JSON::Make(json::JSON::Class::Object);
    TelemetryCommandResult last_command_result_{"idle", "no command processed yet", "", ""};
};

}
