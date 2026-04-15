#include "telemetry_types.hxx"

namespace bvr_sim {

json::JSON telemetry_object_state_to_json(const TelemetryObjectState& state) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["uid"] = json::String(state.uid);
    result["type"] = json::String(state.type);
    result["team"] = json::String(state.team);
    result["mesh_name"] = json::String(state.mesh_name);
    result["alive"] = json::Boolean(state.alive);

    json::JSON position = json::JSON::Make(json::JSON::Class::Array);
    position.append(json::Float(state.position[0]));
    position.append(json::Float(state.position[1]));
    position.append(json::Float(state.position[2]));
    result["position"] = position;

    json::JSON velocity = json::JSON::Make(json::JSON::Class::Array);
    velocity.append(json::Float(state.velocity[0]));
    velocity.append(json::Float(state.velocity[1]));
    velocity.append(json::Float(state.velocity[2]));
    result["velocity"] = velocity;

    json::JSON orientation = json::JSON::Make(json::JSON::Class::Array);
    orientation.append(json::Float(state.orientation[0]));
    orientation.append(json::Float(state.orientation[1]));
    orientation.append(json::Float(state.orientation[2]));
    result["orientation"] = orientation;
    result["debug_register"] = state.debug_register;
    return result;
}

json::JSON world_snapshot_to_json(const WorldSnapshot& snapshot) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["sim_time"] = json::Float(snapshot.sim_time);
    result["dt"] = json::Float(snapshot.dt);
    result["running"] = json::Boolean(snapshot.running);
    result["paused"] = json::Boolean(snapshot.paused);

    json::JSON objects = json::JSON::Make(json::JSON::Class::Array);
    for (const auto& object_state : snapshot.objects) {
        objects.append(telemetry_object_state_to_json(object_state));
    }
    result["objects"] = objects;
    return result;
}

json::JSON telemetry_command_result_to_json(const TelemetryCommandResult& result) {
    json::JSON payload = json::JSON::Make(json::JSON::Class::Object);
    payload["status"] = json::String(result.status);
    payload["message"] = json::String(result.message);
    payload["kind"] = json::String(result.kind);
    payload["target_uid"] = json::String(result.target_uid);
    return payload;
}

}
