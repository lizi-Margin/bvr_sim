#include "telemetry_command_queue.hxx"

namespace bvr_sim {

std::optional<TelemetryCommandKind> telemetry_command_kind_from_string(const std::string& command_name) noexcept {
    if (command_name == "pause") {
        return TelemetryCommandKind::Pause;
    }
    if (command_name == "resume") {
        return TelemetryCommandKind::Resume;
    }
    if (command_name == "step") {
        return TelemetryCommandKind::Step;
    }
    if (command_name == "set_focus_uid") {
        return TelemetryCommandKind::SetFocusUid;
    }
    if (command_name == "set_subscription_filter") {
        return TelemetryCommandKind::SetSubscriptionFilter;
    }
    if (command_name == "object_debug") {
        return TelemetryCommandKind::ObjectDebug;
    }
    if (command_name == "command") {
        return TelemetryCommandKind::Command;
    }
    if (command_name == "set_game_camera") {
        return TelemetryCommandKind::SetGameCamera;
    }
    return std::nullopt;
}

std::string telemetry_command_kind_to_string(TelemetryCommandKind kind) noexcept {
    switch (kind) {
    case TelemetryCommandKind::Pause:
        return "pause";
    case TelemetryCommandKind::Resume:
        return "resume";
    case TelemetryCommandKind::Step:
        return "step";
    case TelemetryCommandKind::SetFocusUid:
        return "set_focus_uid";
    case TelemetryCommandKind::SetSubscriptionFilter:
        return "set_subscription_filter";
    case TelemetryCommandKind::ObjectDebug:
        return "object_debug";
    case TelemetryCommandKind::Command:
        return "command";
    case TelemetryCommandKind::SetGameCamera:
        return "set_game_camera";
    default:
        return "unknown";
    }
}

void TelemetryCommandQueue::push(const TelemetryCommand& command) {
    std::lock_guard<std::mutex> lock(mutex_);
    queue_.push_back(command);
}

std::optional<TelemetryCommand> TelemetryCommandQueue::try_pop() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (queue_.empty()) {
        return std::nullopt;
    }

    auto command = queue_.front();
    queue_.pop_front();
    return command;
}

size_t TelemetryCommandQueue::size() const noexcept {
    std::lock_guard<std::mutex> lock(mutex_);
    return queue_.size();
}

}
