#pragma once

#include "rubbish_can/json.hpp"
#include "telemetry/embedded_web_server.hxx"
#include "telemetry/telemetry_bridge.hxx"
#include <thread>
#include <atomic>
#include <fstream>
#include <mutex>
#include <condition_variable>
#include <memory>

namespace bvr_sim {

class SimCore {
public:
    SimCore(
        double dt,
        const std::string& log_file_path,
        const std::string& acmi_file_path
    );
    ~SimCore();

    SimCore(const SimCore&) = delete;
    SimCore& operator=(const SimCore&) = delete;

    void start();
    void stop();
    void pause();
    void resume();

    void step(int steps = 1);

    json::JSON handle(const std::string& cmd);
    void set_acmi_file_path(const std::string& path);

    bool is_running() const noexcept { return running_; }
    bool is_paused() const noexcept { return paused_; }
    bool is_telemetry_running() const noexcept;

    double get_sim_time() const noexcept;
    double get_dt() const noexcept;
    json::JSON get_telemetry_snapshot() const;
    json::JSON get_telemetry_status() const;
    void start_telemetry_bridge();
    void stop_telemetry_bridge();
    void refresh_telemetry_snapshot();
    bool is_visualization_server_running() const noexcept;
    void set_visualization_static_root(const std::string& static_root);
    void start_visualization_server(int port = 8765);
    void stop_visualization_server();
    json::JSON get_visualization_status() const;

private:
    void run_loop();
    void update_physics();
    void log();
    void handle_telemetry_command(const TelemetryCommand& command);
    
    std::atomic<bool> running_;
    std::atomic<bool> paused_;
    std::atomic<bool> should_exit_;

    std::thread sim_thread_;
    std::mutex pause_mutex_;
    std::condition_variable pause_cv_;

private:
    void truncate_acmi_file();
    std::string acmi_file_path_;
    std::ofstream acmi_file_;
    std::shared_ptr<TelemetryBridge> telemetry_bridge_;
    std::shared_ptr<EmbeddedWebServer> visualization_server_;

};

}
