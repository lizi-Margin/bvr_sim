#include "telemetry_types.hxx"

namespace bvr_sim {

json::JSON telemetry_object_state_to_json(const TelemetryObjectState& state) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["uid"] = state.uid;
    result["type"] = state.type;
    result["team"] = state.team;
    result["alive"] = state.alive;

    json::JSON position = json::JSON::Make(json::JSON::Class::Array);
    position.append(state.position[0]);
    position.append(state.position[1]);
    position.append(state.position[2]);
    result["position"] = position;

    json::JSON velocity = json::JSON::Make(json::JSON::Class::Array);
    velocity.append(state.velocity[0]);
    velocity.append(state.velocity[1]);
    velocity.append(state.velocity[2]);
    result["velocity"] = velocity;

    json::JSON orientation = json::JSON::Make(json::JSON::Class::Array);
    orientation.append(state.orientation[0]);
    orientation.append(state.orientation[1]);
    orientation.append(state.orientation[2]);
    result["orientation"] = orientation;
    result["debug_register"] = state.debug_register;
    return result;
}

json::JSON world_snapshot_to_json(const WorldSnapshot& snapshot) {
    json::JSON result = json::JSON::Make(json::JSON::Class::Object);
    result["sim_time"] = snapshot.sim_time;
    result["dt"] = snapshot.dt;
    result["running"] = snapshot.running;
    result["paused"] = snapshot.paused;

    json::JSON objects = json::JSON::Make(json::JSON::Class::Array);
    for (const auto& object_state : snapshot.objects) {
        objects.append(telemetry_object_state_to_json(object_state));
    }
    result["objects"] = objects;
    return result;
}

}
