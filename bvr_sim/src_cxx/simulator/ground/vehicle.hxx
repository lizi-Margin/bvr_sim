#pragma once
#include "base.hxx"
#include "simulator/environment.hxx"
#include "ground_types.hxx"
#include <memory>

namespace bvr_sim {
// Kinematic bicycle-like route follower. No tire, suspension or armor simulation.
class GroundVehicle final : public GroundUnit {
    std::shared_ptr<const Terrain> environment_;
    std::array<double, 3> initial_position_{};
    double yaw_ = 0, pitch_ = 0, roll_ = 0, speed_ = 0;

  public:
    VehicleParameters parameters;
    VehicleRoute route;
    size_t waypoint = 0;
    bool parking = false;
    std::string motion = "idle", blocked_reason, contact_surface;
    GroundVehicle(const std::string &uid, const std::string &model, TeamColor color,
                  const std::array<double, 3> &position, std::shared_ptr<const Terrain> environment,
                  double dt = .02, VehicleParameters parameters = {});
    void set_route(const VehicleRoute &command);
    void set_parking(bool parked);
    void reset();
    void step() override;
    double get_yaw() const noexcept override { return yaw_; }
    double get_pitch() const noexcept override { return pitch_; }
    double get_roll() const noexcept override { return roll_; }
    std::array<double, 3> get_rpy() const noexcept override { return {roll_, pitch_, yaw_}; }
    const std::string &model_id() const { return model; }
};
} // namespace bvr_sim
