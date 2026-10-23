#include "mk82.hxx"
namespace bvr_sim {
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt) {
    const double speed = std::hypot(std::hypot(velocity[0], velocity[1]), velocity[2]);
    for (int i = 0; i < 3; ++i)
        velocity[i] -= 0.00003 * speed * velocity[i] * dt;
    velocity[2] -= 9.80665 * dt;
    for (int i = 0; i < 3; ++i)
        position[i] += velocity[i] * dt;
}

std::optional<std::array<double, 3>> predict_ballistic_impact(std::array<double, 3> p,
                                                              std::array<double, 3> v, const Terrain &terrain,
                                                              double dt, int max_steps) {
    p[2] -= 2;
    for (int i = 0; i < max_steps; ++i) {
        ballistic_step(p, v, dt);
        if (p[2] <= terrain.collision_height(p[0], p[1])) {
            p[2] = terrain.collision_height(p[0], p[1]);
            return p;
        }
    }
    return std::nullopt;
}
} // namespace bvr_sim
