#pragma once
#include "simulator/simulator.hxx"
#include "simulator/environment.hxx"
#include "simulator/ground/base.hxx"
#include "so_pool.hxx"
#include <cmath>
#include <optional>

namespace bvr_sim {
// Developer-owned Alpha model parameters; preserve the existing physical approximation.
struct Mk82Parameters {
    double quadratic_drag = .00003; // acceleration coefficient, 1/m
    double gravity = 9.80665;       // m/s^2
    double release_drop = 2.;       // m below the carrier reference
    double blast_radius = 45.;      // m, existing simplified ground damage radius
};
inline constexpr Mk82Parameters default_mk82_parameters{};
// Preserved Alpha Mk-82 approximation: explicit Euler, v-squared drag and gravity.
// Pure prediction and released weapons call this same core service.
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt,
                    const Mk82Parameters& parameters = default_mk82_parameters);
std::array<double,3> refine_ballistic_contact(const std::array<double,3>& previous,
                                             const std::array<double,3>& candidate,const Terrain& terrain);
std::optional<std::array<double, 3>> predict_ballistic_impact(std::array<double, 3> position,
                                                              std::array<double, 3> velocity,
                                                              const Terrain &terrain, double dt,
                                                              int max_steps = 6000,bool refined_contact = false,
                                                              const Mk82Parameters& parameters = default_mk82_parameters);
inline double bomb_distance(const std::array<double, 3> &a, const std::array<double, 3> &b) {
    return std::hypot(std::hypot(a[0] - b[0], a[1] - b[1]), a[2] - b[2]);
}
class Mk82Bomb final : public SimulatedObject {
  public:
    std::shared_ptr<const Terrain> terrain;
    std::string owner;
    bool impacted = false;
    Mk82Parameters parameters;
    Mk82Bomb(std::string id, const SimulatedObject &parent, std::shared_ptr<const Terrain> surface,
             double timestep,const Mk82Parameters& parameters = default_mk82_parameters);
    void step() override;
    std::string log() noexcept override { return {}; }
};

} // namespace bvr_sim
