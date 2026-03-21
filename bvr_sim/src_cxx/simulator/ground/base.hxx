#pragma once

#include "../simulator.hxx"
#include <string>
#include <array>

namespace bvr_sim {

class GroundUnit : public SimulatedObject {
protected:
    std::string model;
    double bloods;
    double _collision_radius;
    double _yaw_for_log;
    std::string _log_tacview_Type;

public:
    GroundUnit(
        const std::string& uid,
        const std::string& model,
        TeamColor color,
        const std::array<double, 3>& position,
        double dt = 0.1,
        SOT type_ = SOT::GroundUnit
    ) noexcept;

    ~GroundUnit() noexcept override = default;

    double get_heading() const noexcept override;

    virtual void step() override;

    void hit(double damage = 0.0);

    bool check_collision(const std::array<double, 3>& point) const noexcept;

    std::string log() noexcept override;

protected:
    double _get_terrain_height(double x, double y) const noexcept;
};

}