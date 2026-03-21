#include "simple_fdm.hxx"
#include <cmath>
#include <algorithm>

namespace bvr_sim {

using namespace c3utils;

SimpleFDM::SimpleFDM(double dt) noexcept
    : BaseFDM(dt),
      max_speed(411.0),          // m/s (Mach 1.2)
      min_speed(150.0),          // m/s (minimum airspeed)
      max_turn_rate(deg2rad(9.0)),   // rad/s (9 degrees/sec)
      max_climb_rate(250.0),     // m/s (15,000 ft/min)
      max_acceleration(5.0),     // m/s^2 (longitudinal)
      max_g(9.0),                // max G-load
      DELTA_PITCH_MAX(deg2rad(15) / (1 / dt)),
      min_altitude(feet_to_meters(800.0)),
      max_altitude(feet_to_meters(32000.0)) {}

void SimpleFDM::reset(const std::map<std::string, std::any>& initial_state) {
    // Extract position with default [0.0, 0.0, 1000.0]
    auto pos_it = initial_state.find("position");
    if (pos_it != initial_state.end()) {
        try {
            position = std::any_cast<std::array<double, 3>>(pos_it->second);
        } catch (const std::bad_any_cast&) {
            // Fallback to zeros if cast fails
            position = {0.0, 0.0, 1000.0};
        }
    } else {
        position = {0.0, 0.0, 1000.0};
    }

    // Extract velocity with default [200.0, 0.0, 0.0]
    auto vel_it = initial_state.find("velocity");
    if (vel_it != initial_state.end()) {
        try {
            velocity = std::any_cast<std::array<double, 3>>(vel_it->second);
        } catch (const std::bad_any_cast&) {
            velocity = {200.0, 0.0, 0.0};
        }
    } else {
        velocity = {200.0, 0.0, 0.0};
    }

    // Extract roll with default 0.0
    auto roll_it = initial_state.find("roll");
    if (roll_it != initial_state.end()) {
        try {
            roll = std::any_cast<double>(roll_it->second);
        } catch (const std::bad_any_cast&) {
            roll = 0.0;
        }
    } else {
        roll = 0.0;
    }

    // Extract pitch with default 0.0
    auto pitch_it = initial_state.find("pitch");
    if (pitch_it != initial_state.end()) {
        try {
            pitch = std::any_cast<double>(pitch_it->second);
        } catch (const std::bad_any_cast&) {
            pitch = 0.0;
        }
    } else {
        pitch = 0.0;
    }

    // Extract yaw with default from velocity direction
    auto yaw_it = initial_state.find("yaw");
    if (yaw_it != initial_state.end()) {
        try {
            yaw = std::any_cast<double>(yaw_it->second);
        } catch (const std::bad_any_cast&) {
            yaw = std::atan2(velocity[1], velocity[0]);
        }
    } else {
        yaw = std::atan2(velocity[1], velocity[0]);
    }
}

void SimpleFDM::step(const std::map<std::string, double>& action) {
    // Extract and clamp normalized commands
    double delta_heading_cmd = 0.0;
    auto heading_it = action.find("delta_heading");
    if (heading_it != action.end()) {
        delta_heading_cmd = heading_it->second;
    }

    double delta_altitude_cmd = 0.0;
    auto altitude_it = action.find("delta_altitude");
    if (altitude_it != action.end()) {
        delta_altitude_cmd = altitude_it->second;
    }

    double delta_speed_cmd = 0.0;
    auto speed_it = action.find("delta_speed");
    if (speed_it != action.end()) {
        delta_speed_cmd = speed_it->second;
    }

    double delta_heading_rate = norm(
        delta_heading_cmd * max_turn_rate,
        -max_turn_rate,
        max_turn_rate
    );

    double delta_altitude_rate = norm(
        delta_altitude_cmd * max_climb_rate,
        -max_climb_rate,
        max_climb_rate
    );

    double delta_speed_rate = norm(
        delta_speed_cmd * max_acceleration,
        -max_acceleration,
        max_acceleration
    );

    // Altitude constraints near bounds
    if (position[2] > max_altitude - 200) {
        delta_altitude_rate = std::min(delta_altitude_rate, 0.0);
    }

    if (position[2] < min_altitude + 200) {
        delta_altitude_rate = std::max(delta_altitude_rate, 0.0);
    }

    // Convert rates to changes over dt
    double delta_heading = delta_heading_rate * dt;
    double delta_altitude = delta_altitude_rate * dt;
    double delta_speed = delta_speed_rate * dt;

    // Update speed
    double current_speed = get_speed();
    double new_speed = norm(
        current_speed + delta_speed,
        min_speed,
        max_speed
    );

    // Update heading
    double current_heading = get_heading();
    double new_heading = normalize_angle(current_heading + delta_heading);

    // Update altitude via climb rate
    double new_altitude = norm(
        position[2] + delta_altitude,
        min_altitude,
        max_altitude
    );
    delta_altitude = new_altitude - position[2];

    // Calculate pitch angle from altitude change
    double current_pitch = get_pitch();
    double horizontal_speed = new_speed * std::cos(current_pitch);
    double expected_pitch;
    if (horizontal_speed > 1.0) {
        expected_pitch = std::atan2(-delta_altitude_rate, horizontal_speed);
        expected_pitch = norm(expected_pitch, -deg2rad(45.0), deg2rad(45.0));  // Limit to ±45 degrees
    } else {
        expected_pitch = 0.0;
    }

    double delta_pitch = expected_pitch - current_pitch;
    delta_pitch = norm(delta_pitch, -DELTA_PITCH_MAX, DELTA_PITCH_MAX);
    double new_pitch = current_pitch + delta_pitch;

    // Update velocity vector in NWU frame
    velocity[0] = new_speed * std::cos(new_pitch) * std::cos(new_heading);  // North
    velocity[1] = new_speed * std::cos(new_pitch) * std::sin(new_heading);  // West
    velocity[2] = new_speed * std::sin(-new_pitch);                         // Up

    // Update position
    position[0] += velocity[0] * dt;
    position[1] += velocity[1] * dt;
    position[2] += velocity[2] * dt;

    // Update attitude
    yaw = new_heading;
    pitch = new_pitch;

    // Ensure altitude bounds
    position[2] = norm(position[2], min_altitude, max_altitude);
    if (position[2] == min_altitude || position[2] == max_altitude) {
        velocity[2] = 0.0;
    }
}

void SimpleFDM::set_aircraft_parameters(const std::map<std::string, double>& params) noexcept {
    for (const auto& [key, value] : params) {
        if (key == "max_speed") {
            max_speed = value;
        } else if (key == "min_speed") {
            min_speed = value;
        } else if (key == "max_turn_rate") {
            max_turn_rate = value;
        } else if (key == "max_climb_rate") {
            max_climb_rate = value;
        } else if (key == "max_acceleration") {
            max_acceleration = value;
        } else if (key == "max_g") {
            max_g = value;
        } else if (key == "min_altitude") {
            min_altitude = value;
        } else if (key == "max_altitude") {
            max_altitude = value;
        }
        // DELTA_PITCH_MAX is calculated from max_turn_rate and dt, so we recalculate it
        // if the underlying parameters change
        if (key == "dt") {
            DELTA_PITCH_MAX = deg2rad(15) / (1 / value);
        }
    }
}

}