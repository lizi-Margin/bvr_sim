#pragma once
#include "simulator/simulator.hxx"
#include "simulator/environment.hxx"
#include "simulator/ground/base.hxx"
#include "so_pool.hxx"
#include <cmath>
#include <optional>

namespace bvr_sim {
// Preserved Alpha Mk-82 approximation: explicit Euler, v-squared drag and gravity.
// Pure prediction and released weapons call this same core service.
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt);
std::array<double,3> refine_ballistic_contact(const std::array<double,3>& previous,
                                             const std::array<double,3>& candidate,const Terrain& terrain);
std::optional<std::array<double, 3>> predict_ballistic_impact(std::array<double, 3> position,
                                                              std::array<double, 3> velocity,
                                                              const Terrain &terrain, double dt,
                                                              int max_steps = 6000,bool refined_contact = false);
inline double bomb_distance(const std::array<double, 3> &a, const std::array<double, 3> &b) {
    return std::hypot(std::hypot(a[0] - b[0], a[1] - b[1]), a[2] - b[2]);
}
class Mk82Bomb final : public SimulatedObject {
  public:
    std::shared_ptr<const Terrain> terrain;
    std::string owner;
    bool impacted = false;
    Mk82Bomb(std::string id, const SimulatedObject &parent, std::shared_ptr<const Terrain> surface,
             double timestep)
        : SimulatedObject(id, parent.color, parent.position, parent.velocity, timestep, SOT::Bomb),
          terrain(std::move(surface)), owner(parent.uid) {
        position[2] -= 2.0;
    }
    void step() override {
        if (!is_alive)
            return;
        const auto previous = position;
        ballistic_step(position, velocity, dt);
        if (position[2] <= terrain->collision_height(position[0], position[1])) {
            position=refine_ballistic_contact(previous,position,*terrain);
            for (const auto &obj : SOPool::instance().get_all()) {
                if (obj->color == color || !obj->is_alive)
                    continue;
                if (auto ground = std::dynamic_pointer_cast<GroundUnit>(obj))
                    if (bomb_distance(position, ground->position) <= 45.0)
                        ground->hit();
            }
            impacted = true;
            is_alive = false;
        }
    }
    std::string log() noexcept override { return {}; }
};

} // namespace bvr_sim
