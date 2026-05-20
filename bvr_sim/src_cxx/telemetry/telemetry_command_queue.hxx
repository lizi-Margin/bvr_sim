#pragma once

#include "support/json.hpp"
#include "telemetry_types.hxx"
#include <deque>
#include <mutex>
#include <optional>
#include <string>

namespace bvr_sim {

enum class TelemetryCommandKind {
    Pause = 0,
    Resume,
    Step,
    SetFocusUid,
    SetSubscriptionFilter,
    ObjectDebug,
    Command,
    SetGameCamera
};

struct TelemetryCommand {
    TelemetryCommandKind kind = TelemetryCommandKind::Pause;
    std::string target_uid;
    json::JSON payload = json::JSON::Make(json::JSON::Class::Object);
};

std::optional<TelemetryCommandKind> telemetry_command_kind_from_string(const std::string& command_name) noexcept;
std::string telemetry_command_kind_to_string(TelemetryCommandKind kind) noexcept;

class TelemetryCommandQueue {
public:
    void push(const TelemetryCommand& command);
    std::optional<TelemetryCommand> try_pop();
    size_t size() const noexcept;

private:
    std::deque<TelemetryCommand> queue_;
    mutable std::mutex mutex_;
};

}
