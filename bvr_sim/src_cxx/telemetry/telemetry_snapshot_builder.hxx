#pragma once

#include "telemetry_types.hxx"

namespace bvr_sim {

class TelemetrySnapshotBuilder {
public:
    static WorldSnapshot make_empty_snapshot(double sim_time, double dt, bool running, bool paused) noexcept;
};

}
