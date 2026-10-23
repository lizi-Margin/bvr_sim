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

namespace bvr_sim {
class SimCore;
class Fighter;

struct GameConfig {
    std::string player_model = "F22";
    std::string enemy_model = "F16";
    std::string mission = "air"; // air | strike | combined
    std::string fdm = "jsbsim";
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
};

struct PilotCommand {
    std::string uid = "player";
    double heading = 0.0; // world NWU radians
    double pitch = 0.0;   // desired climb angle, radians
    double throttle = 0.8;
    double roll_input = 0.0;
    bool manual_roll = false;
    bool fire = false;
    bool drop_bomb = false;
    bool lock = false;
    std::string target_uid;
    std::string weapon = "AIM-120C7";
};

struct GameContact {
    std::string uid;
    std::string sensor;
    std::array<double, 3> position{};
    std::array<double, 3> velocity{};
    bool locked = false;
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
};

struct LaunchEnvelope {
    std::string target_uid;
    double range = 0, closing_speed = 0, bearing = 0, rmax = 0, rtr = 0, eta = 0;
    bool in_range = false;
};
struct MissileFlight {
    std::string uid, owner, target;
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
    std::vector<CombatEvent> events;
    int missiles_left = 0, bombs_left = 0;
    int air_kills = 0, ground_kills = 0;
    bool radar_warning = false, missile_warning = false;
    std::string radar_mode = "RWS", rwr_mode = "quiet", enemy_behavior = "intercept";
    double radar_range = 80000;
    LaunchEnvelope envelope;
    std::vector<MissileFlight> missiles;
    std::optional<std::array<double, 3>> bomb_impact;
};

// All height fields use indexed triangle planes, including fine/coarse tile seams.
inline double sample_height_field(double origin_north, double origin_west, double spacing, int columns,
                                  int rows, const std::vector<double> &heights, double north, double west) {
    if (columns < 2 || rows < 2 || spacing <= 0 || heights.size() != size_t(columns * rows))
        throw std::invalid_argument("Invalid terrain height field");
    const double u = std::clamp((north - origin_north) / spacing, 0.0, double(columns - 1));
    const double v = std::clamp((west - origin_west) / spacing, 0.0, double(rows - 1));
    const int x = std::min(int(u), columns - 2), y = std::min(int(v), rows - 2);
    const double tx = u - x, ty = v - y;
    const double h00 = heights[y * columns + x], h10 = heights[y * columns + x + 1];
    const double h01 = heights[(y + 1) * columns + x], h11 = heights[(y + 1) * columns + x + 1];
    if (tx + ty <= 1)
        return h00 + tx * (h10 - h00) + ty * (h01 - h00);
    return h11 + (1 - tx) * (h01 - h11) + (1 - ty) * (h10 - h11);
}
struct TerrainTile {
    double origin_north = 0, origin_west = 0, spacing = 50;
    int columns = 2, rows = 2;
    std::vector<double> heights{0, 0, 0, 0};
    bool contains(double n, double w) const {
        return n >= origin_north && w >= origin_west && n <= origin_north + spacing * (columns - 1) &&
               w <= origin_west + spacing * (rows - 1);
    }
    double height(double n, double w) const {
        return sample_height_field(origin_north, origin_west, spacing, columns, rows, heights, n, w);
    }
};
// A multi-resolution height field usable without any renderer or GPU.
struct GameTerrain {
    double origin_north = -50000.0, origin_west = -50000.0;
    double spacing = 1000.0;
    int columns = 2, rows = 2;
    std::vector<double> heights{0.0, 0.0, 0.0, 0.0};
    std::vector<TerrainTile> detail_tiles;
    // Set from the actual immutable data by GameSession; infinity disables the shortcut on mutable DTOs.
    double maximum_height = std::numeric_limits<double>::infinity();
    double height(double north, double west) const;
    bool line_of_sight(const std::array<double, 3> &a, const std::array<double, 3> &b) const;
};

inline double GameTerrain::height(double north, double west) const {
    const TerrainTile *selected = nullptr;
    for (const auto &tile : detail_tiles)
        if (tile.contains(north, west) && (!selected || tile.spacing < selected->spacing))
            selected = &tile;
    if (selected)
        return selected->height(north, west);
    return sample_height_field(origin_north, origin_west, spacing, columns, rows, heights, north, west);
}

class GameSession {
  public:
    explicit GameSession(const std::string &log_path = "bvr_game.log");
    ~GameSession();
    GameSession(const GameSession &) = delete;
    GameSession &operator=(const GameSession &) = delete;
    void reset(const GameConfig &config);
    void submit(const PilotCommand &command);
    void step(int ticks = 1);       // honors pause
    void step_exact(int ticks = 1); // deterministic debugger step, even when paused
    void set_paused(bool paused);
    GameFrame frame() const;
    GameTerrain terrain() const;
    void set_terrain(const GameTerrain &terrain);
    void close();

  private:
    void advance(int ticks, bool force);
    void publish_frame();
    void apply_command(const PilotCommand &command);
    void drive_player(const PilotCommand &command);
    void update_enemy();
    void record(std::string kind, std::string actor, std::string target, std::string weapon,
                std::string message, std::array<double, 3> position = {});
    std::shared_ptr<Fighter> fighter(const std::string &uid) const;
    mutable std::mutex mutex_;
    std::unique_ptr<SimCore> core_;
    std::shared_ptr<GameTerrain> terrain_;
    GameConfig config_;
    GameFrame frame_;
    std::vector<PilotCommand> pending_;
    std::optional<PilotCommand> pilot_controls_;
    std::vector<CombatEvent> events_;
    std::set<std::string> seen_deaths_, seen_missiles_;
    bool paused_ = false, closed_ = false;
    std::uint64_t tick_ = 0, applied_tick_ = 0;
    unsigned bomb_serial_ = 0;
    std::string selected_target_, result_ = "running";
    std::string enemy_behavior_ = "intercept";
    bool enemy_locked_ = false;
    std::map<std::string, double> weapon_launch_times_;
};
} // namespace bvr_sim
