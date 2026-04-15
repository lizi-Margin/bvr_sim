#include "test_main.hxx"
#include "telemetry/telemetry_command_queue.hxx"

TEST(TelemetryCommandQueue, PushAndPopSingleCommand) {
    bvr_sim::TelemetryCommandQueue queue;
    queue.push({bvr_sim::TelemetryCommandKind::Step, "", json::Integral(3)});

    auto command = queue.try_pop();

    ASSERT(command.has_value());
    ASSERT(static_cast<int>(command->kind) == static_cast<int>(bvr_sim::TelemetryCommandKind::Step));
    ASSERT(command->payload.JSONType() == json::JSON::Class::Integral);
    ASSERT_EQ(static_cast<double>(command->payload.ToInt()), 3.0);
}

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

TEST(TelemetryCommandQueue, ParsesKnownCommandKinds) {
    auto pause = bvr_sim::telemetry_command_kind_from_string("pause");
    auto focus = bvr_sim::telemetry_command_kind_from_string("set_focus_uid");

    ASSERT(pause.has_value());
    ASSERT(focus.has_value());
    ASSERT(static_cast<int>(*pause) == static_cast<int>(bvr_sim::TelemetryCommandKind::Pause));
    ASSERT(static_cast<int>(*focus) == static_cast<int>(bvr_sim::TelemetryCommandKind::SetFocusUid));
}

TEST(TelemetryCommandQueue, RejectsUnknownCommandKind) {
    auto invalid = bvr_sim::telemetry_command_kind_from_string("launch_everything");
    ASSERT(!invalid.has_value());
}
