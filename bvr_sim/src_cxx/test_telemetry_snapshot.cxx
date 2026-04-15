#include "test_main.hxx"
#include "simulator/register.hxx"
#include "simulator/simulator.hxx"
#include "telemetry/telemetry_snapshot_builder.hxx"
#include "telemetry/telemetry_types.hxx"

namespace {

class FixedOrientationObject : public bvr_sim::SimulatedObject {
public:
    FixedOrientationObject()
        : bvr_sim::SimulatedObject(
            "fixed_orientation",
            bvr_sim::TeamColor::Blue,
            {1.0, 2.0, 3.0},
            {4.0, 5.0, 6.0},
            0.1,
            bvr_sim::SOT::GroundUnit) {
    }

    void step() override {
    }

    std::string log() noexcept override {
        return "";
    }

    double get_roll() const noexcept override {
        return 0.11;
    }

    double get_pitch() const noexcept override {
        return -0.22;
    }

    double get_yaw() const noexcept override {
        return 0.33;
    }
};

class YawOnlyObject : public bvr_sim::SimulatedObject {
public:
    YawOnlyObject()
        : bvr_sim::SimulatedObject(
            "yaw_only",
            bvr_sim::TeamColor::Red,
            {0.0, 0.0, 0.0},
            {0.0, 0.0, 0.0},
            0.1,
            bvr_sim::SOT::GroundUnit) {
    }

    void step() override {
    }

    std::string log() noexcept override {
        return "";
    }

    double get_yaw() const noexcept override {
        return -1.25;
    }
};

}

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

TEST(TelemetrySnapshot, MissileUsesRegisterRpyWhenPresent) {
    bvr_sim::Register reg;
    reg.set("uid", json::String("missile_1"));
    reg.set("Type", json::String("Missile"));
    reg.set("color", json::String("Blue"));
    reg.set("missile_model", json::String("AIM-120C"));
    reg.set("is_alive", json::Boolean(true));

    json::JSON position = json::JSON::Make(json::JSON::Class::Array);
    position.append(100.0);
    position.append(200.0);
    position.append(300.0);
    reg.set("position", position);

    json::JSON velocity = json::JSON::Make(json::JSON::Class::Array);
    velocity.append(400.0);
    velocity.append(500.0);
    velocity.append(600.0);
    reg.set("velocity", velocity);

    json::JSON rpy = json::JSON::Make(json::JSON::Class::Array);
    rpy.append(0.4);
    rpy.append(0.5);
    rpy.append(0.6);
    reg.set("rpy", rpy);

    const auto state = bvr_sim::TelemetrySnapshotBuilder::build_object_state(reg);
    ASSERT(state.mesh_name == "AIM-120C");
    ASSERT_NEAR(state.orientation[0], 0.4, 1e-9);
    ASSERT_NEAR(state.orientation[1], 0.5, 1e-9);
    ASSERT_NEAR(state.orientation[2], 0.6, 1e-9);
}

TEST(TelemetrySnapshot, SimulatedObjectWriteRegisterUsesUnifiedRpyContract) {
    FixedOrientationObject object;
    object.write_register();

    const auto roll = object.get("roll");
    const auto pitch = object.get("pitch");
    const auto yaw = object.get("yaw");
    const auto rpy = object.get("rpy");

    ASSERT(roll.has_value());
    ASSERT(pitch.has_value());
    ASSERT(yaw.has_value());
    ASSERT(rpy.has_value());
    ASSERT_NEAR(roll->ToFloat(), 0.11, 1e-9);
    ASSERT_NEAR(pitch->ToFloat(), -0.22, 1e-9);
    ASSERT_NEAR(yaw->ToFloat(), 0.33, 1e-9);

    auto rpy_vec = object.get_register().get_vector("rpy");
    ASSERT(rpy_vec.has_value());
    ASSERT_NEAR((*rpy_vec)[0], 0.11, 1e-9);
    ASSERT_NEAR((*rpy_vec)[1], -0.22, 1e-9);
    ASSERT_NEAR((*rpy_vec)[2], 0.33, 1e-9);
}

TEST(TelemetrySnapshot, HeadingRemainsCompatibleWithYawContract) {
    YawOnlyObject object;
    object.write_register();

    ASSERT_NEAR(object.get_heading(), -1.25, 1e-9);

    const auto yaw = object.get("yaw");
    auto rpy_vec = object.get_register().get_vector("rpy");
    ASSERT(yaw.has_value());
    ASSERT(rpy_vec.has_value());
    ASSERT_NEAR(yaw->ToFloat(), -1.25, 1e-9);
    ASSERT_NEAR((*rpy_vec)[2], -1.25, 1e-9);
}
