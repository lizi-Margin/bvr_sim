#pragma once

// In-process game API. Value types only: no renderer, window or telemetry types.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <map>
#include <limits>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#include <variant>
#include "simulator/environment.hxx"
#include "simulator/weapon_catalog.hxx"
#include "simulator/ground/ground_types.hxx"
#include "simulator/aircraft/tactical_pilot.hxx"
#include "simulator/aircraft/player_flight_types.hxx"

namespace bvr_sim {
class SimCore;
class Fighter;

struct GameConfig {
    std::string player_model = "F22";
    std::string enemy_model = "F16";
    std::string mission = "air"; // also dogfight_1v1: fixed4km head-on, one opponent
    std::string fdm = "jsbsim";
    bool library_aircraft = false; // explicit unarmed training access to separately imported aircraft
    std::uint32_t seed = 7;
    double dt = 0.02;
    double enemy_range = 12000.0;
    double altitude = 3000.0;
    double player_north = 0.0, player_west = 0.0;
    double ground_north = 6000.0, ground_west = 0.0;
    double speed = 250.0;
    bool enemy_attacks = true;
    bool enemy_evasion = false; // legacy callers keep their existing intercept behavior
    int missiles = 4;
    int bombs = 2;
    bool use_station_loadout = false; // legacy count-only callers remain supported
    LoadoutSpec loadout;
    std::vector<GroundUnitSpec> ground_units;
    int intercept_waves=3;
    double intercept_interval=120.,intercept_timeout=600.;
};

struct PilotCommand {
    std::string uid = "player";
    double heading = 0.0; // world NWU radians
    double pitch = 0.0;   // desired climb angle, radians
    double throttle = 0.8;
    double roll_input = 0.0;
    bool manual_roll = false;
    std::optional<double> roll_rate; // YASim interactive assist, rad/s; manual_roll takes priority
    double pitch_input = 0.0; // normalized stick: positive pull/up, negative push/down
    bool manual_pitch = false; // override climb-angle assist with elevator input
    bool fire = false;
    bool drop_bomb = false;
    bool lock = false;
    std::string target_uid;
    std::string weapon = "AIM-120C7";
    std::string station;
};

struct GameContact {
    std::string uid;
    std::string sensor;
    std::array<double, 3> position{};
    std::array<double, 3> velocity{};
    bool locked = false;
};

struct GameWarning {
    std::string uid;
    double bearing = 0.0; // relative to ownship heading; RWS supplies direction only
    double range = 0.0;
    bool localized = false;
    bool missile = false;
};

struct GameEntity {
    std::string uid, model, kind, team;
    bool alive = true;
    std::array<double, 3> position{}, velocity{}, orientation{};
    double health = 1.0;
    double mach = 0.0;
    double throttle = 0.0, weapon_age = 0.0;
    bool motor_burning = false;
    std::map<std::string, std::string> pylons;
    std::map<std::string, double> animation_properties;
};

struct GroundState {
    std::string uid, model, kind, motion, blocked_reason, contact_surface;
    std::array<double, 3> position{}, velocity{}, orientation{};
    VehicleRoute route;
    double health = 0, speed = 0;
    size_t waypoint = 0;
    bool alive = true, parking = false;
    int missiles_left = 0;
    std::vector<std::string> sensor_contacts;
};

struct LaunchEnvelope {
    std::string target_uid;
    double range = 0, closing_speed = 0, bearing = 0, rmax = 0, rtr = 0, eta = 0;
    bool in_range = false;
};
struct MissileFlight {
    std::string uid, owner, target, model;
    double age = 0, range = 0, closing_speed = 0, eta = -1;
    bool seeker_active = false, motor_burning = false;
};

struct CombatEvent {
    std::uint64_t tick = 0;
    std::string kind, actor, target, weapon, message;
    std::array<double, 3> position{};
};

struct GameFrame {
    std::uint64_t tick = 0;
    std::uint64_t applied_command_tick = 0;
    double sim_time = 0.0;
    bool paused = false;
    std::string mission, result = "running", selected_target;
    std::vector<GameEntity> entities;  // render/debug world; never use as HUD contacts
    std::vector<GameContact> contacts; // player sensor observations only
    std::vector<GameWarning> warnings; // RWS bearings and localized MWS warnings
    std::vector<GroundState> ground_units;
    std::vector<CombatEvent> events;
    int missiles_left = 0, bombs_left = 0;
    std::string selected_weapon, launch_reason;
    bool launch_ready = false;
    std::map<std::string,int> weapon_counts;
    int air_kills = 0, ground_kills = 0;
    bool radar_warning = false, missile_warning = false;
    std::string radar_mode = "RWS", rwr_mode = "quiet", enemy_behavior = "intercept";
    double radar_range = 80000;
    LaunchEnvelope envelope;
    std::vector<MissileFlight> missiles;
    std::optional<std::array<double, 3>> bomb_impact;
    int mission_wave=0,mission_total=0,mission_kills_required=0;
    double next_wave_time=-1;
};

// Backward-compatible API name; physical environment is owned by simulator/core.
using GameTerrain = Terrain;

class GameSession {
  public:
    explicit GameSession(const std::string &log_path = "bvr_game.log");
    ~GameSession();
    GameSession(const GameSession &) = delete;
    GameSession &operator=(const GameSession &) = delete;
    void reset(const GameConfig &config);
    void submit(const PilotCommand &command);
    void submit_player(const PlayerFlightIntent &intent);
    void configure_player_flight(const PlayerFlightProfile &profile);
    PlayerFlightProfile player_flight_profile() const;
    PlayerFlightState player_flight_state() const;
    void step(int ticks = 1);       // honors pause
    void step_exact(int ticks = 1); // deterministic debugger step, even when paused
    void set_paused(bool paused);
    GameFrame frame() const;
    GameTerrain terrain() const;
    void set_terrain(const GameTerrain &terrain);
    void spawn_ground(const GroundUnitSpec &spec);
    void set_ground_route(const std::string &uid, const VehicleRoute &route);
    void park_ground(const std::string &uid, bool parked);
    void begin_recording(const std::string &log_path,const std::string &acmi_path,const std::string &reference_time);
    void end_recording();
    void flush_recording();
    void close();

