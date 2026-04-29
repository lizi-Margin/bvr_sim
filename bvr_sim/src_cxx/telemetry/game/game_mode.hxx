#pragma once

#include "../telemetry_bridge.hxx"
#include "../telemetry_command_queue.hxx"
#include "../telemetry_types.hxx"
#include "rubbish_can/json.hpp"

#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>

namespace bvr_sim {

class GameMode {
public:
    GameMode();
    ~GameMode();

    GameMode(const GameMode&) = delete;
    GameMode& operator=(const GameMode&) = delete;

    void set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> provider);
    void set_command_submitter(std::function<void(const TelemetryCommand&)> submitter);

    void start();
    void stop() noexcept;

    bool is_running() const noexcept;
    bool is_supported() const noexcept;
    json::JSON get_status() const;
    void submit_command(const TelemetryCommand& command) const;

private:
    void run_loop() noexcept;

    std::function<std::shared_ptr<const WorldSnapshot>()> snapshot_provider_;
    std::function<void(const TelemetryCommand&)> command_submitter_;

    std::atomic<bool> running_;
    std::atomic<bool> stop_requested_;
    std::atomic<bool> supported_;
    std::thread viewer_thread_;

    mutable std::mutex state_mutex_;
    std::string last_error_;
    double last_sim_time_ = 0.0;
    long last_object_count_ = 0;
    long last_command_count_ = 0;
    long last_draw_calls_ = 0;
    long last_vertex_count_ = 0;
    bool shadows_enabled_ = true;
    bool material_system_enabled_ = true;
};

} // namespace bvr_sim




