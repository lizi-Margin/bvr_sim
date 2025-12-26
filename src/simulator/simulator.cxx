#include "simulator.hxx"
#include "register.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include <cmath>
#include <random>
#include <sstream>
#include <iomanip>
#include "c3utils/c3utils.hxx"

namespace bvr_sim {

using namespace c3utils;

std::string SOT_to_string(SOT type) noexcept {
    switch (type) {
        case SOT::Unknown: return "Unknown";
        case SOT::Aircraft: return "Aircraft";
        case SOT::Missile: return "Missile";
        case SOT::GroundUnit: return "GroundUnit";
        case SOT::AA: return "AA";
        case SOT::DataObj: return "DataObj";

        case SOT::MAX_SOT_VALUE:
        default:
            colorful::printHONG("SOT_to_string: Error type");
            check(false, "SOT_to_string: Error type");
    }
}

std::tuple<double, double, double> NWU2LLA(double north, double west, double up) noexcept {
    // auto result = NWU_to_LLA_deg_lowacc(north, west, up, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT);
    auto result = NWU_to_LLA_deg(north, west, up, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT);
    return std::make_tuple(result[0], result[1], result[2]);
}

std::tuple<double, double, double> LLA2NWU(double lon, double lat, double alt) noexcept {
    // auto result = LLA_to_NWU_deg_lowacc(lon, lat, alt, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT);
    auto result = LLA_to_NWU_deg(lon, lat, alt, REFERENCE_LON, REFERENCE_LAT, REFERENCE_ALT);
    return std::make_tuple(result[0], result[1], result[2]);
}

std::tuple<double, double, double> velocity_to_euler(const std::array<double, 3>& velocity, bool deg) noexcept {
    Vector3 vel_vec(velocity);
    auto angles = velocity_to_euler_NWU(vel_vec);
    double roll = angles[0];
    double pitch = angles[1];
    double yaw = angles[2];

    if (deg) {
        roll = rad2deg(roll);
        pitch = rad2deg(pitch);
        yaw = rad2deg(yaw);
    }

    return std::make_tuple(roll, pitch, yaw);
}

SimulatedObject::SimulatedObject(
    const std::string& uid_,
    TeamColor color_,
    const std::array<double, 3>& position_,
    const std::array<double, 3>& velocity_,
    double dt_,
    SOT type_
) noexcept
    : Type(type_),
      rubbish_countup(-20),
      uid(uid_),
      color(color_),
      dt(dt_),
      is_alive(true),
      position{0.0, 0.0, 0.0},
      velocity{0.0, 0.0, 0.0},
      render_explosion(false)
{
    update_state(position_, velocity_);
}

void SimulatedObject::tick() noexcept {
    check(static_cast<int>(Type) != static_cast<int>(SOT::Unknown), "SimulatedObject::tick: SOT::Unknown is not allowed");
    check(static_cast<int>(Type) > static_cast<int>(SOT::Unknown), "SimulatedObject::tick: Error type");
    check(static_cast<int>(Type) < static_cast<int>(SOT::MAX_SOT_VALUE), "SimulatedObject::tick: Error type");

    if (Type == SOT::DataObj) {
        colorful::printHUANG("SimulatedObject::tick: DataObj is not allowed to tick");
        SL::get().printf("[SimulatedObject] Warning: DataObj is not allowed to tick\n");
        return;
    }

    if(!is_alive) {
        if (rubbish_countup < std::numeric_limits<int>::max()){
            rubbish_countup++;
        }
    } else {
        step();
    }
    write_register();  //expose object state to register system, but may be a tiny bit slow
}  


double SimulatedObject::get_speed() const noexcept {
    return c3u::linalg_norm(velocity);
}

double SimulatedObject::get_mach() const noexcept {
    double speed_mps = get_speed();
    double altitude_m = position[2];
    return c3utils::get_mach(speed_mps, altitude_m);
}

double SimulatedObject::get_heading() const noexcept {
    return std::atan2(velocity[1], velocity[0]);
}

double SimulatedObject::get_altitude() const noexcept {
    return position[2];
}

void SimulatedObject::update_state(
    const std::optional<std::array<double, 3>>& position_,
    const std::optional<std::array<double, 3>>& velocity_
) noexcept {
    if (position_.has_value()) {
        position = position_.value();
    }
    if (velocity_.has_value()) {
        velocity = velocity_.value();
    }
}

std::string SimulatedObject::get_new_uuid() const noexcept {
    static std::random_device rd;
    static std::mt19937_64 gen(rd());
    static std::uniform_int_distribution<uint64_t> dis;

    uint64_t random_val = dis(gen);
    std::stringstream ss;
    ss << std::setw(8) << std::setfill('0') << (random_val % static_cast<uint64_t>(1e8));
    return ss.str();
}

std::optional<json::JSON> SimulatedObject::get(const std::string& key) const noexcept {
    return register_.get(key);
}

bool SimulatedObject::set(const std::string& key, const json::JSON& value) noexcept {
    return register_.set(key, value);
}

void SimulatedObject::write_register() noexcept {
    json::JSON Type_json = json::JSON::Make(json::JSON::Class::String);
    Type_json = SOT_to_string(Type);
    register_.set("Type", Type_json);

    json::JSON uid_json = json::JSON::Make(json::JSON::Class::String);
    uid_json = uid;
    register_.set("uid", uid_json);

    json::JSON color_json = json::JSON::Make(json::JSON::Class::String);
    check((color == TeamColor::Red) || (color == TeamColor::Blue), "color must be Red or Blue");
    color_json = color == TeamColor::Red ? "Red" : "Blue";
    register_.set("color", color_json);

    json::JSON dt_json = json::JSON::Make(json::JSON::Class::Floating);
    dt_json = dt;
    register_.set("dt", dt_json);

    json::JSON is_alive_json = json::JSON::Make(json::JSON::Class::Boolean);
    is_alive_json = is_alive;
    register_.set("is_alive", is_alive_json);

    json::JSON position_json = json::JSON::Make(json::JSON::Class::Array);
    position_json.append(position[0]);
    position_json.append(position[1]);
    position_json.append(position[2]);
    register_.set("position", position_json);
    json::JSON velocity_json = json::JSON::Make(json::JSON::Class::Array);
    velocity_json.append(velocity[0]);
    velocity_json.append(velocity[1]);
    velocity_json.append(velocity[2]);
    register_.set("velocity", velocity_json);
}

}
