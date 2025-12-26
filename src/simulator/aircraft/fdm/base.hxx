#pragma once

#include "c3utils/c3utils.hxx"
#include <array>
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

class BaseFDM {
protected:
    double dt;

    std::array<double, 3> position;
    std::array<double, 3> velocity;
    double roll;
    double pitch;
    double yaw;
    bool terminate;

public:
    explicit BaseFDM(double dt = 0.1) noexcept;

    virtual ~BaseFDM() noexcept = default;

    virtual void reset(const std::map<std::string, std::any>& initial_state) = 0;

    virtual void step(const std::map<std::string, double>& action) = 0;

    std::array<double, 3> get_position() const noexcept;
    std::array<double, 3> get_velocity() const noexcept;
    double get_speed() const noexcept;
    double get_heading() const noexcept;
    c3utils::Vector3 get_heading_vec() const noexcept;
    double get_pitch() const noexcept;
    double get_roll() const noexcept;
    std::array<double, 3> get_rpy() const noexcept;

    void set_position(const std::array<double, 3>& pos) noexcept;
    void set_velocity(const std::array<double, 3>& vel) noexcept;
    void set_attitude(double roll_, double pitch_, double yaw_) noexcept;

    std::map<std::string, std::any> get_state_dict() const noexcept;

    bool is_terminated() const noexcept { return terminate; };

protected:
    double normalize_angle(double angle) const noexcept;
};

}
