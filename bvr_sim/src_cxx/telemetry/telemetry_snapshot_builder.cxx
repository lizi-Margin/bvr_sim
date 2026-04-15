#include "telemetry_snapshot_builder.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/check.hxx"
#include "rubbish_can/colorful.hxx"
#include <sstream>

namespace {

const char* json_type_name(json::JSON::Class type) noexcept {
    switch (type) {
    case json::JSON::Class::Null: return "Null";
    case json::JSON::Class::Object: return "Object";
    case json::JSON::Class::Array: return "Array";
    case json::JSON::Class::String: return "String";
    case json::JSON::Class::Floating: return "Floating";
    case json::JSON::Class::Integral: return "Integral";
    case json::JSON::Class::Boolean: return "Boolean";
    default: return "Unknown";
    }
}

json::JSON copy_register_to_json_object(const bvr_sim::Register& reg) {
    json::JSON object = json::JSON::Make(json::JSON::Class::Object);
    for (const auto& [key, value] : reg.get_all()) {
        object[key] = value;
    }
    return object;
}

void log_register_debug_dump(const bvr_sim::Register& reg, const std::string& reason, const std::string& key) {
    const auto reg_dump = copy_register_to_json_object(reg);

    std::ostringstream keys_stream;
    bool first = true;
    for (const auto& [entry_key, value] : reg.get_all()) {
        if (!first) {
            keys_stream << ", ";
        }
        first = false;
        keys_stream << entry_key << "(" << json_type_name(value.JSONType()) << ")";
    }

    colorful::printHONG(
        "[TelemetrySnapshotBuilder] %s key=%s register_keys=[%s]",
        reason.c_str(),
        key.c_str(),
        keys_stream.str().c_str());
    SL::get().printf(
        "[TelemetrySnapshotBuilder] %s key=%s register_keys=[%s]",
        reason.c_str(),
        key.c_str(),
        keys_stream.str().c_str());
    SL::get().printf(
        "[TelemetrySnapshotBuilder] register_dump=%s",
        reg_dump.dump(1, "", "").c_str());
}

std::string require_string(const bvr_sim::Register& reg, const std::string& key) {
    auto value = reg.get(key);
    if (!value.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing string key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing string key: %s\n", key.c_str());
        log_register_debug_dump(reg, "missing string key", key);
        check(false, "TelemetrySnapshotBuilder missing required string key: " + key);
    }
    if (value->JSONType() != json::JSON::Class::String) {
        colorful::printHONG("TelemetrySnapshotBuilder key has wrong string type: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong string type for key: %s\n", key.c_str());
        log_register_debug_dump(reg, "wrong string type", key);
        check(false, "TelemetrySnapshotBuilder expected string key: " + key);
    }
    return value->ToString();
}

bool require_bool(const bvr_sim::Register& reg, const std::string& key) {
    auto value = reg.get(key);
    if (!value.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing bool key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing bool key: %s\n", key.c_str());
        log_register_debug_dump(reg, "missing bool key", key);
        check(false, "TelemetrySnapshotBuilder missing required bool key: " + key);
    }
    if (value->JSONType() != json::JSON::Class::Boolean) {
        colorful::printHONG("TelemetrySnapshotBuilder key has wrong bool type: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong bool type for key: %s\n", key.c_str());
        log_register_debug_dump(reg, "wrong bool type", key);
        check(false, "TelemetrySnapshotBuilder expected bool key: " + key);
    }
    return value->ToBool();
}

std::array<double, 3> require_vec3(const bvr_sim::Register& reg, const std::string& key) {
    auto vector = reg.get_vector(key);
    if (!vector.has_value()) {
        colorful::printHONG("TelemetrySnapshotBuilder missing vec3 key: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] missing vec3 key: %s\n", key.c_str());
        log_register_debug_dump(reg, "missing vec3 key", key);
        check(false, "TelemetrySnapshotBuilder missing required vec3 key: " + key);
    }
    if (vector->size() != 3) {
        colorful::printHONG("TelemetrySnapshotBuilder vec3 key has wrong size: %s", key.c_str());
        SL::get().printf("[TelemetrySnapshotBuilder] wrong vec3 size for key: %s\n", key.c_str());
        log_register_debug_dump(reg, "wrong vec3 size", key);
        check(false, "TelemetrySnapshotBuilder expected vec3 key: " + key);
    }
    return {(*vector)[0], (*vector)[1], (*vector)[2]};
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
    if (reg.has("aircraft_model")) {
        state.mesh_name = require_string(reg, "aircraft_model");
    } else if (reg.has("missile_model")) {
        state.mesh_name = require_string(reg, "missile_model");
    } else {
        state.mesh_name = state.type;
    }
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
