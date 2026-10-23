#include "vehicle.hxx"
#include "so_pool.hxx"
#include <cmath>
#include <algorithm>
#include <stdexcept>

namespace bvr_sim {
GroundVehicle::GroundVehicle(const std::string &uid, const std::string &model, TeamColor color,
                             const std::array<double, 3> &initial, std::shared_ptr<const Terrain> environment,
                             double dt, VehicleParameters config)
    : GroundUnit(uid, model, color, initial, dt), environment_(std::move(environment)),
      initial_position_(initial), parameters(config) {
    if (!environment_ || !std::isfinite(dt) || dt <= 0 || dt > .1)
        throw std::invalid_argument("Vehicle environment/dt");
    _collision_radius = parameters.radius;
    reset();
}
void GroundVehicle::set_route(const VehicleRoute &command) {
    if (command.points.empty() || command.points.size() > 4096 || !std::isfinite(command.speed) ||
        command.speed < 0 || command.speed > parameters.max_speed)
        throw std::invalid_argument("Vehicle route/speed");
    for (auto p : command.points)
        for (double x : p)
            if (!std::isfinite(x))
                throw std::invalid_argument("Non-finite waypoint");
    route = command;
    waypoint = 0;
    blocked_reason.clear();
    while (waypoint + 1 < route.points.size() &&
           std::hypot(position[0] - route.points[waypoint][0], position[1] - route.points[waypoint][1]) <
               parameters.waypoint_radius)
        ++waypoint;
    if (speed_ < .01)
        yaw_ = std::atan2(route.points[waypoint][1] - position[1], route.points[waypoint][0] - position[0]);
    motion = parking ? "parking" : "moving";
}
void GroundVehicle::set_parking(bool stopped) { parking = stopped; }
void GroundVehicle::reset() {
    position = initial_position_;
    velocity = {0, 0, 0};
    speed_ = yaw_ = pitch_ = roll_ = 0;
    bloods = 100;
    is_alive = true;
    rubbish_countup = -20;
    render_explosion = false;
    waypoint = 0;
    parking = false;
    blocked_reason.clear();
    route = {};
    motion = "idle";
    auto ground = environment_->contact(position[0], position[1], 0, position[2], parameters.max_step);
    if (ground.water || environment_->blocked(position[0], position[1], ground.height + .1,
                                              ground.height + parameters.height, parameters.radius))
        throw std::invalid_argument("Vehicle spawn intersects water or obstacle");
    position[2] = ground.height;
    contact_surface = ground.surface_id;
}
void GroundVehicle::step() {
    if (!is_alive) {
        speed_ = 0;
        velocity = {0, 0, 0};
        motion = "destroyed";
        return;
    }
    double target = 0, distance = 0, error = 0;
    if (!route.points.empty() && waypoint < route.points.size()) {
        auto point = route.points[waypoint];
        double dn = point[0] - position[0], dw = point[1] - position[1];
        distance = std::hypot(dn, dw);
        if (distance < parameters.waypoint_radius) {
            if (waypoint + 1 < route.points.size())
                ++waypoint;
            else if (route.loop)
                waypoint = 0;
            else {
                waypoint = route.points.size();
                motion = "arrived";
            }
        }
        if (waypoint < route.points.size()) {
            point = route.points[waypoint];
            dn = point[0] - position[0];
            dw = point[1] - position[1];
            distance = std::hypot(dn, dw);
            error = std::remainder(std::atan2(dw, dn) - yaw_, 2 * std::acos(-1.0));
            target = std::min(route.speed, std::sqrt(2 * parameters.brake * std::max(0., distance - .5)));
            target *= std::max(.12, std::cos(error));
        }
    }
    if (parking)
        target = 0;
    double candidate_speed =
        speed_ + std::clamp(target - speed_, -parameters.brake * dt, parameters.acceleration * dt);
    double new_yaw = yaw_ + std::clamp(error, -parameters.yaw_rate * dt, parameters.yaw_rate * dt);
    double n = position[0] + std::cos(new_yaw) * candidate_speed * dt,
           w = position[1] + std::sin(new_yaw) * candidate_speed * dt;
    auto ground = environment_->contact(n, w, new_yaw, position[2], parameters.max_step);
    bool touches_water = ground.water;
    for (int i = 0; i < 8 && !touches_water && !environment_->water_regions.empty(); ++i) {
        double angle = i * std::acos(-1.0) / 4;
        touches_water =
            environment_->water_at(n + std::cos(angle) * parameters.radius,
                                   w + std::sin(angle) * parameters.radius, position[2], parameters.max_step);
    }
    std::string reason;
    if (touches_water)
        reason = "water";
    else if (ground.grade > parameters.max_grade)
        reason = "slope";
    else if (std::abs(ground.height - position[2]) > parameters.max_step)
        reason = "step";
    else if (environment_->blocked(n, w, ground.height + .1, ground.height + parameters.height,
                                   parameters.radius))
        reason = "obstacle";
    if (reason.empty())
        for (const auto &other : SOPool::instance().get_all())
            if (other.get() != this && other->is_alive &&
                (other->Type == SOT::GroundUnit || other->Type == SOT::AA) &&
                std::hypot(n - other->position[0], w - other->position[1]) < 2 * parameters.radius &&
                std::abs(ground.height - other->position[2]) < parameters.height) {
                reason = "unit";
                break;
            }
    if (!reason.empty()) {
        speed_ = 0;
        velocity = {0, 0, 0};
        blocked_reason = reason;
        motion = "blocked";
        return;
    }
    auto previous = position;
    position = {n, w, ground.height};
    yaw_ = new_yaw;
    pitch_ = ground.pitch;
    roll_ = ground.roll;
    for (int i = 0; i < 3; ++i)
        velocity[i] = (position[i] - previous[i]) / dt;
    speed_ = candidate_speed;
    contact_surface = ground.surface_id;
    blocked_reason.clear();
    if (parking)
        motion = speed_ < .01 ? "parked" : "braking";
    else if (speed_ > .01)
        motion = "moving";
    else
        motion = !route.points.empty() && waypoint >= route.points.size() ? "arrived" : "idle";
}
} // namespace bvr_sim
