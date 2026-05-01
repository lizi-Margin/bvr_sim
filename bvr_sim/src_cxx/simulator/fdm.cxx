#include "fdm.hxx"
#include <cmath>

namespace bvr_sim {

using namespace c3utils;

FDM_API::FDM_API(double dt) noexcept
    : dt(dt),
      position{0.0, 0.0, 0.0},
      velocity{0.0, 0.0, 0.0},
      roll(0.0),
      pitch(0.0),
      yaw(0.0) {}

std::array<double, 3> FDM_API::get_position() const noexcept {
    return position;
}

std::array<double, 3> FDM_API::get_velocity() const noexcept {
    return velocity;
}

double FDM_API::get_speed() const noexcept {
    return std::sqrt(velocity[0] * velocity[0] +
                    velocity[1] * velocity[1] +
                    velocity[2] * velocity[2]);
}

double FDM_API::get_heading() const noexcept {
    return yaw;
}

Vector3 FDM_API::get_heading_vec() const noexcept {
    return Vector3(1, 0, 0).rotate_zyx_self(roll, pitch, yaw);
}

double FDM_API::get_pitch() const noexcept {
    return pitch;
}

double FDM_API::get_roll() const noexcept {
    return roll;
}

std::array<double, 3> FDM_API::get_rpy() const noexcept {
    return {roll, pitch, yaw};
}

void FDM_API::set_position(const std::array<double, 3>& pos) noexcept {
    position = pos;
}

void FDM_API::set_velocity(const std::array<double, 3>& vel) noexcept {
    velocity = vel;
}

void FDM_API::set_attitude(double roll_, double pitch_, double yaw_) noexcept {
    roll = roll_;
    pitch = pitch_;
    yaw = yaw_;
}

double FDM_API::normalize_angle(double angle) const noexcept {
    return norm_pi(angle);
}

std::map<std::string, std::any> FDM_API::get_state_dict() const noexcept {
    std::map<std::string, std::any> state;
    state["position"] = position;
    state["velocity"] = velocity;
    state["roll"] = roll;
    state["pitch"] = pitch;
    state["yaw"] = yaw;
    return state;
}

}

