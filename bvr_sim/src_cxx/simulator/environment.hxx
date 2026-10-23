#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <vector>
#include <string>
#include <optional>
#include <map>

namespace bvr_sim {
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
// Explicit triangle surfaces preserve bridge decks above riverbeds. Coordinates are NWU metres.
struct ContactSurface {
    std::string id, material;
    std::vector<std::array<double, 3>> vertices;
    std::vector<unsigned> indices;
    bool drivable = true;
    std::array<double, 4> bounds{-INFINITY, -INFINITY, INFINITY, INFINITY};
    std::optional<double> height(double north, double west) const;
    void prepare();

  private:
    std::map<std::pair<int, int>, std::vector<size_t>> triangle_index_;
    size_t prepared_indices_ = 0;
};
struct CollisionBox {
    std::string id;
    std::array<double, 3> center{}, half_size{1, 1, 1};
    double yaw = 0;
    bool overlaps(double north, double west, double bottom, double top, double radius = 0) const;
};
struct WaterRegion {
    std::string id;
    std::vector<std::array<double, 2>> polygon;
    bool contains(double north, double west) const;
};
struct GroundContact {
    double height = 0, pitch = 0, roll = 0, grade = 0;
    bool water = false, supported = false;
    std::string surface_id;
};
// A multi-resolution physical environment usable without any renderer or GPU.
struct Terrain {
    double origin_north = -50000.0, origin_west = -50000.0;
    double spacing = 1000.0;
    int columns = 2, rows = 2;
    std::vector<double> heights{0.0, 0.0, 0.0, 0.0};
    std::vector<TerrainTile> detail_tiles;
    std::vector<ContactSurface> contact_surfaces;
    std::vector<CollisionBox> obstacles;
    std::vector<WaterRegion> water_regions;
    // Set from the actual immutable data by GameSession; infinity disables the shortcut on mutable DTOs.
    double maximum_height = std::numeric_limits<double>::infinity();
    double height(double north, double west) const;
    double collision_height(double north, double west) const;
    GroundContact contact(double north, double west, double yaw = 0, double reference_height = INFINITY,
                          double max_step = .6) const;
    bool water_at(double north, double west, double reference_height = INFINITY, double max_step = .6) const;
    bool blocked(double north, double west, double bottom, double top, double radius = 0) const;
    void prepare_surfaces();
    bool line_of_sight(const std::array<double, 3> &a, const std::array<double, 3> &b) const;

  private:
    std::map<std::pair<int, int>, std::vector<size_t>> surface_index_, obstacle_index_;
    bool indexed_ = false;
    size_t prepared_surfaces_ = 0, prepared_obstacles_ = 0;
    template <class F> void each_surface(double n, double w, F f) const {
        if (indexed_ && prepared_surfaces_ == contact_surfaces.size()) {
            auto found = surface_index_.find({int(std::floor(n / 128)), int(std::floor(w / 128))});
            if (found != surface_index_.end())
                for (auto i : found->second)
                    f(contact_surfaces[i]);
        } else
            for (const auto &s : contact_surfaces)
                f(s);
    }
    template <class F> void each_obstacle(double n, double w, double radius, F f) const {
        if (indexed_ && prepared_obstacles_ == obstacles.size()) {
            for (int x = int(std::floor((n - radius) / 128)); x <= int(std::floor((n + radius) / 128)); ++x)
                for (int y = int(std::floor((w - radius) / 128)); y <= int(std::floor((w + radius) / 128));
                     ++y) {
                    auto found = obstacle_index_.find({x, y});
                    if (found != obstacle_index_.end())
                        for (auto i : found->second)
                            f(obstacles[i]);
                }
        } else
            for (const auto &o : obstacles)
                f(o);
    }
};

inline double Terrain::height(double north, double west) const {
    const TerrainTile *selected = nullptr;
    for (const auto &tile : detail_tiles)
        if (tile.contains(north, west) && (!selected || tile.spacing < selected->spacing))
            selected = &tile;
    if (selected)
        return selected->height(north, west);
    return sample_height_field(origin_north, origin_west, spacing, columns, rows, heights, north, west);
}

} // namespace bvr_sim
