#include "telemetry_command_queue.hxx"

namespace bvr_sim {

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
