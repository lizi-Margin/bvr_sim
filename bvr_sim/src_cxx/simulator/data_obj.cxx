#include "data_obj.hxx"
#include <random>
#include <cmath>
#include <sstream>
#include <iomanip>

namespace bvr_sim {

DataObj::DataObj(
    const std::shared_ptr<SimulatedObject>& source_obj,
    double noise_std_position,
    double noise_std_velocity
) noexcept
    : SimulatedObject(
        source_obj->uid,
        source_obj->color,
        add_position_error(source_obj->position, noise_std_position),
        add_velocity_error(source_obj->velocity, noise_std_velocity),
        source_obj->dt,
        SOT::DataObj
      ),
      source(source_obj),
      name_suffix("0" + get_new_uuid()),
      noise_std_position(noise_std_position),
      noise_std_velocity(noise_std_velocity),
      true_position(source_obj->position),
      true_velocity(source_obj->velocity) {
}

std::array<double, 3> DataObj::add_position_error(
    const std::array<double, 3>& true_pos,
    double std_dev
) const noexcept {
    if (std_dev <= 0) {
        return true_pos;
    }

    static thread_local std::random_device rd;
    static thread_local std::mt19937 gen(rd());
    std::normal_distribution<double> dist(0.0, std_dev);

    std::array<double, 3> result;
    result[0] = true_pos[0] + dist(gen);
    result[1] = true_pos[1] + dist(gen);
    result[2] = true_pos[2] + dist(gen);

    return result;
}

std::array<double, 3> DataObj::add_velocity_error(
    const std::array<double, 3>& true_vel,
    double std_dev
) const noexcept {
    if (std_dev <= 0) {
        return true_vel;
    }

    static thread_local std::random_device rd;
    static thread_local std::mt19937 gen(rd());
    std::normal_distribution<double> dist(0.0, std_dev);

    std::array<double, 3> result;
    result[0] = true_vel[0] + dist(gen);
    result[1] = true_vel[1] + dist(gen);
    result[2] = true_vel[2] + dist(gen);

    return result;
}

void DataObj::step() {
}

std::string DataObj::log() noexcept {
    if (!is_alive) {
        return "";
    }

    auto [lon, lat, alt] = NWU2LLA(position[0], position[1], position[2]);

    auto [roll_deg, pitch_deg, yaw_deg] = velocity_to_euler(velocity, true);

    std::stringstream ss;
    ss << std::fixed << std::setprecision(6);
    ss << uid << name_suffix << ","
       << "T=" << lon << "|" << lat << "|" << alt << "|"
       << roll_deg << "|" << pitch_deg << "|" << yaw_deg << ","
       << "Name=" << uid << name_suffix << ","
       << "Type=" << "Navaid + Static" << ","
       << "Color=";

    if (color == TeamColor::Red) {
        ss << "Red";
    } else {
        ss << "Blue";
    }

    ss << ","
       << "Radius=5,"
       << "Visible=1,"
       << "\n";

    return ss.str();
}

std::array<double, 3> DataObj::get_position_error() const noexcept {
    return {
        position[0] - true_position[0],
        position[1] - true_position[1],
        position[2] - true_position[2]
    };
}

std::array<double, 3> DataObj::get_velocity_error() const noexcept {
    return {
        velocity[0] - true_velocity[0],
        velocity[1] - true_velocity[1],
        velocity[2] - true_velocity[2]
    };
}

double DataObj::get_position_error_magnitude() const noexcept {
    auto error = get_position_error();
    return std::sqrt(error[0] * error[0] + error[1] * error[1] + error[2] * error[2]);
}

double DataObj::get_velocity_error_magnitude() const noexcept {
    auto error = get_velocity_error();
    return std::sqrt(error[0] * error[0] + error[1] * error[1] + error[2] * error[2]);
}

}
