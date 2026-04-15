#include "telemetry_snapshot_builder.hxx"

namespace bvr_sim {

WorldSnapshot TelemetrySnapshotBuilder::make_empty_snapshot(double sim_time, double dt, bool running, bool paused) noexcept {
    WorldSnapshot snapshot;
    snapshot.sim_time = sim_time;
    snapshot.dt = dt;
    snapshot.running = running;
    snapshot.paused = paused;
    return snapshot;
}

}
