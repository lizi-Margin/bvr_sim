#include "base.hxx"
#include <cmath>
#include <random>
#include <sstream>
#include <iomanip>
#include "c3utils/c3utils.hxx"

namespace bvr_sim {


GroundUnit::GroundUnit(
    const std::string& uid,
    const std::string& model,
    TeamColor color,
    const std::array<double, 3>& position,
    double dt,
    SOT type_
) noexcept : SimulatedObject(
        uid,
        color,
        {position[0], position[1], _get_terrain_height(position[0], position[1])},
        {0.0, 0.0, 0.0},
        dt,
        type_
    ),
    model(model),
    bloods(100.0),
    _collision_radius(10.0),
    _log_tacview_Type("") {

    // Initialize random yaw for logging
    static thread_local std::mt19937 generator{std::random_device{}()};
    static thread_local std::uniform_real_distribution<double> distribution(-c3u::pi, c3u::pi);
    _yaw_for_log = distribution(generator);
}

double GroundUnit::get_heading() const noexcept {
    return _yaw_for_log;
}

double GroundUnit::_get_terrain_height(double x, double y) const noexcept {
    std::cout << "get_terrain_height: " << x << ", " << y << "called, but not implemented" << std::endl;
    // Random terrain height between 0 and 50 meters
    static thread_local std::mt19937 generator{std::random_device{}()};
    static thread_local std::uniform_int_distribution<int> distribution(0, 50);
    return static_cast<double>(distribution(generator));
}

bool GroundUnit::check_collision(const std::array<double, 3>& point) const noexcept {
    double distance = std::sqrt(
        std::pow(position[0] - point[0], 2) +
        std::pow(position[1] - point[1], 2) +
        std::pow(position[2] - point[2], 2)
    );
    return distance <= _collision_radius;
}

void GroundUnit::step() {
    // Ground units are static by default
}

void GroundUnit::hit(double damage) {
    if (damage <= 0.0) {
        bloods = 0.0;
    } else {
        bloods -= damage;
    }
    if (bloods <= 0.0) {
        is_alive = false;
    }
}

std::string GroundUnit::log() noexcept {
    auto [lon, lat, alt] = NWU2LLA(position[0], position[1], position[2]);

    std::ostringstream msg;
    msg << std::fixed << std::setprecision(6);

    if (is_alive) {
        msg << uid << ",T=" << lon << "|" << lat << "|" << alt << "|0.0|0.0|" << -c3u::rad2deg(get_heading()) << ",";
        msg << "Name=" << model << ",Color=" << (color == TeamColor::Red ? "Red" : "Blue") << _log_tacview_Type;
        msg << "\n";
        return msg.str();
    } else if (!render_explosion) {
        msg << uid << ",T=" << lon << "|" << lat << "|" << alt << "|0.0|0.0|" << -c3u::rad2deg(get_heading()) << ",";
        msg << "Name=" << model << ",Color=" << (color == TeamColor::Red ? "Red" : "Blue") << _log_tacview_Type;
        msg << "\n";

        // Cast away const for render_explosion modification
        render_explosion = true;

        msg << "-" << uid << "\n";
        std::string explosion_id = uid + get_new_uuid();
        msg << explosion_id << ",T=" << lon << "|" << lat << "|" << alt << ",Type=Explosion + Large\n";
        return msg.str();
    } else {
        return "";
    }
}

}