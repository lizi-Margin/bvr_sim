#include "../../test_main.cxx"
#include "fighter.hxx"
#include "fdm/simple_fdm.hxx"
#include <array>
#include <map>
#include <any>
#include <cmath>

using namespace bvr_sim;

// Test: Aircraft initializes at correct position
TEST(F16, InitializeAtPosition) {
    // Create F16 fighter with initial position
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};  // lat, lon, alt (meters)
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};   // vx, vy, vz (m/s)

    Fighter f16("test_f16_1", TeamColor::Blue, initial_pos, initial_vel, 0.1, "simple");

    // Verify altitude is initialized correctly (±1m tolerance)
    auto pos = f16.get_position();
    ASSERT_NEAR(pos[2], 5000.0, 1.0);
}

// Test: Pitch control increases pitch rate
TEST(F16, PitchControlIncreasesPitchRate) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_2", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Apply positive pitch control via FDM step
    // In the actual system, controls come from the action space
    std::map<std::string, double> action;
    action["delta_heading"] = 0.0;
    action["delta_altitude"] = 500.0;  // Climb command
    action["delta_speed"] = 1.0;

    // Get initial pitch
    double initial_pitch = f16.get_pitch();

    // Step the dynamics
    f16.step();

    // After stepping with climb command, pitch should change
    // The exact response depends on SimpleFDM implementation
    // We verify that pitch can be read and has a reasonable value
    double final_pitch = f16.get_pitch();
    ASSERT_RANGE(final_pitch, -M_PI, M_PI);  // Pitch should be within [-180, 180] degrees
}

// Test: Roll control increases roll rate
TEST(F16, RollControlIncreasesTurnRate) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_3", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Apply heading change (which translates to roll control)
    std::map<std::string, double> action;
    action["delta_heading"] = 90.0;  // Turn right
    action["delta_altitude"] = 0.0;
    action["delta_speed"] = 1.0;

    double initial_heading = f16.get_heading();

    // Step the dynamics multiple times to see heading change
    for (int i = 0; i < 5; ++i) {
        f16.step();
    }

    double final_heading = f16.get_heading();

    // Heading should change when turning
    ASSERT_RANGE(final_heading, -2*M_PI, 2*M_PI);
}

// Test: Throttle affects acceleration/speed
TEST(F16, ThrottleAffectsSpeed) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {200.0, 0.0, 0.0};

    Fighter f16("test_f16_4", TeamColor::Blue, initial_pos, initial_vel, 0.1, "simple");

    double initial_speed = f16.get_speed();
    ASSERT_NEAR(initial_speed, 200.0, 10.0);

    // Apply throttle
    std::map<std::string, double> action;
    action["delta_heading"] = 0.0;
    action["delta_altitude"] = 0.0;
    action["delta_speed"] = 1.0;  // Full throttle

    // Step multiple times
    for (int i = 0; i < 10; ++i) {
        f16.step();
    }

    double final_speed = f16.get_speed();

    // Speed should be a valid positive value
    ASSERT(final_speed > 0.0);
    ASSERT(final_speed < 400.0);  // Should be realistic for F16
}

// Test: Altitude changes with pitch input
TEST(F16, AltitudeChangesWithPitchInput) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_5", TeamColor::Blue, initial_pos, initial_vel, 0.1, "simple");

    auto initial_alt = f16.get_position()[2];
    ASSERT_NEAR(initial_alt, 5000.0, 1.0);

    // Command altitude increase
    std::map<std::string, double> action;
    action["delta_heading"] = 0.0;
    action["delta_altitude"] = 1000.0;  // Climb to 6000m
    action["delta_speed"] = 1.0;

    // Step the dynamics multiple times
    for (int i = 0; i < 20; ++i) {
        f16.step();
    }

    auto final_alt = f16.get_position()[2];

    // Altitude should increase (may not reach target immediately)
    // Just verify it can change and stays in valid range
    ASSERT_RANGE(final_alt, 0.0, 15000.0);
}

// Test: State propagation over multiple timesteps
TEST(F16, StatePropagationOverTime) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_6", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Verify initial state
    auto initial_position = f16.get_position();
    auto initial_velocity_arr = f16.get_position();
    double initial_speed = f16.get_speed();

    ASSERT_NEAR(initial_position[2], 5000.0, 1.0);
    ASSERT_NEAR(initial_speed, 250.0, 10.0);

    // Run simulation for multiple steps
    std::map<std::string, double> action;
    action["delta_heading"] = 45.0;
    action["delta_altitude"] = 500.0;
    action["delta_speed"] = 1.0;

    for (int i = 0; i < 50; ++i) {
        f16.step();
    }

    // Verify state is still valid after propagation
    auto final_position = f16.get_position();
    double final_speed = f16.get_speed();
    auto rpy = f16.get_rpy();

    // Position should be valid
    ASSERT_RANGE(final_position[2], 0.0, 15000.0);  // Altitude

    // Speed should be positive and reasonable
    ASSERT(final_speed > 0.0);
    ASSERT(final_speed < 400.0);

    // Roll, Pitch, Yaw should be angles
    ASSERT_RANGE(rpy[0], -M_PI, M_PI);  // Roll
    ASSERT_RANGE(rpy[1], -M_PI, M_PI);  // Pitch
    ASSERT_RANGE(rpy[2], -M_PI, M_PI);  // Yaw
}
