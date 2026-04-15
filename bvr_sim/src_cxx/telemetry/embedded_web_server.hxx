#pragma once

#include "telemetry_command_queue.hxx"
#include "rubbish_can/json.hpp"
#include <atomic>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace bvr_sim {

class EmbeddedWebServer {
public:
    using JsonProvider = std::function<json::JSON()>;
    using CommandSubmitter = std::function<void(const TelemetryCommand&)>;

    EmbeddedWebServer();
    ~EmbeddedWebServer();

    void set_snapshot_provider(JsonProvider provider);
    void set_diagnostics_provider(JsonProvider provider);
    void set_command_submitter(CommandSubmitter submitter);
    void set_static_root(const std::string& static_root);

    void start(int port);
    void stop();

    bool is_running() const noexcept;
    int get_port() const noexcept;
    std::string get_base_url() const;
    std::string get_frontend_url() const;
    size_t get_client_count() const noexcept;
    std::string get_static_root() const;
    bool is_static_frontend_available() const;

private:
    class Impl;

    std::shared_ptr<Impl> impl_;
    std::atomic<bool> running_;
    int port_;
    mutable std::mutex callback_mutex_;
    JsonProvider snapshot_provider_;
    JsonProvider diagnostics_provider_;
    CommandSubmitter command_submitter_;
    std::string static_root_;
};

}
