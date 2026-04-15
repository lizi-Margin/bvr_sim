#include "telemetry_snapshot_builder.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "rubbish_can/colorful.hxx"

namespace {

std::string require_string(const bvr_sim::Register& reg, const std::string& key) {
    auto value = reg.get(key);
    if (!value.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing string key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing string key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder missing required string key: " + key);
    }
    if (value->JSONType() != json::JSON::Class::String) {
        colorful::printHONG("TelemetrySnapshotBuilder key has wrong string type: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong string type for key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder expected string key: " + key);
    }
    return value->ToString();
}

bool require_bool(const bvr_sim::Register& reg, const std::string& key) {
    auto value = reg.get(key);
    if (!value.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing bool key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing bool key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder missing required bool key: " + key);
    }
    if (value->JSONType() != json::JSON::Class::Boolean) {
        colorful::printHONG("TelemetrySnapshotBuilder key has wrong bool type: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong bool type for key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder expected bool key: " + key);
    }
    return value->ToBool();
}

std::array<double, 3> require_vec3(const bvr_sim::Register& reg, const std::string& key) {
    auto vector = reg.get_vector(key);
    if (!vector.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing vec3 key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing vec3 key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder missing required vec3 key: " + key);
    }
    if (vector->size() != 3) {
        colorful::printHONG("TelemetrySnapshotBuilder vec3 key has wrong size: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong vec3 size for key: %s\n", key.c_str());
        check(false, "TelemetrySnapshotBuilder expected vec3 key: " + key);
    }
    return {(*vector)[0], (*vector)[1], (*vector)[2]};
}

json::JSON copy_register_to_json_object(const bvr_sim::Register& reg) {
    json::JSON object = json::JSON::Make(json::JSON::Class::Object);
    for (const auto& [key, value] : reg.get_all()) {
        object[key] = value;
    }
    return object;
}

}

namespace bvr_sim {

WorldSnapshot TelemetrySnapshotBuilder::make_empty_snapshot(double sim_time, double dt, bool running, bool paused) noexcept {
    WorldSnapshot snapshot;
    snapshot.sim_time = sim_time;
    snapshot.dt = dt;
    snapshot.running = running;
    snapshot.paused = paused;
    return snapshot;
}

TelemetryObjectState TelemetrySnapshotBuilder::build_object_state(const Register& reg) noexcept {
    TelemetryObjectState state;
    state.uid = require_string(reg, "uid");
    state.type = require_string(reg, "Type");
    state.team = require_string(reg, "color");
    state.alive = require_bool(reg, "is_alive");
    state.position = require_vec3(reg, "position");
    state.velocity = require_vec3(reg, "velocity");

    if (reg.has("rpy")) {
        state.orientation = require_vec3(reg, "rpy");
    } else {
        state.orientation = {0.0, 0.0, 0.0};
    }

    state.debug_register = copy_register_to_json_object(reg);
    return state;
}

}
