#include "game_session.hxx"
#include "simulator/bomb/mk82.hxx"
#include "simulator/aircraft/catalog.hxx"
#include "simulator/ground/vehicle.hxx"
#include "simulator/ground/ground_factory.hxx"
#include "simulator/ground/slamraam.hxx"
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
std::shared_ptr<Fighter> create_fighter(const std::string &uid, const std::string &model,
                                        const std::string &team, const std::array<double, 3> &position,
                                        const std::array<double, 3> &velocity, const GameConfig &config,
                                        bool player) {
    json::JSON spec = json::Object();
    spec["unit_spec"] = json::String(model);
    spec["radar_type"] = json::String(config.library_aircraft?"none":"radar");
    spec["color"] = json::String(team);
    spec["fdm_type"] = json::String(
        config.fdm == "auto" ? aircraft_definition(model, config.library_aircraft).fdm_type : config.fdm);
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

GameSession::GameSession(const std::string &log_path) : session_log_path_(log_path),terrain_(std::make_shared<GameTerrain>()) {
    bool expected = false;
    if (!session_owned.compare_exchange_strong(expected, true))
        throw std::runtime_error("bvr_sim currently permits one game session per process");
    try {
        core_ = std::make_unique<SimCore>(config_.dt, log_path, "", false);
        core_->set_environment(terrain_);
    } catch (...) {
        session_owned = false;
        throw;
    }
}
GameSession::~GameSession() { try{close();}catch(...){} }
void GameSession::begin_recording(const std::string& log,const std::string& acmi,const std::string& reference){
    std::lock_guard<std::mutex> lock(mutex_);
    if(closed_)throw std::runtime_error("Session is closed");
    try{core_->begin_recording(log,acmi,reference);recording_=true;}
    catch(...){
        try{core_->end_recording();SL::init_instance(session_log_path_,true);}catch(...){}
        recording_=false;throw;
    }
}
void GameSession::end_recording(){
    std::lock_guard<std::mutex> lock(mutex_);
    if(!recording_||closed_)return;
    std::exception_ptr error;
    try{core_->end_recording();}catch(...){error=std::current_exception();}
    recording_=false;SL::init_instance(session_log_path_,true);
    if(error)std::rethrow_exception(error);
}
void GameSession::flush_recording(){
    std::lock_guard<std::mutex> lock(mutex_);
    if(closed_)throw std::runtime_error("Session is closed");
    core_->flush_recording();
}
void GameSession::close() {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        return;
    std::exception_ptr error;
    if(recording_){try{core_->end_recording();}catch(...){error=std::current_exception();}recording_=false;}
    if (core_)
        core_->stop();
    BaselinePool::instance().clear();
    SOPool::instance().clear();
    core_.reset();
    SL::shutdown();
    SimulatedObject::set_uuid_seed(std::nullopt);
    DataObj::set_noise_seed(std::nullopt);
    closed_ = true;
    session_owned = false;
    if(error)std::rethrow_exception(error);
}
void GameSession::reset(const GameConfig &config) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    if(recording_){core_->end_recording();recording_=false;SL::init_instance(session_log_path_,true);}
    if (config.dt <= 0 || config.dt > 0.1 || !std::isfinite(config.dt))
        throw std::invalid_argument("Game dt must be in (0,0.1]");
    const auto definition = aircraft_definition(config.player_model, config.library_aircraft);
    if (!config.library_aircraft)
        aircraft_definition(config.enemy_model);
    if (config.library_aircraft &&
        (config.mission != "training" || config.missiles || config.bombs || config.enemy_attacks))
        throw std::invalid_argument(
            "Imported library access is unarmed training-only; disable enemy weapons");
    if (config.mission != "air" && config.mission != "strike" && config.mission != "combined" &&
        config.mission != "convoy" && config.mission != "training" && config.mission != "intercept_patrol")
        throw std::invalid_argument("Unknown mission");
    if(config.mission=="intercept_patrol" && (config.intercept_waves<1||config.intercept_waves>5||
       !std::isfinite(config.intercept_interval)||config.intercept_interval<30||
       !std::isfinite(config.intercept_timeout)||config.intercept_timeout<120||config.intercept_timeout>900))
        throw std::invalid_argument("Invalid intercept scenario");
    if (config.fdm != "jsbsim" && config.fdm != "simple" && config.fdm != "yasim" && config.fdm != "auto")
        throw std::invalid_argument("Unknown FDM");
    if (config.library_aircraft && config.fdm != "auto" && config.fdm != definition.fdm_type)
        throw std::invalid_argument("Requested backend differs from the imported source");
    if (config.missiles < 0 || config.missiles > definition.max_missiles || config.bombs < 0 ||
        config.bombs > definition.max_bombs)
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
    ground_objectives_.clear();
    pilot_controls_.reset();
    intercept_spawned_=0;enemy_pilots_.clear();enemy_phases_.clear();intercept_weapon_kills_.clear();
    SimulatedObject::set_uuid_seed(config.seed);
    DataObj::set_noise_seed(config.seed);
    create_fighter("player", config.player_model, "Blue",
                   {config.player_north, config.player_west, config.altitude}, {config.speed, 0, 0}, config,
                   true);
    if (config.mission == "air" || config.mission == "combined") {
        std::mt19937 random(config.seed);
        const double west = std::uniform_real_distribution<double>(-100.0, 100.0)(random);
        create_fighter("bandit", config.enemy_model, "Red",
                       {config.player_north + config.enemy_range, config.player_west + west, config.altitude},
                       {-config.speed, 0, 0}, config, false);
    }
    if(config.mission=="intercept_patrol")spawn_intercept_wave();
    auto ground = std::make_shared<GroundStaticTarget>(
        "depot", TeamColor::Red,
        std::array<double, 3>{config.ground_north, config.ground_west,
                              terrain_->height(config.ground_north, config.ground_west)},
        config.dt);
    SOPool::instance().add(ground);
    for (const auto &spec : config.ground_units) {
        create_ground_unit(spec, terrain_, config.dt);
        if (spec.mission_target && spec.team == "red")
            ground_objectives_.insert(spec.uid);
    }
    if (config.mission == "convoy" && ground_objectives_.empty())
        throw std::invalid_argument("Convoy mission requires declared ground objectives");
    record("sortie_started", "player", "", "", "Sortie started");
    publish_frame();
}
void GameSession::submit(const PilotCommand &command) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    if (!std::isfinite(command.heading) || !std::isfinite(command.pitch) ||
        !std::isfinite(command.throttle) || !std::isfinite(command.roll_input) ||
        !std::isfinite(command.pitch_input) || (command.roll_rate && !std::isfinite(*command.roll_rate)))
        throw std::invalid_argument("Pilot controls must be finite");
    if (command.uid != "player")
        throw std::invalid_argument("Pilot command must address the player");
    if (command.roll_rate && (config_.fdm == "auto" ?
        aircraft_definition(config_.player_model, config_.library_aircraft).fdm_type : config_.fdm) != "yasim")
        throw std::invalid_argument("Roll-rate assist requires the YASim backend");
    if (pending_.size() >= 256)
        throw std::runtime_error("Pilot command queue is full");
    pending_.push_back(command);
}
std::shared_ptr<Fighter> GameSession::fighter(const std::string &uid) const {
    return std::dynamic_pointer_cast<Fighter>(SOPool::instance().get(uid));
}
void GameSession::configure_player_flight(const PlayerFlightProfile& profile){
    std::lock_guard<std::mutex> lock(mutex_);
    if(closed_)throw std::runtime_error("Session is closed");
    profile.validate();auto p=fighter("player");if(!p)throw std::logic_error("Reset before configuring player flight");
    if(p->player_flight_state().active&&!paused_)throw std::logic_error("Pause before reloading an active player flight profile");
    p->configure_player_flight(profile);
}
PlayerFlightProfile GameSession::player_flight_profile() const {
    std::lock_guard<std::mutex> lock(mutex_);auto p=fighter("player");
    if(closed_||!p)throw std::logic_error("No active player");return p->player_flight_profile();
}
PlayerFlightState GameSession::player_flight_state() const {
    std::lock_guard<std::mutex> lock(mutex_);auto p=fighter("player");
    if(closed_||!p)throw std::logic_error("No active player");return p->player_flight_state();
}
void GameSession::submit_player(const PlayerFlightIntent& intent){
    std::lock_guard<std::mutex> lock(mutex_);
    if(closed_)throw std::runtime_error("Session is closed");
    validate_player_intent(intent);auto p=fighter("player");
    if(!p)throw std::logic_error("No active player");p->player_flight_profile();
    if(pending_.size()>=256)throw std::runtime_error("Pilot command queue is full");
    pending_.push_back(intent);
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
        c.manual_roll ? std::optional<double>(std::clamp(c.roll_input, -1.0, 1.0)) : std::nullopt,
        c.manual_pitch ? std::optional<double>(-std::clamp(c.pitch_input, -1.0, 1.0)) : std::nullopt,
        c.roll_rate);
}
void GameSession::apply_command(const PilotCommand &c,bool drive) {
    auto player = fighter(c.uid);
    if (!player || !player->is_alive)
        return;
    if(drive){pilot_controls_ = c;drive_player(c);}
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
            SOPool::instance().add(std::make_shared<Mk82Bomb>("bomb_" + std::to_string(++bomb_serial_),
                                                              *player, terrain_, config_.dt));
            record("bomb_released", c.uid, "", "Mk-82", "Bomb away", player->position);
        }
    }
}
void GameSession::spawn_intercept_wave(){
    const int wave=intercept_spawned_++;
    const std::string uid="raider_"+std::to_string(wave+1);
    std::mt19937 random(config_.seed+unsigned(wave)*7919);
    double west=std::uniform_real_distribution<double>(-6000,6000)(random);
    create_fighter(uid,config_.enemy_model,"Red",
        {config_.player_north+config_.enemy_range+wave*20000,config_.player_west+west,config_.altitude},
        {-config_.speed,0,0},config_,false);
    enemy_pilots_.emplace(uid,AirTacticalPilot(config_.seed+wave));
    record("hostile_wave","mission",uid,"","Inbound group "+std::to_string(wave+1)+" / "+std::to_string(config_.intercept_waves)+"; search northern corridor");
}
void GameSession::update_intercept_enemies(){
    if(intercept_spawned_<config_.intercept_waves && cfg::sim_time>=intercept_spawned_*config_.intercept_interval)
        spawn_intercept_wave();
    for(auto& [uid,pilot]:enemy_pilots_){
        auto own=fighter(uid);if(!own||!own->is_alive)continue;
        TacticalObservation o;o.position=own->position;o.velocity=own->velocity;o.yaw=own->get_yaw();
        o.altitude_agl=own->position[2]-terrain_->height(own->position[0],own->position[1]);
        o.missiles=own->pylon_manager.num_left_weapons("AIM-120");
        auto radar=std::dynamic_pointer_cast<Radar>(own->radar);
        if(radar)for(const auto& [id,t]:radar->get_data())
            if(t->is_alive && t->color!=own->color && terrain_->line_of_sight(own->position,t->position))
                o.tracks.push_back({id,t->position,t->velocity});
        o.radar_warning=own->rws&&!own->rws->get_data().empty();
        o.missile_warning=own->mws&&!own->mws->get_data().empty();
        if(o.missile_warning){auto t=own->mws->get_data().begin()->second;
            o.threat_bearing=norm_angle(std::atan2(t->position[1]-o.position[1],t->position[0]-o.position[0])-o.yaw);}
        o.weapon_supporting=std::any_of(own->launched_missiles.begin(),own->launched_missiles.end(),[](const auto& m){return m&&m->is_alive;});
        auto intent=pilot.decide(o,cfg::sim_time,pi,config_.altitude);
        own->set_pilot_input(std::clamp(norm_angle(intent.heading-o.yaw)/(85*pi/180),-.8,.8),intent.pitch/(pi/4),intent.throttle);
        if(radar)radar->radar_mode=intent.lock?"stt":"scan";
        if(intent.phase!=enemy_phases_[uid]){
            enemy_phases_[uid]=intent.phase;enemy_behavior_=intent.phase;
            record("enemy_maneuver",uid,"player","","Observed-state AI: "+intent.phase,own->position);
        }
        if(config_.enemy_attacks&&intent.fire&&own->shoot("AIM-120C7",intent.target_uid)){
            own->last_shoot_time=cfg::sim_time;pilot.launched(cfg::sim_time);
            record("missile_launched",uid,intent.target_uid,"AIM-120C7","Hostile missile launched",own->position);
        }
    }
}
void GameSession::update_enemy() {
    if(config_.mission=="intercept_patrol"){update_intercept_enemies();return;}
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
        for (const auto &command : pending_){
            if(auto legacy=std::get_if<PilotCommand>(&command))apply_command(*legacy);
            else {
                const auto& intent=std::get<PlayerFlightIntent>(command);
                if(auto p=fighter("player");p&&p->is_alive){
                    pilot_controls_.reset();p->set_player_flight(intent);
                    PilotCommand actions;actions.fire=intent.fire;actions.drop_bomb=intent.drop_bomb;
                    actions.lock=intent.lock;actions.target_uid=intent.target_uid;actions.weapon=intent.weapon;
                    apply_command(actions,false);
                }
            }
        }
        pending_.clear();
        if (pilot_controls_)
            drive_player(*pilot_controls_);
        update_enemy();
        core_->step(1);
        for (const auto &obj : SOPool::instance().get_all_ever_existed()) {
            if (auto bomb = std::dynamic_pointer_cast<Mk82Bomb>(obj)) {
                if (bomb->impacted && seen_missiles_.insert(bomb->uid).second)
                    record("bomb_impact", bomb->owner, "", "Mk-82", "Bomb impacted terrain", bomb->position);
            } else if (auto missile = std::dynamic_pointer_cast<Missile>(obj)) {
                auto [launch, inserted] =
                    weapon_launch_times_.try_emplace(missile->uid, cfg::sim_time - config_.dt);
                if (inserted && missile->parent && missile->parent->Type == SOT::AA)
                    record("missile_launched", missile->parent->uid,
                           missile->target ? missile->target->uid : "", missile->missile_model,
                           "Ground launcher fired after sensor detection", missile->position);
                if (missile->is_done && seen_missiles_.insert(missile->uid).second)
                {
                    if(config_.mission=="intercept_patrol"&&missile->is_success&&missile->parent&&
                       missile->parent->uid=="player"&&missile->target&&enemy_pilots_.count(missile->target->uid))
                        intercept_weapon_kills_.insert(missile->target->uid);
                    record(missile->is_success ? "missile_hit" : "missile_missed",
                           missile->parent ? missile->parent->uid : "",
                           missile->target ? missile->target->uid : "", missile->missile_model,
                           missile->get_log_done_reason(), missile->position);
                }
            }
            if (!obj->is_alive &&
                (obj->Type == SOT::Aircraft || obj->Type == SOT::GroundUnit || obj->Type == SOT::AA) &&
                seen_deaths_.insert(obj->uid).second)
                record(
                    obj->Type == SOT::Aircraft ? "aircraft_destroyed" : "ground_destroyed", "", obj->uid, "",
                    obj->uid == "player" &&
                            obj->position[2] <= terrain_->collision_height(obj->position[0], obj->position[1])
                        ? "Terrain collision"
                        : "Target destroyed",
                    obj->position);
        }
        auto player = fighter("player");
        if (seen_deaths_.count(selected_target_)) {
            selected_target_.clear();
            if (auto radar = std::dynamic_pointer_cast<Radar>(player->radar))
                radar->radar_mode = "scan";
        }
        if (!player || !player->is_alive)
            result_ = "failed";
        else if ((config_.mission=="intercept_patrol" && int(intercept_weapon_kills_.size())==config_.intercept_waves) ||
                 (config_.mission == "air" && seen_deaths_.count("bandit")) ||
                 (config_.mission == "strike" && seen_deaths_.count("depot")) ||
                 (config_.mission == "combined" && seen_deaths_.count("bandit") &&
                  seen_deaths_.count("depot")) ||
                 (config_.mission == "convoy" && !ground_objectives_.empty() &&
                  std::all_of(ground_objectives_.begin(), ground_objectives_.end(),
                              [&](const auto &uid) { return seen_deaths_.count(uid) > 0; })))
            result_ = "succeeded";
        else if (cfg::sim_time >= (config_.mission=="intercept_patrol"?config_.intercept_timeout:900))
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
    if(config_.mission=="intercept_patrol"){
        f.air_kills=int(intercept_weapon_kills_.size());
        f.mission_wave=intercept_spawned_;f.mission_total=f.mission_kills_required=config_.intercept_waves;
        f.next_wave_time=intercept_spawned_<config_.intercept_waves?intercept_spawned_*config_.intercept_interval:-1;
    }
    for (const auto &object : SOPool::instance().get_all_ever_existed()) {
        if (object->color == TeamColor::Red && !object->is_alive &&
            (object->Type == SOT::GroundUnit || object->Type == SOT::AA))
            ++f.ground_kills;
        if (auto ground = std::dynamic_pointer_cast<GroundUnit>(object)) {
            GroundState state;
            state.uid = ground->uid;
            state.model = ground->model_id();
            state.alive = ground->is_alive;
            state.position = ground->position;
            state.velocity = ground->velocity;
            state.orientation = ground->get_rpy();
            state.health = ground->health();
            state.speed = ground->get_speed();
            state.kind = "static";
            state.motion = "static";
            if (auto vehicle = std::dynamic_pointer_cast<GroundVehicle>(ground)) {
                state.kind = "vehicle";
                state.motion = state.alive ? vehicle->motion : "destroyed";
                state.blocked_reason = vehicle->blocked_reason;
                state.contact_surface = vehicle->contact_surface;
                state.route = vehicle->route;
                state.waypoint = vehicle->waypoint;
                state.parking = vehicle->parking;
            } else if (auto sam = std::dynamic_pointer_cast<SLAMRAAM>(ground)) {
                state.kind = "sam";
                state.missiles_left = sam->get_num_left_missiles();
                for (const auto &[uid, _] : sam->search_radar.contacts)
                    state.sensor_contacts.push_back(uid);
            }
            f.ground_units.push_back(std::move(state));
        }
    }
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
            if (auto controlled = std::dynamic_pointer_cast<Fighter>(ac)) {
                e.animation_properties = controlled->visual_properties();
                if(auto player_throttle=controlled->player_throttle())e.throttle=*player_throttle;
            }
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
        } else if (auto vehicle = std::dynamic_pointer_cast<GroundVehicle>(obj)) {
            e.kind = "vehicle";
            e.model = vehicle->model_id();
            e.health = vehicle->health();
        } else if (auto sam = std::dynamic_pointer_cast<SLAMRAAM>(obj)) {
            e.kind = "sam";
            e.model = "SLAMRAAM";
            e.health = sam->health();
        } else {
            e.kind = "ground";
            e.model = "depot";
        }
        f.entities.push_back(std::move(e));
    }
    if (auto player = fighter("player")) {
        if (auto radar = std::dynamic_pointer_cast<Radar>(player->radar))
            f.radar_range = radar->radar_range;
        else { f.radar_mode="OFF";f.radar_range=0; }
        f.missiles_left = player->pylon_manager.num_left_weapons("AIM-120");
        f.bombs_left = player->pylon_manager.num_left_weapons("Mk-82");
        if (f.bombs_left > 0 && player->is_alive) {
            f.bomb_impact =
                predict_ballistic_impact(player->position, player->velocity, *terrain_, config_.dt,6000,player->player_flight_active());
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
        const auto append_warning = [&](const auto &sensor, bool missile, bool localized) {
            if (!sensor)
                return;
            for (const auto &[uid, observation] : sensor->get_data()) {
                if (!observation || !observation->is_alive)
                    continue;
                const double dn = observation->position[0] - player->position[0];
                const double dw = observation->position[1] - player->position[1];
                const double bearing =
                    std::remainder(std::atan2(dw, dn) - player->get_yaw(), 2.0 * std::acos(-1.0));
                f.warnings.push_back({uid, bearing, std::hypot(dn, dw), localized, missile});
            }
        };
        append_warning(player->rws, false, false);
        append_warning(player->mws, true, true);
        f.radar_warning = player->rws && !player->rws->get_data().empty();
        f.missile_warning = player->mws && !player->mws->get_data().empty();
        f.rwr_mode = f.missile_warning ? "missile" : (f.radar_warning ? "search" : "quiet");
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
            // Bounded1024x1024 permits a continuous20km/25m regional tile
            // (~5MiB of doubles); its sampling/physics are otherwise unchanged.
            tile.columns > 1024 || tile.rows > 1024 || !std::isfinite(tile.origin_north) ||
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
    terrain_->prepare_surfaces();
}
void GameSession::spawn_ground(const GroundUnitSpec &spec) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    create_ground_unit(spec, terrain_, config_.dt);
    if (spec.mission_target && spec.team == "red")
        ground_objectives_.insert(spec.uid);
    record("ground_spawned", "", spec.uid, "", "Core ground object created", spec.position);
    publish_frame();
}
void GameSession::set_ground_route(const std::string &uid, const VehicleRoute &route) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    auto vehicle = std::dynamic_pointer_cast<GroundVehicle>(SOPool::instance().get(uid));
    if (!vehicle || !vehicle->is_alive)
        throw std::invalid_argument("Unknown live ground vehicle: " + uid);
    vehicle->set_route(route);
    record("ground_route_set", "", uid, "", "Route submitted to core");
    publish_frame();
}
void GameSession::park_ground(const std::string &uid, bool parked) {
    std::lock_guard<std::mutex> lock(mutex_);
    if (closed_)
        throw std::runtime_error("Session is closed");
    auto vehicle = std::dynamic_pointer_cast<GroundVehicle>(SOPool::instance().get(uid));
    if (!vehicle || !vehicle->is_alive)
        throw std::invalid_argument("Unknown live ground vehicle: " + uid);
    vehicle->set_parking(parked);
    record(parked ? "ground_stop_requested" : "ground_resume_requested", "", uid, "", "Core parking command");
    publish_frame();
}
} // namespace bvr_sim
