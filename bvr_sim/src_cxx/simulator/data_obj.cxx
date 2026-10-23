#include "data_obj.hxx"
#include <random>
#include <cmath>
#include <sstream>
#include <iomanip>
#include <mutex>

namespace bvr_sim {
namespace {
std::mutex noise_mutex;
std::optional<std::mt19937_64> seeded_position_noise, seeded_velocity_noise;
}
void DataObj::set_noise_seed(std::optional<uint64_t> seed) noexcept {
    std::lock_guard<std::mutex> lock(noise_mutex);
    if(seed) {
        seeded_position_noise.emplace(*seed);
        seeded_velocity_noise.emplace(*seed ^ 0x9e3779b97f4a7c15ULL);
    } else {
        seeded_position_noise.reset();
        seeded_velocity_noise.reset();
    }
}

DataObj::DataObj(
    const std::shared_ptr<SimulatedObject>& source_obj,
    double noise_std_position,
    double noise_std_velocity
) noexcept
    : source(source_obj),
      uid(source_obj->uid),
      color(source_obj->color),
      dt(source_obj->dt),
      is_alive(source_obj->is_alive),
      position(add_position_error(source_obj->position, noise_std_position)),
      velocity(add_velocity_error(source_obj->velocity, noise_std_velocity)),
      name_suffix("0" + SimulatedObject::get_new_uuid()),
      noise_std_position(noise_std_position),
      noise_std_velocity(noise_std_velocity),
      true_position(source_obj->position),
      true_velocity(source_obj->velocity) {
}

std::array<double, 3> DataObj::add_position_error(
    const std::array<double, 3>& true_pos,
    double std_dev
) noexcept {
    if (std_dev <= 0) {
        return true_pos;
    }

    static thread_local std::random_device rd;
    static thread_local std::mt19937 gen(rd());
    std::normal_distribution<double> dist(0.0, std_dev);

    std::lock_guard<std::mutex> lock(noise_mutex);
    if(seeded_position_noise)
        return {true_pos[0]+dist(*seeded_position_noise),true_pos[1]+dist(*seeded_position_noise),true_pos[2]+dist(*seeded_position_noise)};

    std::array<double, 3> result;
    result[0] = true_pos[0] + dist(gen);
    result[1] = true_pos[1] + dist(gen);
    result[2] = true_pos[2] + dist(gen);

    return result;
}

std::array<double, 3> DataObj::add_velocity_error(
    const std::array<double, 3>& true_vel,
    double std_dev
) noexcept {
    if (std_dev <= 0) {
        return true_vel;
    }

    static thread_local std::random_device rd;
    static thread_local std::mt19937 gen(rd());
    std::normal_distribution<double> dist(0.0, std_dev);

    std::lock_guard<std::mutex> lock(noise_mutex);
    if(seeded_velocity_noise)
        return {true_vel[0]+dist(*seeded_velocity_noise),true_vel[1]+dist(*seeded_velocity_noise),true_vel[2]+dist(*seeded_velocity_noise)};

    std::array<double, 3> result;
    result[0] = true_vel[0] + dist(gen);
    result[1] = true_vel[1] + dist(gen);
    result[2] = true_vel[2] + dist(gen);

    return result;
}

void DataObj::step() noexcept {
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
