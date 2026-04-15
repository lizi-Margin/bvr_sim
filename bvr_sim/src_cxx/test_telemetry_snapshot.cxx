#include "test_main.hxx"
#include "simulator/register.hxx"
#include "telemetry/telemetry_snapshot_builder.hxx"
#include "telemetry/telemetry_types.hxx"

TEST(TelemetrySnapshot, DefaultSnapshotStartsEmpty) {
    bvr_sim::WorldSnapshot snapshot;
    ASSERT_EQ(static_cast<double>(snapshot.objects.size()), 0.0);
    ASSERT_EQ(snapshot.sim_time, 0.0);
    ASSERT_EQ(snapshot.dt, 0.0);
}

TEST(TelemetrySnapshot, BuildsNormalizedStateFromRegister) {
    bvr_sim::Register reg;
    reg.set("uid", json::String("blue_1"));
    reg.set("Type", json::String("Aircraft"));
    reg.set("color", json::String("Blue"));
    reg.set("is_alive", json::Boolean(true));

    json::JSON position = json::JSON::Make(json::JSON::Class::Array);
    position.append(1.0);
    position.append(2.0);
    position.append(3.0);
    reg.set("position", position);

    json::JSON velocity = json::JSON::Make(json::JSON::Class::Array);
    velocity.append(4.0);
    velocity.append(5.0);
    velocity.append(6.0);
    reg.set("velocity", velocity);

    json::JSON rpy = json::JSON::Make(json::JSON::Class::Array);
    rpy.append(0.1);
    rpy.append(0.2);
    rpy.append(0.3);
    reg.set("rpy", rpy);

    const auto state = bvr_sim::TelemetrySnapshotBuilder::build_object_state(reg);
    ASSERT(state.uid == "blue_1");
    ASSERT(state.type == "Aircraft");
    ASSERT(state.team == "Blue");
    ASSERT(state.alive);
    ASSERT_NEAR(state.position[0], 1.0, 1e-9);
    ASSERT_NEAR(state.velocity[2], 6.0, 1e-9);
    ASSERT_NEAR(state.orientation[1], 0.2, 1e-9);
}

TEST(TelemetrySnapshot, CopiesRawRegisterIntoDebugPayload) {
    bvr_sim::Register reg;
    reg.set("uid", json::String("ground_1"));
    reg.set("Type", json::String("GroundUnit"));
    reg.set("color", json::String("Red"));
    reg.set("is_alive", json::Boolean(true));

    json::JSON position = json::JSON::Make(json::JSON::Class::Array);
    position.append(10.0);
    position.append(20.0);
    position.append(0.0);
    reg.set("position", position);

    json::JSON velocity = json::JSON::Make(json::JSON::Class::Array);
    velocity.append(0.0);
    velocity.append(0.0);
    velocity.append(0.0);
    reg.set("velocity", velocity);

    const auto state = bvr_sim::TelemetrySnapshotBuilder::build_object_state(reg);
    ASSERT(state.debug_register.JSONType() == json::JSON::Class::Object);
    ASSERT(state.debug_register.hasKey("uid"));
    ASSERT(state.debug_register.at("uid").ToString() == "ground_1");
}
