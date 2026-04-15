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
    return std::nullopt;
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
