#include "test_main.hxx"
#include "telemetry/telemetry_types.hxx"

TEST(TelemetrySnapshot, DefaultSnapshotStartsEmpty) {
    bvr_sim::WorldSnapshot snapshot;
    ASSERT_EQ(static_cast<double>(snapshot.objects.size()), 0.0);
    ASSERT_EQ(snapshot.sim_time, 0.0);
    ASSERT_EQ(snapshot.dt, 0.0);
}
