#include "test_main.hxx"
#include "telemetry/telemetry_command_queue.hxx"

TEST(TelemetryCommandQueue, PreservesQueuedCommandOrder) {
    bvr_sim::TelemetryCommandQueue queue;

    queue.push({bvr_sim::TelemetryCommandKind::Pause});
    queue.push({bvr_sim::TelemetryCommandKind::Resume});

    auto first = queue.try_pop();
    auto second = queue.try_pop();

    ASSERT(first.has_value());
    ASSERT(second.has_value());
    ASSERT(static_cast<int>(first->kind) == static_cast<int>(bvr_sim::TelemetryCommandKind::Pause));
    ASSERT(static_cast<int>(second->kind) == static_cast<int>(bvr_sim::TelemetryCommandKind::Resume));
}
