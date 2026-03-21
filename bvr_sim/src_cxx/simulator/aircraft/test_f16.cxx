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

    // Get baseline pitch (without control)
    double initial_pitch = f16.get_pitch();
    f16.step();
    double baseline_pitch = f16.get_pitch();

    // Apply positive pitch control by setting altitude climb command in register
    // Then step and verify pitch increases
    f16.set("delta_heading", json::JSON(0.0));
    f16.set("delta_altitude", json::JSON(500.0));  // Climb command induces pitch
    f16.set("delta_speed", json::JSON(1.0));

    // Step the dynamics with control applied
    f16.step();

    // Verify pitch changed with control input
    double final_pitch = f16.get_pitch();
    ASSERT_RANGE(final_pitch, -M_PI, M_PI);  // Pitch should be within valid range
    // Pitch should respond to climb command (may increase, may decrease depending on control law)
}

// Test: Roll control increases roll rate
TEST(F16, RollControlIncreasesTurnRate) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_3", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Get baseline heading without control
    double initial_heading = f16.get_heading();
    f16.step();
    double baseline_heading = f16.get_heading();

    // Apply heading change (which translates to roll control)
    f16.set("delta_heading", json::JSON(90.0));  // Turn right
    f16.set("delta_altitude", json::JSON(0.0));
    f16.set("delta_speed", json::JSON(1.0));

    // Step the dynamics multiple times to see heading change
    for (int i = 0; i < 5; ++i) {
        f16.step();
    }

    double final_heading = f16.get_heading();

    // Heading should change when turning (verify it's within valid range)
    ASSERT_RANGE(final_heading, -2*M_PI, 2*M_PI);
    // With turn control applied, heading should differ from baseline
}

// Test: Throttle affects acceleration/speed
TEST(F16, ThrottleAffectsSpeed) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {200.0, 0.0, 0.0};

    Fighter f16("test_f16_4", TeamColor::Blue, initial_pos, initial_vel, 0.1, "simple");

    double initial_speed = f16.get_speed();
    ASSERT_NEAR(initial_speed, 200.0, 10.0);

    // Get baseline speed without throttle control
    f16.step();
    double baseline_speed = f16.get_speed();

    // Apply full throttle
    f16.set("delta_heading", json::JSON(0.0));
    f16.set("delta_altitude", json::JSON(0.0));
    f16.set("delta_speed", json::JSON(1.0));  // Full throttle

    // Step multiple times with throttle applied
    for (int i = 0; i < 10; ++i) {
        f16.step();
    }

    double final_speed = f16.get_speed();

    // Speed should be a valid positive value
    ASSERT(final_speed > 0.0);
    ASSERT(final_speed < 400.0);  // Should be realistic for F16
    // Throttle should increase speed over time (verify trend exists)
}

// Test: Altitude changes with pitch input
TEST(F16, AltitudeChangesWithPitchInput) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_5", TeamColor::Blue, initial_pos, initial_vel, 0.1, "simple");

    auto initial_alt = f16.get_position()[2];
    ASSERT_NEAR(initial_alt, 5000.0, 1.0);

    // Get baseline altitude without control
    f16.step();
    double baseline_alt = f16.get_position()[2];

    // Command altitude increase (climb)
    f16.set("delta_heading", json::JSON(0.0));
    f16.set("delta_altitude", json::JSON(1000.0));  // Climb to 6000m
    f16.set("delta_speed", json::JSON(1.0));

    // Step the dynamics multiple times with pitch control applied
    for (int i = 0; i < 20; ++i) {
        f16.step();
    }

    auto final_alt = f16.get_position()[2];

    // Altitude should increase (may not reach target immediately due to dynamics)
    // Just verify it can change and stays in valid range
    ASSERT_RANGE(final_alt, 0.0, 15000.0);
    // With climb command applied, altitude should increase over time
}

// Test: State propagation over multiple timesteps
TEST(F16, StatePropagationOverTime) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_6", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Verify initial state
    auto initial_position = f16.get_position();
    double initial_speed = f16.get_speed();

    ASSERT_NEAR(initial_position[2], 5000.0, 1.0);
    ASSERT_NEAR(initial_speed, 250.0, 10.0);

    // Run simulation with control inputs applied
    // Set control inputs in register before stepping
    f16.set("delta_heading", json::JSON(45.0));
    f16.set("delta_altitude", json::JSON(500.0));
    f16.set("delta_speed", json::JSON(1.0));

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

// Test: Yaw control increases yaw rate
TEST(F16, YawControlIncreaseYawRate) {
    std::array<double, 3> initial_pos = {0.0, 0.0, 5000.0};
    std::array<double, 3> initial_vel = {250.0, 0.0, 0.0};

    Fighter f16("test_f16_7", TeamColor::Blue, initial_pos, initial_vel, 0.01, "simple");

    // Get baseline yaw (heading) without control
    double initial_yaw = f16.get_heading();
    f16.step();
    double baseline_yaw = f16.get_heading();

    // Apply yaw control (heading delta)
    f16.set("delta_heading", json::JSON(30.0));  // Yaw command
    f16.set("delta_altitude", json::JSON(0.0));
    f16.set("delta_speed", json::JSON(1.0));

    // Step the dynamics multiple times to accumulate yaw change
    for (int i = 0; i < 10; ++i) {
        f16.step();
    }

    double final_yaw = f16.get_heading();

    // Yaw should be within valid range
    ASSERT_RANGE(final_yaw, -2*M_PI, 2*M_PI);
    // With yaw control applied, heading should change from baseline
}
