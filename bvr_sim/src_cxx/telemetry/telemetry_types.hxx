#pragma once

#include "support/json.hpp"
#include <array>
#include <string>
#include <vector>

namespace bvr_sim {

struct TelemetryObjectState {
    std::string uid;
    std::string type;
    std::string team;
    std::string mesh_name;
    bool alive = false;
    std::array<double, 3> position{0.0, 0.0, 0.0};
    std::array<double, 3> velocity{0.0, 0.0, 0.0};
    std::array<double, 3> orientation{0.0, 0.0, 0.0};
    json::JSON debug_register = json::JSON::Make(json::JSON::Class::Object);
};

struct WorldSnapshot {
    double sim_time = 0.0;
    double dt = 0.0;
    bool running = false;
    bool paused = false;
    std::vector<TelemetryObjectState> objects;
};

struct TelemetryCommandResult {
    std::string status;
    std::string message;
    std::string kind;
    std::string target_uid;
};

json::JSON telemetry_object_state_to_json(const TelemetryObjectState& state);
json::JSON world_snapshot_to_json(const WorldSnapshot& snapshot);
json::JSON telemetry_command_result_to_json(const TelemetryCommandResult& result);

}
