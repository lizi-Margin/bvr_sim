#include "base.hxx"
#include <cmath>

namespace bvr_sim {

using namespace c3utils;

BaseFDM::BaseFDM(double dt) noexcept
    : dt(dt),
      position{0.0, 0.0, 0.0},
      velocity{0.0, 0.0, 0.0},
      roll(0.0),
      pitch(0.0),
      yaw(0.0),
      terminate(false) {}

std::array<double, 3> BaseFDM::get_position() const noexcept {
    return position;
}

std::array<double, 3> BaseFDM::get_velocity() const noexcept {
    return velocity;
}

double BaseFDM::get_speed() const noexcept {
    return std::sqrt(velocity[0] * velocity[0] +
                    velocity[1] * velocity[1] +
                    velocity[2] * velocity[2]);
}

double BaseFDM::get_heading() const noexcept {
    return yaw;
}

Vector3 BaseFDM::get_heading_vec() const noexcept {
    return Vector3(1, 0, 0).rotate_zyx_self(roll, pitch, yaw);
}

double BaseFDM::get_pitch() const noexcept {
    return pitch;
}

double BaseFDM::get_roll() const noexcept {
    return roll;
}

std::array<double, 3> BaseFDM::get_rpy() const noexcept {
    return {roll, pitch, yaw};
}

void BaseFDM::set_position(const std::array<double, 3>& pos) noexcept {
    position = pos;
}

void BaseFDM::set_velocity(const std::array<double, 3>& vel) noexcept {
    velocity = vel;
}

void BaseFDM::set_attitude(double roll_, double pitch_, double yaw_) noexcept {
    roll = roll_;
    pitch = pitch_;
    yaw = yaw_;
}

double BaseFDM::normalize_angle(double angle) const noexcept {
    return norm_pi(angle);
}

std::map<std::string, std::any> BaseFDM::get_state_dict() const noexcept {
    std::map<std::string, std::any> state;
    state["position"] = position;
    state["velocity"] = velocity;
    state["roll"] = roll;
    state["pitch"] = pitch;
    state["yaw"] = yaw;
    return state;
}

}
