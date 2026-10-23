#include "ground_radar.hxx"
#include "so_pool.hxx"
#include <cmath>
namespace bvr_sim {
void GroundSearchRadar::update(const SimulatedObject &owner, const Terrain &environment, double range) {
    contacts.clear();
    if (!owner.is_alive)
        return;
    auto eye = owner.position;
    eye[2] += 3;
    for (const auto &obj : SOPool::instance().get_all()) {
        if (!obj->is_alive || obj->Type != SOT::Aircraft || obj->color == owner.color)
            continue;
        double distance = std::hypot(std::hypot(obj->position[0] - eye[0], obj->position[1] - eye[1]),
                                     obj->position[2] - eye[2]);
        if (distance <= range && environment.line_of_sight(eye, obj->position))
            contacts[obj->uid] = {obj->uid, obj->position, obj->velocity, distance};
    }
}
} // namespace bvr_sim