  private:
    void advance(int ticks, bool force);
    void publish_frame();
    void apply_command(const PilotCommand &command,bool drive=true);
    void drive_player(const PilotCommand &command);
    void update_enemy();
    void update_dogfight_enemy();
    void spawn_intercept_wave();
    void update_intercept_enemies();
    void record(std::string kind, std::string actor, std::string target, std::string weapon,
                std::string message, std::array<double, 3> position = {});
    std::shared_ptr<Fighter> fighter(const std::string &uid) const;
    mutable std::mutex mutex_;
    std::unique_ptr<SimCore> core_;
    std::string session_log_path_;
    bool recording_=false;
    std::shared_ptr<GameTerrain> terrain_;
    GameConfig config_;
    GameFrame frame_;
    std::vector<std::variant<PilotCommand,PlayerFlightIntent>> pending_;
    std::optional<PilotCommand> pilot_controls_;
    std::vector<CombatEvent> events_;
    std::set<std::string> seen_deaths_, seen_missiles_;
    bool paused_ = false, closed_ = false;
    std::uint64_t tick_ = 0, applied_tick_ = 0;
    unsigned bomb_serial_ = 0;
    std::string selected_target_, result_ = "running";
    std::string selected_weapon_ = "AIM-120C7";
    std::string enemy_behavior_ = "intercept";
    bool enemy_locked_ = false;
    std::map<std::string, double> weapon_launch_times_;
    std::set<std::string> ground_objectives_;
    int intercept_spawned_=0;
    std::map<std::string,AirTacticalPilot> enemy_pilots_;
    std::map<std::string,std::string> enemy_phases_;
    std::set<std::string> intercept_weapon_kills_;
};
} // namespace bvr_sim
