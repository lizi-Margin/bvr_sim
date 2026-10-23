#include "game_session.hxx"
#include "bsl_pool.hxx"
#include "core.hxx"
#include "global_config.hxx"
#include "simulator/aircraft/fighter.hxx"
#include "simulator/data_obj.hxx"
#include "simulator/ground/ground_static_target.hxx"
#include "simulator/missile/base.hxx"
#include "simulator/missile/aim120c.hxx"
#include "simulator/sense/radar.hxx"
#include "simulator/unit_factory.hxx"
#include "so_pool.hxx"
#include "support/SL.hxx"
#include <algorithm>
#include <atomic>
#include <cmath>
#include <random>
#include <stdexcept>

namespace bvr_sim {
namespace {
constexpr double pi = 3.14159265358979323846;
std::atomic<bool> session_owned{false};
double norm_angle(double x) { return std::remainder(x, 2 * pi); }
double distance(const std::array<double, 3> &a, const std::array<double, 3> &b) {
    return std::hypot(std::hypot(a[0] - b[0], a[1] - b[1]), a[2] - b[2]);
}
// An explicitly approximate 1-D launch zone, integrated with the same motor,
// mass, drag and minimum-Mach parameters as AIM120C. It is not a kill guarantee.
LaunchEnvelope launch_envelope(const Fighter &own, const std::array<double, 3> &position,
                               const std::array<double, 3> &velocity, const std::string &uid) {
    LaunchEnvelope zone;
    zone.target_uid = uid;
    zone.range = distance(own.position, position);
    if (zone.range < 1)
        return zone;
    double target_radial = 0, own_radial = 0, target_speed = 0;
    for (int i = 0; i < 3; ++i) {
        double axis = (position[i] - own.position[i]) / zone.range;
        target_radial += velocity[i] * axis;
        own_radial += own.velocity[i] * axis;
        target_speed += velocity[i] * velocity[i];
    }
    target_speed = std::sqrt(target_speed);
    zone.closing_speed = own_radial - target_radial;
    zone.bearing =
        norm_angle(std::atan2(position[1] - own.position[1], position[0] - own.position[0]) - own.get_yaw());
    using Key = std::pair<int, int>;
    static std::map<Key, std::vector<std::pair<double, double>>> cache;
    const double own_speed = std::hypot(std::hypot(own.velocity[0], own.velocity[1]), own.velocity[2]);
    Key key{int(std::round(own.position[2] / 250)), int(std::round(own_speed / 25))};
    auto found = cache.find(key);
    if (found == cache.end()) {
        if (cache.size() > 4096)
            cache.clear();
        MissileAerodynamics aero;
        const auto &p = default_missile_parameter;
        double travel = 0, v = key.second * 25.0;
        std::vector<std::pair<double, double>> samples;
        for (double t = 0; t < p.t_max; t += .5) {
            bool burn = t <= p.t_thrust;
            double mass = p.m0 - p.dm * std::min(t, p.t_thrust);
            double drag = aero.compute_drag(v, 0, key.first * 250.0).first;
            v += ((burn ? p.thrust : 0) - drag) / mass * .5;
            travel += std::max(0.0, v) * .5;
            samples.emplace_back(t + .5, travel);
            if (!burn && v < .8 * aero.speed_of_sound(key.first * 250.0))
                break;
        }
        found = cache.emplace(key, std::move(samples)).first;
    }
    zone.eta = -1;
    for (auto [time, travel] : found->second) {
        double range = travel - target_radial * time;
        zone.rmax = std::max(zone.rmax, range);
        zone.rtr = std::max(zone.rtr, travel - target_speed * time);
        if (zone.eta < 0 && range >= zone.range)
            zone.eta = time;
    }
    zone.in_range = zone.range <= zone.rmax && std::abs(zone.bearing) < pi / 3;
    return zone;
}
void ballistic_step(std::array<double, 3> &position, std::array<double, 3> &velocity, double dt) {
    const double speed = std::hypot(std::hypot(velocity[0], velocity[1]), velocity[2]);
    for (int i = 0; i < 3; ++i)
        velocity[i] -= 0.00003 * speed * velocity[i] * dt;
    velocity[2] -= 9.80665 * dt;
    for (int i = 0; i < 3; ++i)
        position[i] += velocity[i] * dt;
}

// Ballistics and ground damage live here, never in the render/input layer.
class GameBomb final : public SimulatedObject {
  public:
    std::shared_ptr<const GameTerrain> terrain;
    std::string owner;
    bool impacted = false;
    GameBomb(std::string id, const Fighter &parent, std::shared_ptr<const GameTerrain> surface,
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
        if (position[2] <= terrain->height(position[0], position[1])) {
            double low = 0, high = 1;
            for (int n = 0; n < 24; ++n) {
                const double t = (low + high) / 2;
                const double x = previous[0] + (position[0] - previous[0]) * t;
                const double y = previous[1] + (position[1] - previous[1]) * t;
                const double z = previous[2] + (position[2] - previous[2]) * t;
                if (z > terrain->height(x, y))
                    low = t;
                else
                    high = t;
            }
            for (int i = 0; i < 3; ++i)
                position[i] = previous[i] + (position[i] - previous[i]) * high;
            for (const auto &obj : SOPool::instance().get_all()) {
                if (obj->color == color || !obj->is_alive)
                    continue;
                if (auto ground = std::dynamic_pointer_cast<GroundUnit>(obj))
                    if (distance(position, ground->position) <= 45.0)
                        ground->hit();
            }
            impacted = true;
            is_alive = false;
        }
    }
    std::string log() noexcept override { return {}; }
};

std::shared_ptr<Fighter> create_fighter(const std::string &uid, const std::string &model,
                                        const std::string &team, const std::array<double, 3> &position,
                                        const std::array<double, 3> &velocity, const GameConfig &config,
                                        bool player) {
    json::JSON spec = json::Object();
    spec["unit_spec"] = json::String(model);
    spec["color"] = json::String(team);
    spec["fdm_type"] = json::String(config.fdm);
    spec["position"] = json::Array(position[0], position[1], position[2]);
    spec["velocity"] = json::Array(velocity[0], velocity[1], velocity[2]);
    spec["pylon_mounts"] = json::Object();
    for (int i = 0; i < config.missiles; ++i)
        spec["pylon_mounts"]["M" + std::to_string(i)] = json::String("AIM-120C7");
    if (player)
        for (int i = 0; i < config.bombs; ++i)
            spec["pylon_mounts"]["B" + std::to_string(i)] = json::String("Mk-82");
    auto unit = std::dynamic_pointer_cast<Fighter>(UnitFactory::create_unit(uid, spec));
    if (!unit)
        throw std::runtime_error("Cannot create aircraft: " + model);
    SOPool::instance().add(unit);
    return unit;
}
} // namespace

bool GameTerrain::line_of_sight(const std::array<double, 3> &a, const std::array<double, 3> &b) const {
    if (std::min(a[2], b[2]) > maximum_height + 1)
        return true;
    double sample_spacing = spacing;
    for (const auto &tile : detail_tiles)
        sample_spacing = std::min(sample_spacing, tile.spacing);
    const int n = std::max(2, int(std::ceil(distance(a, b) / std::max(5.0, sample_spacing / 4))));
    for (int i = 1; i < n; ++i) {
        const double t = double(i) / n;
        if (a[2] + (b[2] - a[2]) * t < height(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            return false;
    }
    return true;
}
GameSession::GameSession(const std::string &log_path) : terrain_(std::make_shared<GameTerrain>()) {
    bool expected = false;
    if (!session_owned.compare_exchange_strong(expected, true))
        throw std::runtime_error("bvr_sim currently permits one game session per process");
    try {
        core_ = std::make_unique<SimCore>(config_.dt, log_path, "", false);
    } catch (...) {
        session_owned = false;
        throw;
    }
}
GameSession::~GameSession() { close(); }
void GameSession::close() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        return;
    if (core_)
        core_->stop();
    BaselinePool::instance().clear();
    SOPool::instance().clear();
    core_.reset();
    SL::shutdown();
    SimulatedObject::set_uuid_seed(std::nullopt);
    closed_ = true;
    session_owned = false;
}
void GameSession::reset(const GameConfig &config) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    if (config.dt <= 0 || config.dt > 0.1 || !std::isfinite(config.dt))
        throw std::invalid_argument("Game dt must be in (0,0.1]");
    if (config.player_model != "F22" && config.player_model != "F16")
        throw std::invalid_argument("Unsupported player aircraft");
    if (config.enemy_model != "F22" && config.enemy_model != "F16")
        throw std::invalid_argument("Unsupported opponent aircraft");
    if (config.mission != "air" && config.mission != "strike" && config.mission != "combined")
        throw std::invalid_argument("Unknown mission");
    if (config.fdm != "jsbsim" && config.fdm != "simple")
        throw std::invalid_argument("Unknown FDM");
    if (config.missiles < 0 || config.missiles > 8 || config.bombs < 0 || config.bombs > 4)
        throw std::invalid_argument("Invalid loadout");
    if (!std::isfinite(config.player_north) || !std::isfinite(config.player_west) ||
        !std::isfinite(config.ground_north) || !std::isfinite(config.ground_west) ||
        !std::isfinite(config.altitude) ||
        config.altitude <= terrain_->height(config.player_north, config.player_west) ||
        config.altitude > 20000 || !std::isfinite(config.speed) || config.speed < 80 || config.speed > 800 ||
        !std::isfinite(config.enemy_range) || config.enemy_range < 1000 || config.enemy_range > 500000)
        throw std::invalid_argument("Invalid sortie position or airspeed");
    config_ = config;
    cfg::dt = config.dt;
    cfg::sim_time = 0;
    BaselinePool::instance().clear();
    SOPool::instance().clear();
    pending_.clear();
    events_.clear();
    seen_deaths_.clear();
    seen_missiles_.clear();
    tick_ = applied_tick_ = bomb_serial_ = 0;
    paused_ = false;
    result_ = "running";
    selected_target_.clear();
    enemy_behavior_ = "intercept";
    enemy_locked_ = false;
    weapon_launch_times_.clear();
    pilot_controls_.reset();
    SimulatedObject::set_uuid_seed(config.seed);
    create_fighter("player", config.player_model, "Blue",
                   {config.player_north, config.player_west, config.altitude}, {config.speed, 0, 0}, config,
                   true);
    if (config.mission != "strike") {
        std::mt19937 random(config.seed);
        const double west = std::uniform_real_distribution<double>(-100.0, 100.0)(random);
        create_fighter("bandit", config.enemy_model, "Red",
                       {config.player_north + config.enemy_range, config.player_west + west, config.altitude},
                       {-config.speed, 0, 0}, config, false);
    }
    auto ground = std::make_shared<GroundStaticTarget>(
        "depot", TeamColor::Red,
        std::array<double, 3>{config.ground_north, config.ground_west,
                              terrain_->height(config.ground_north, config.ground_west)},
        config.dt);
    SOPool::instance().add(ground);
    record("sortie_started", "player", "", "", "Sortie started");
    publish_frame();
}
void GameSession::submit(const PilotCommand &command) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    if (!std::isfinite(command.heading) || !std::isfinite(command.pitch) ||
        !std::isfinite(command.throttle) || !std::isfinite(command.roll_input))
        throw std::invalid_argument("Pilot controls must be finite");
    if (command.uid != "player")
        throw std::invalid_argument("Pilot command must address the player");
    if (pending_.size() >= 256)
        throw std::runtime_error("Pilot command queue is full");
    pending_.push_back(command);
}
std::shared_ptr<Fighter> GameSession::fighter(const std::string &uid) const {
    return std::dynamic_pointer_cast<Fighter>(SOPool::instance().get(uid));
}
void GameSession::record(std::string kind, std::string actor, std::string target, std::string weapon,
                         std::string message, std::array<double, 3> position) {
    events_.push_back({tick_, std::move(kind), std::move(actor), std::move(target), std::move(weapon),
                       std::move(message), position});
    if (events_.size() > 512)
        events_.erase(events_.begin(), events_.begin() + 128);
}
void GameSession::drive_player(const PilotCommand &c) {
    auto player = fighter(c.uid);
    if (!player || !player->is_alive)
        return;
    player->set_pilot_input(
        std::clamp(norm_angle(c.heading - player->get_yaw()) / (85 * pi / 180), -1.0, 1.0),
        std::clamp(c.pitch / (pi / 4), -1.0, 1.0), std::clamp(c.throttle, 0.0, 1.0),
        c.manual_roll ? std::optional<double>(std::clamp(c.roll_input, -1.0, 1.0)) : std::nullopt);
}
void GameSession::apply_command(const PilotCommand &c) {
    auto player = fighter(c.uid);
    if (!player || !player->is_alive)
        return;
    pilot_controls_ = c;
    drive_player(c);
    applied_tick_ = tick_;
    if (c.lock) {
        const auto radar = std::dynamic_pointer_cast<Radar>(player->radar);
        const auto it = radar ? radar->get_data().find(c.target_uid)
                              : std::map<std::string, std::shared_ptr<DataObj>>::const_iterator{};
        if (radar && it != radar->get_data().end() && it->second->is_alive &&
            terrain_->line_of_sight(player->position, it->second->position)) {
            selected_target_ = c.target_uid;
            radar->radar_mode = "stt";
            record("target_locked", c.uid, c.target_uid, "", "Radar target locked");
        } else
            record("lock_rejected", c.uid, c.target_uid, "", "Target is not a radar contact");
    }
    if (c.fire) {
        const auto fire_radar = std::dynamic_pointer_cast<Radar>(player->radar);
        const std::string target = c.target_uid.empty() ? selected_target_ : c.target_uid;
        const auto target_obj = SOPool::instance().get(target);
        if (target.empty() || !target_obj || !target_obj->is_alive || target != selected_target_ ||
            !fire_radar || !fire_radar->get_data().count(target) || c.weapon != "AIM-120C7" ||
            !terrain_->line_of_sight(player->position, target_obj->position) ||
            !player->can_shoot_enm(target_obj) ||
            !launch_envelope(*player, target_obj->position, target_obj->velocity, target).in_range)
            record("fire_rejected", c.uid, target, c.weapon, "A valid lock and launch zone are required");
        else if (player->shoot(c.weapon, target)) {
            player->last_shoot_time = cfg::sim_time;
            record("missile_launched", c.uid, target, c.weapon, "Missile away", player->position);
        } else
            record("fire_rejected", c.uid, target, c.weapon, "No ammunition or weapon cooling down");
    }
    if (c.drop_bomb) {
        const auto mount = player->pylon_manager.release_weapon("Mk-82");
        if (mount.empty())
            record("release_rejected", c.uid, "", "Mk-82", "No bombs remaining");
        else {
            SOPool::instance().add(std::make_shared<GameBomb>("bomb_" + std::to_string(++bomb_serial_),
                                                              *player, terrain_, config_.dt));
            record("bomb_released", c.uid, "", "Mk-82", "Bomb away", player->position);
        }
    }
}
void GameSession::update_enemy() {
    auto enemy = fighter("bandit"), player = fighter("player");
    if (!enemy || !player || !enemy->is_alive || !player->is_alive)
        return;
    const auto &a = enemy->position;
    const auto &b = player->position;
    double desired = std::atan2(b[1] - a[1], b[0] - a[0]);
    double climb = std::clamp((b[2] - a[2]) / 5000.0, -.5, .5);
    std::string behavior = "intercept";
    auto radar = std::dynamic_pointer_cast<Radar>(enemy->radar);
    bool observed = radar && radar->get_data().count("player") && terrain_->line_of_sight(a, b);
    if (observed && !enemy_locked_ && config_.enemy_attacks) {
        enemy_locked_ = true;
        radar->radar_mode = "stt";
        record("enemy_lock", "bandit", "player", "", "Enemy radar tracking", a);
    }
    if (!observed) {
        enemy_locked_ = false;
        if (radar)
            radar->radar_mode = "scan";
    }
    if (config_.enemy_evasion) {
        if (enemy->mws && !enemy->mws->get_data().empty()) {
            behavior = "defend";
            desired += ((config_.seed & 1) ? 1 : -1) * pi * .58;
            climb = a[2] > terrain_->height(a[0], a[1]) + 1500 ? -.35 : 0;
        } else if (enemy->rws && enemy->rws->get_data().count("player") &&
                   std::dynamic_pointer_cast<Radar>(player->radar)->radar_mode == "stt" &&
                   distance(a, b) > 22000) {
            behavior = "crank";
            desired += ((config_.seed & 1) ? 1 : -1) * pi * .18;
            climb = -.08;
        }
    }
    if (behavior != enemy_behavior_) {
        enemy_behavior_ = behavior;
        record("enemy_maneuver", "bandit", "player", "", "Enemy maneuver: " + behavior, a);
    }
    enemy->set_pilot_input(std::clamp(norm_angle(desired - enemy->get_yaw()) / (85 * pi / 180), -0.8, 0.8),
                           climb, 0.85, std::nullopt);
    const auto zone = launch_envelope(*enemy, b, player->velocity, "player");
    // One missile in flight per AI salvo; another is allowed after a natural miss.
    bool airborne = false;
    for (auto &object : SOPool::instance().get_all())
        if (auto missile = std::dynamic_pointer_cast<Missile>(object))
            if (missile->is_alive && missile->parent && missile->parent->uid == "bandit")
                airborne = true;
    if (config_.enemy_attacks && observed && !airborne && zone.in_range &&
        (config_.enemy_evasion ? distance(a, b) < zone.rmax * .7
                               : (cfg::sim_time > 8 && distance(a, b) < 12000)) &&
        enemy->can_shoot_enm(player) && enemy->shoot("AIM-120C7", "player")) {
        enemy->last_shoot_time = cfg::sim_time;
        record("missile_launched", "bandit", "player", "AIM-120C7", "Enemy missile launched", a);
    }
}
void GameSession::step(int n) { advance(n, false); }
void GameSession::step_exact(int n) { advance(n, true); }
void GameSession::advance(int n, bool force) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    if (n < 0 || n > 100000)
        throw std::invalid_argument("Tick count out of range");
    for (int i = 0; i < n; ++i) {
        if ((paused_ && !force) || result_ != "running")
            break;
        ++tick_;
        for (const auto &command : pending_)
            apply_command(command);
        pending_.clear();
        if (pilot_controls_)
            drive_player(*pilot_controls_);
        update_enemy();
        core_->step(1);
        for (const auto &obj : SOPool::instance().get_all_ever_existed()) {
            if (auto bomb = std::dynamic_pointer_cast<GameBomb>(obj)) {
                if (bomb->impacted && seen_missiles_.insert(bomb->uid).second)
                    record("bomb_impact", bomb->owner, "", "Mk-82", "Bomb impacted terrain", bomb->position);
            } else if (auto missile = std::dynamic_pointer_cast<Missile>(obj)) {
                weapon_launch_times_.try_emplace(missile->uid, cfg::sim_time - config_.dt);
                if (missile->is_done && seen_missiles_.insert(missile->uid).second)
                    record(missile->is_success ? "missile_hit" : "missile_missed",
                           missile->parent ? missile->parent->uid : "",
                           missile->target ? missile->target->uid : "", missile->missile_model,
                           missile->get_log_done_reason(), missile->position);
            }
            if (!obj->is_alive && (obj->Type == SOT::Aircraft || obj->Type == SOT::GroundUnit) &&
                seen_deaths_.insert(obj->uid).second)
                record(obj->Type == SOT::Aircraft ? "aircraft_destroyed" : "ground_destroyed", "", obj->uid,
                       "", "Target destroyed", obj->position);
        }
        auto player = fighter("player");
        if (player && player->is_alive &&
            player->position[2] <= terrain_->height(player->position[0], player->position[1])) {
            player->hit();
            seen_deaths_.insert("player");
            record("aircraft_destroyed", "", "player", "", "Terrain collision", player->position);
        }
        if (seen_deaths_.count(selected_target_)) {
            selected_target_.clear();
            if (auto radar = std::dynamic_pointer_cast<Radar>(player->radar))
                radar->radar_mode = "scan";
        }
        if (!player || !player->is_alive)
            result_ = "failed";
        else if ((config_.mission == "air" && seen_deaths_.count("bandit")) ||
                 (config_.mission == "strike" && seen_deaths_.count("depot")) ||
                 (config_.mission == "combined" && seen_deaths_.count("bandit") &&
                  seen_deaths_.count("depot")))
            result_ = "succeeded";
        else if (cfg::sim_time >= 900)
            result_ = "failed";
        if (result_ != "running")
            record("mission_" + result_, "player", "", "",
                   result_ == "succeeded" ? "Mission accomplished" : "Mission failed");
    }
    publish_frame();
}
void GameSession::publish_frame() {
    GameFrame f;
    f.tick = tick_;
    f.applied_command_tick = applied_tick_;
    f.sim_time = cfg::sim_time;
    f.paused = paused_;
    f.result = result_;
    f.mission = config_.mission;
    f.selected_target = selected_target_;
    f.radar_mode = selected_target_.empty() ? "RWS" : "STT";
    f.enemy_behavior = enemy_behavior_;
    f.events = events_;
    f.air_kills = int(seen_deaths_.count("bandit"));
    f.ground_kills = int(seen_deaths_.count("depot"));
    for (const auto &obj : SOPool::instance().get_all()) {
        if (obj->Type == SOT::DataObj)
            continue;
        GameEntity e;
        e.uid = obj->uid;
        e.position = obj->position;
        e.velocity = obj->velocity;
        e.orientation = obj->get_rpy();
        e.alive = obj->is_alive;
        e.team = obj->color == TeamColor::Blue ? "blue" : "red";
        e.mach = obj->get_mach();
        if (auto ac = std::dynamic_pointer_cast<Aircraft>(obj)) {
            e.kind = "aircraft";
            e.model = ac->aircraft_model;
            e.health = ac->bloods;
            e.pylons = ac->pylon_manager.get_all_mounts();
            e.throttle = ac->uid == "player" && pilot_controls_ ? pilot_controls_->throttle : .85;
        } else if (auto missile = std::dynamic_pointer_cast<Missile>(obj)) {
            e.kind = "missile";
            e.model = missile->missile_model;
            e.weapon_age = std::max(0.0, cfg::sim_time - weapon_launch_times_[obj->uid]);
            e.motor_burning = e.weapon_age <= default_missile_parameter.t_thrust;
            if (missile->is_alive && missile->target) {
                MissileFlight flight;
                flight.uid = obj->uid;
                flight.owner = missile->parent ? missile->parent->uid : "";
                flight.target = missile->target->uid;
                flight.age = e.weapon_age;
                flight.range = distance(obj->position, missile->target->position);
                flight.seeker_active = missile->radar_on;
                flight.motor_burning = e.motor_burning;
                if (flight.range > 1) {
                    for (int i = 0; i < 3; ++i)
                        flight.closing_speed += (obj->velocity[i] - missile->target->velocity[i]) *
                                                (missile->target->position[i] - obj->position[i]) /
                                                flight.range;
                    if (flight.closing_speed > 1)
                        flight.eta = flight.range / flight.closing_speed;
                }
                f.missiles.push_back(std::move(flight));
            }
        } else if (obj->Type == SOT::Bomb) {
            e.kind = "bomb";
            e.model = "Mk-82";
        } else {
            e.kind = "ground";
            e.model = "depot";
        }
        f.entities.push_back(std::move(e));
    }
    if (auto player = fighter("player")) {
        if (auto radar = std::dynamic_pointer_cast<Radar>(player->radar))
            f.radar_range = radar->radar_range;
        f.missiles_left = player->pylon_manager.num_left_weapons("AIM-120");
        f.bombs_left = player->pylon_manager.num_left_weapons("Mk-82");
        if (f.bombs_left > 0 && player->is_alive) {
            auto p = player->position, v = player->velocity;
            p[2] -= 2;
            for (int i = 0; i < 6000; ++i) {
                ballistic_step(p, v, config_.dt);
                if (p[2] <= terrain_->height(p[0], p[1])) {
                    p[2] = terrain_->height(p[0], p[1]);
                    f.bomb_impact = p;
                    break;
                }
            }
        }
        if (player->radar)
            for (const auto &[uid, observation] : player->radar->get_data()) {
                if (observation && observation->is_alive && !seen_deaths_.count(uid) &&
                    terrain_->line_of_sight(player->position, observation->position)) {
                    f.contacts.push_back({uid, "radar", observation->position, observation->velocity,
                                          uid == selected_target_});
                    if (uid == selected_target_)
                        f.envelope =
                            launch_envelope(*player, observation->position, observation->velocity, uid);
                }
            }
        f.radar_warning = player->rws && !player->rws->get_data().empty();
        f.missile_warning = player->mws && !player->mws->get_data().empty();
        if (auto enemy = fighter("bandit")) {
            bool illuminated = enemy->is_alive && enemy->radar && enemy->radar->get_data().count("player") &&
                               terrain_->line_of_sight(player->position, enemy->position);
            f.rwr_mode = f.missile_warning ? "missile"
                         : illuminated     ? (enemy_locked_ ? "lock" : "search")
                                           : "quiet";
        }
    }
    frame_ = std::move(f);
}
void GameSession::set_paused(bool paused) {
    std::lock_guard<std::mutex> lock(mutex_);
    paused_ = paused;
    publish_frame();
}
GameFrame GameSession::frame() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return frame_;
}
GameTerrain GameSession::terrain() const {
    std::lock_guard<std::mutex> lock(mutex_);
    return *terrain_;
}
void GameSession::set_terrain(const GameTerrain &terrain) {
    if (!std::isfinite(terrain.origin_north) || !std::isfinite(terrain.origin_west) ||
        !std::isfinite(terrain.spacing) || terrain.columns < 2 || terrain.rows < 2 || terrain.columns > 512 ||
        terrain.rows > 512 || std::any_of(terrain.heights.begin(), terrain.heights.end(), [](double x) {
            return !std::isfinite(x);
        }))
        throw std::invalid_argument("Invalid terrain data");
    sample_height_field(terrain.origin_north, terrain.origin_west, terrain.spacing, terrain.columns,
                        terrain.rows, terrain.heights, terrain.origin_north, terrain.origin_west);
    double highest = *std::max_element(terrain.heights.begin(), terrain.heights.end());
    for (const auto &tile : terrain.detail_tiles) {
        if (!std::isfinite(tile.spacing) || tile.spacing <= 0 || tile.columns < 2 || tile.rows < 2 ||
            tile.columns > 512 || tile.rows > 512 || !std::isfinite(tile.origin_north) ||
            !std::isfinite(tile.origin_west) ||
            std::any_of(tile.heights.begin(), tile.heights.end(), [](double h) { return !std::isfinite(h); }))
            throw std::invalid_argument("Invalid detail height field");
        tile.height(tile.origin_north, tile.origin_west);
        highest = std::max(highest, *std::max_element(tile.heights.begin(), tile.heights.end()));
    }
    std::lock_guard<std::mutex> lock(mutex_);
    if (tick_ != 0)
        throw std::logic_error("Change terrain before sortie reset");
    *terrain_ = terrain;
    terrain_->maximum_height = highest;
}
} // namespace bvr_sim
