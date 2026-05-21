#pragma once

#include "register.hxx"
#include "sense/sensor_manager.hxx"
#include "support/colorful.hxx"
#include <string>
#include <array>
#include <vector>
#include <tuple>
#include <optional>
#include <memory>
#include <map>

namespace bvr_sim {

constexpr double REFERENCE_LON = 41.64821;
constexpr double REFERENCE_LAT = 42.23831;
constexpr double REFERENCE_ALT = 0.0;

std::tuple<double, double, double> NWU2LLA(double north, double west, double up) noexcept;

std::tuple<double, double, double> LLA2NWU(double lon, double lat, double alt) noexcept;

std::tuple<double, double, double> velocity_to_euler(const std::array<double, 3>& velocity, bool deg = false) noexcept;

enum class TeamColor {
    Red,
    Blue
};

enum class SOT {  // Simulated Object Type
    Unknown = 0,
    Aircraft,
    Missile,
    GroundUnit,
    AA,
    DataObj,
    MAX_SOT_VALUE
};

std::string SOT_to_string(SOT type) noexcept;

class SimulatedObject : public std::enable_shared_from_this<SimulatedObject> {
public:
    const SOT Type;
protected:
    int rubbish_countup;
public:
    const std::string uid;
    const TeamColor color;
    double dt;

    bool is_alive;

    std::array<double, 3> position;
    std::array<double, 3> velocity;

    std::vector<std::shared_ptr<SimulatedObject>> partners;
    std::vector<std::shared_ptr<SimulatedObject>> enemies;

protected:
    bool render_explosion;
    Register register_;
    std::unique_ptr<SensorManager> sensor_manager_;

public:
    SimulatedObject(
        const std::string& uid_,
        TeamColor color_,
        const std::array<double, 3>& position_,
        const std::array<double, 3>& velocity_,
        double dt_ = 0.1,
        SOT type_ = SOT::Unknown
    ) noexcept;

    virtual ~SimulatedObject() noexcept;
    bool trashed() const noexcept { return rubbish_countup > 0; }

    void tick() noexcept;

    virtual void step() = 0;

    virtual std::string log() noexcept = 0;

    virtual double get_speed() const noexcept;
    virtual double get_mach() const noexcept;
    virtual double get_roll() const noexcept;
    virtual double get_pitch() const noexcept;
    virtual double get_yaw() const noexcept;
    virtual std::array<double, 3> get_rpy() const noexcept;
    virtual double get_heading() const noexcept;
    virtual double get_altitude() const noexcept;

    void update_state(
        const std::optional<std::array<double, 3>>& position_ = std::nullopt,
        const std::optional<std::array<double, 3>>& velocity_ = std::nullopt
    ) noexcept;

    static std::string get_new_uuid() noexcept;

    std::optional<json::JSON> get(const std::string& key) const noexcept;
    bool set(const std::string& key, const json::JSON& value) noexcept;
    bool set_with_penalty(const std::string& key, const json::JSON& value, int penalty) noexcept;
    // Register& get_register() noexcept { return register_; }
    const Register& get_register() const noexcept { return register_; }
    virtual void write_register() noexcept;

    SensorManager& sensor_manager() noexcept;
    const SensorManager& sensor_manager() const noexcept;
    bool add_sensor(const std::string& name, const std::shared_ptr<SensorBase>& sensor) noexcept;
    void update_sensors() noexcept;
    std::shared_ptr<SensorBase> get_sensor(const std::string& name) const noexcept;
    const std::map<std::string, std::shared_ptr<SensorBase>>& get_sensors() const noexcept;

    void debug_print() const noexcept {
        colorful::printHUANG("SimulatedObject::DebugPrint");
        std::cout << "uid: " << uid << std::endl;
        std::cout << "Type: " << static_cast<int>(Type) << std::endl;
        std::string color_str = color == TeamColor::Red ? "Red" : "Blue";
        std::cout << "color: " << color_str << std::endl;
        std::cout << "position: " << position[0] << ", " << position[1] << ", " << position[2] << std::endl;
        std::cout << "velocity: " << velocity[0] << ", " << velocity[1] << ", " << velocity[2] << std::endl;
        std::cout << "speed: " << get_speed() << std::endl;
        std::cout << "mach: " << get_mach() << std::endl;
        std::cout << "heading: " << get_heading() << std::endl;
        std::cout << "altitude: " << get_altitude() << std::endl;
        colorful::printHUANG("=========================");
    }

    virtual void clean_up() noexcept {
        enemies.clear();
        partners.clear();
        if (sensor_manager_) {
            sensor_manager_->clear();
        }
    }
};

}
