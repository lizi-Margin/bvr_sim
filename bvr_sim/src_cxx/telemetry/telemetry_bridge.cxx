#include "telemetry_bridge.hxx"
#include "global_config.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "so_pool.hxx"

#include <chrono>

namespace bvr_sim {

namespace {

bool snapshot_matches_filter(const TelemetryObjectState& object_state, const json::JSON& filter) {
    if (filter.JSONType() == json::JSON::Class::Null) {
        return true;
    }
    format_check(
        filter.JSONType() == json::JSON::Class::Object,
        "TelemetryBridge subscription_filter must be a JSON object");

    if (filter.hasKey("type")) {
        format_check(
            filter.at("type").JSONType() == json::JSON::Class::String,
            "TelemetryBridge subscription_filter.type must be string");
        const auto required_type = filter.at("type").ToString();
        if (object_state.type.find(required_type) == std::string::npos) {
            return false;
        }
    }

    if (filter.hasKey("team")) {
        format_check(
            filter.at("team").JSONType() == json::JSON::Class::String,
            "TelemetryBridge subscription_filter.team must be string");
        const auto required_team = filter.at("team").ToString();
        if (object_state.team != required_team) {
            return false;
        }
    }

    return true;
}

}

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

void TelemetryBridge::set_command_handler(std::function<TelemetryCommandResult(const TelemetryCommand&)> handler) {
    std::lock_guard<std::mutex> lock(command_handler_mutex_);
    command_handler_ = std::move(handler);
}

void TelemetryBridge::set_last_command_result(const TelemetryCommandResult& result) {
    std::lock_guard<std::mutex> lock(state_mutex_);
    last_command_result_ = result;
}

json::JSON TelemetryBridge::get_diagnostics() const {
    json::JSON diagnostics = json::JSON::Make(json::JSON::Class::Object);
    diagnostics["running"] = json::Boolean(is_running());
    diagnostics["queue_size"] = json::Integral(static_cast<long>(command_queue_.size()));

    auto snapshot = get_latest_snapshot();
    diagnostics["has_snapshot"] = json::Boolean(snapshot != nullptr);
    diagnostics["snapshot_object_count"] = json::Integral(snapshot ? static_cast<long>(snapshot->objects.size()) : 0L);
    diagnostics["snapshot_sim_time"] = json::Float(snapshot ? snapshot->sim_time : 0.0);

    std::lock_guard<std::mutex> lock(state_mutex_);
    diagnostics["focus_uid"] = json::String(focus_uid_);
    diagnostics["subscription_filter"] = subscription_filter_;
    diagnostics["last_command_result"] = telemetry_command_result_to_json(last_command_result_);
    return diagnostics;
}

void TelemetryBridge::run_loop() noexcept {
    while (running_.load()) {
        process_commands();
        sample_once();
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
}

void TelemetryBridge::process_commands() noexcept {
    while (true) {
        auto command = try_pop_command();
        if (!command.has_value()) {
            return;
        }

        if (command->kind == TelemetryCommandKind::SetFocusUid) {
            TelemetryCommandResult result;
            result.status = "applied";
            result.message = "focus updated";
            result.kind = telemetry_command_kind_to_string(command->kind);
            result.target_uid = command->target_uid;
            {
                std::lock_guard<std::mutex> lock(state_mutex_);
                focus_uid_ = command->target_uid;
                last_command_result_ = result;
            }
            continue;
        }

        if (command->kind == TelemetryCommandKind::SetSubscriptionFilter) {
            TelemetryCommandResult result;
            result.status = "applied";
            result.message = "subscription filter updated";
            result.kind = telemetry_command_kind_to_string(command->kind);
            result.target_uid = command->target_uid;
            {
                std::lock_guard<std::mutex> lock(state_mutex_);
                subscription_filter_ = command->payload;
                last_command_result_ = result;
            }
            continue;
        }

        std::function<TelemetryCommandResult(const TelemetryCommand&)> handler;
        {
            std::lock_guard<std::mutex> lock(command_handler_mutex_);
            handler = command_handler_;
        }
        if (handler) {
            set_last_command_result(handler(*command));
            continue;
        }

        TelemetryCommandResult result;
        result.status = "error";
        result.message = "command handler unavailable";
        result.kind = telemetry_command_kind_to_string(command->kind);
        result.target_uid = command->target_uid;
        set_last_command_result(result);
    }
}

void TelemetryBridge::sample_once() noexcept {
    auto snapshot = std::make_shared<WorldSnapshot>(
        TelemetrySnapshotBuilder::make_empty_snapshot(cfg::sim_time, cfg::dt, running_.load(), false));
    json::JSON subscription_filter = json::JSON::Make(json::JSON::Class::Object);
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        subscription_filter = subscription_filter_;
    }

    for (const auto& object : SOPool::instance().get_all()) {
        if (!object) {
            colorful::printHONG("[TelemetryBridge] null object found in SOPool during sampling");
            SL::get().print("[TelemetryBridge] null object found in SOPool during sampling");
            check(false, "TelemetryBridge::sample_once encountered null object in SOPool");
        }
        auto object_state = TelemetrySnapshotBuilder::build_object_state(object->get_register());
        if (snapshot_matches_filter(object_state, subscription_filter)) {
            snapshot->objects.push_back(std::move(object_state));
        }
    }

    set_latest_snapshot(snapshot);
}

}
