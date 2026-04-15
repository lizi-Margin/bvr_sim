#pragma once

#include "rubbish_can/json.hpp"
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
    ObjectDebug
};

struct TelemetryCommand {
    TelemetryCommandKind kind = TelemetryCommandKind::Pause;
    std::string target_uid;
    json::JSON payload = json::JSON::Make(json::JSON::Class::Object);
};

std::optional<TelemetryCommandKind> telemetry_command_kind_from_string(const std::string& command_name) noexcept;

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
