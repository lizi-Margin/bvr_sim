#include "ground_factory.hxx"
#include "slamraam.hxx"
#include "ground_static_target.hxx"
#include "so_pool.hxx"
#include <stdexcept>
namespace bvr_sim {
std::shared_ptr<GroundUnit> create_ground_unit(const GroundUnitSpec &s, std::shared_ptr<const Terrain> env,
                                               double dt) {
    if (!env || s.uid.empty() || SOPool::instance().get(s.uid))
        throw std::invalid_argument("Missing environment or duplicate ground UID");
    if (s.team != "red" && s.team != "blue")
        throw std::invalid_argument("Invalid ground team");
    for (double x : s.position)
        if (!std::isfinite(x))
            throw std::invalid_argument("Invalid ground position");
    TeamColor color = s.team == "blue" ? TeamColor::Blue : TeamColor::Red;
    std::shared_ptr<GroundUnit> result;
    if (s.kind == "vehicle") {
        auto v = std::make_shared<GroundVehicle>(s.uid, s.model, color, s.position, env, dt);
        if (!s.route.points.empty())
            v->set_route(s.route);
        result = v;
    } else if (s.kind == "sam") {
        if (s.missiles < 0 || s.missiles > 12)
            throw std::invalid_argument("Invalid SAM magazine");
        auto contact = env->contact(s.position[0], s.position[1], 0, s.position[2]);
        if (contact.water ||
            env->blocked(s.position[0], s.position[1], contact.height + .1, contact.height + 2, 1))
            throw std::invalid_argument("SAM spawn intersects water/obstacle");
        auto position = s.position;
        position[2] = contact.height;
        auto sam = std::make_shared<SLAMRAAM>(s.uid, color, position, dt, s.missiles);
        sam->environment = env;
        result = sam;
    } else if (s.kind == "static")
        result = std::make_shared<GroundStaticTarget>(s.uid, color, s.position, dt);
    else
        throw std::invalid_argument("Unknown ground kind");
    SOPool::instance().add(result);
    return result;
}
} // namespace bvr_sim
