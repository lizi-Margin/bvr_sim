#include "environment.hxx"
namespace bvr_sim {
void ContactSurface::prepare() {
    if (vertices.size() < 3 || indices.size() % 3)
        throw std::invalid_argument("Invalid core contact surface: " + id);
    bounds = {INFINITY, INFINITY, -INFINITY, -INFINITY};
    for (auto p : vertices) {
        for (double x : p)
            if (!std::isfinite(x))
                throw std::invalid_argument("Non-finite surface");
        bounds[0] = std::min(bounds[0], p[0]);
        bounds[1] = std::min(bounds[1], p[1]);
        bounds[2] = std::max(bounds[2], p[0]);
        bounds[3] = std::max(bounds[3], p[1]);
    }
    for (auto index : indices)
        if (index >= vertices.size())
            throw std::invalid_argument("Surface index");
    triangle_index_.clear();
    for (size_t i = 0; i + 2 < indices.size(); i += 3) {
        std::array<double, 4> b{INFINITY, INFINITY, -INFINITY, -INFINITY};
        for (int k = 0; k < 3; ++k) {
            const auto &p = vertices[indices[i + k]];
            b[0] = std::min(b[0], p[0]);
            b[1] = std::min(b[1], p[1]);
            b[2] = std::max(b[2], p[0]);
            b[3] = std::max(b[3], p[1]);
        }
        for (int x = int(std::floor(b[0] / 64)); x <= int(std::floor(b[2] / 64)); ++x)
            for (int y = int(std::floor(b[1] / 64)); y <= int(std::floor(b[3] / 64)); ++y)
                triangle_index_[{x, y}].push_back(i);
    }
    prepared_indices_ = indices.size();
}
std::optional<double> ContactSurface::height(double n, double w) const {
    if (n < bounds[0] || w < bounds[1] || n > bounds[2] || w > bounds[3])
        return std::nullopt;
    std::optional<double> highest;
    auto test = [&](size_t i) {
        const auto &a = vertices[indices[i]];
        const auto &b = vertices[indices[i + 1]];
        const auto &c = vertices[indices[i + 2]];
        const double det = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]);
        if (std::abs(det) < 1e-10)
            return;
        const double u = ((n - a[0]) * (c[1] - a[1]) - (w - a[1]) * (c[0] - a[0])) / det;
        const double v = ((b[0] - a[0]) * (w - a[1]) - (b[1] - a[1]) * (n - a[0])) / det;
        if (u >= -1e-8 && v >= -1e-8 && u + v <= 1 + 1e-8) {
            double z = a[2] + u * (b[2] - a[2]) + v * (c[2] - a[2]);
            if (!highest || z > *highest)
                highest = z;
        }
    };
    if (prepared_indices_ == indices.size()) {
        auto found = triangle_index_.find({int(std::floor(n / 64)), int(std::floor(w / 64))});
        if (found != triangle_index_.end())
            for (auto i : found->second)
                test(i);
    } else
        for (size_t i = 0; i + 2 < indices.size(); i += 3)
            test(i);
    return highest;
}
bool CollisionBox::overlaps(double n, double w, double bottom, double top, double radius) const {
    if (top < center[2] - half_size[2] || bottom > center[2] + half_size[2])
        return false;
    double dn = n - center[0], dw = w - center[1];
    double x = std::cos(yaw) * dn + std::sin(yaw) * dw, y = -std::sin(yaw) * dn + std::cos(yaw) * dw;
    return std::abs(x) < half_size[0] + radius && std::abs(y) < half_size[1] + radius;
}
bool WaterRegion::contains(double n, double w) const {
    if (polygon.size() < 3)
        return false;
    bool result = false;
    for (size_t i = 0, j = polygon.size() - 1; i < polygon.size(); j = i++) {
        const auto &a = polygon[i];
        const auto &b = polygon[j];
        if ((a[1] > w) != (b[1] > w) && n < (b[0] - a[0]) * (w - a[1]) / (b[1] - a[1]) + a[0])
            result = !result;
    }
    return result;
}
void Terrain::prepare_surfaces() {
    indexed_ = false;
    surface_index_.clear();
    obstacle_index_.clear();
    auto add = [](auto &index, const std::array<double, 4> &b, size_t id) {
        for (int x = int(std::floor(b[0] / 128)); x <= int(std::floor(b[2] / 128)); ++x)
            for (int y = int(std::floor(b[1] / 128)); y <= int(std::floor(b[3] / 128)); ++y)
                index[{x, y}].push_back(id);
    };
    for (auto &surface : contact_surfaces) {
        surface.prepare();
        if (std::isfinite(maximum_height))
            for (auto p : surface.vertices)
                maximum_height = std::max(maximum_height, p[2]);
    }
    for (const auto &obstacle : obstacles) {
        for (double x : obstacle.center)
            if (!std::isfinite(x))
                throw std::invalid_argument("Obstacle center");
        for (double x : obstacle.half_size)
            if (!std::isfinite(x) || x <= 0)
                throw std::invalid_argument("Obstacle extent");
        if (!std::isfinite(obstacle.yaw))
            throw std::invalid_argument("Obstacle heading");
        if (std::isfinite(maximum_height))
            maximum_height = std::max(maximum_height, obstacle.center[2] + obstacle.half_size[2]);
    }
    for (size_t i = 0; i < contact_surfaces.size(); ++i)
        add(surface_index_, contact_surfaces[i].bounds, i);
    for (size_t i = 0; i < obstacles.size(); ++i) {
        const auto &o = obstacles[i];
        double c = std::abs(std::cos(o.yaw)), s = std::abs(std::sin(o.yaw));
        double n = c * o.half_size[0] + s * o.half_size[1], w = s * o.half_size[0] + c * o.half_size[1];
        add(obstacle_index_, {o.center[0] - n, o.center[1] - w, o.center[0] + n, o.center[1] + w}, i);
    }
    prepared_surfaces_ = contact_surfaces.size();
    prepared_obstacles_ = obstacles.size();
    indexed_ = true;
}
double Terrain::collision_height(double n, double w) const {
    double z = height(n, w);
    each_surface(n, w, [&](const auto &s) {
        if (auto h = s.height(n, w))
            z = std::max(z, *h);
    });
    each_obstacle(n, w, 0, [&](const auto &b) {
        if (b.overlaps(n, w, -INFINITY, INFINITY))
            z = std::max(z, b.center[2] + b.half_size[2]);
    });
    return z;
}
GroundContact Terrain::contact(double n, double w, double yaw, double reference, double max_step) const {
    auto sample = [&](double x, double y) {
        double z = height(x, y);
        each_surface(x, y, [&](const auto &s) {
            if (s.drivable)
                if (auto h = s.height(x, y))
                    if (*h <= reference + max_step && *h >= z)
                        z = *h;
        });
        return z;
    };
    GroundContact result;
    result.height = sample(n, w);
    each_surface(n, w, [&](const auto &s) {
        if (s.drivable)
            if (auto h = s.height(n, w))
                if (std::abs(*h - result.height) < 1e-5) {
                    result.surface_id = s.id;
                    result.supported = true;
                }
    });
    for (const auto &r : water_regions)
        if (r.contains(n, w))
            result.water = true;
    if (result.supported)
        result.water = false;
    const double cn = std::cos(yaw), sw = std::sin(yaw), a = 1.2;
    const double along = (sample(n + cn * a, w + sw * a) - sample(n - cn * a, w - sw * a)) / (2 * a);
    const double across = (sample(n - sw * a, w + cn * a) - sample(n + sw * a, w - cn * a)) / (2 * a);
    result.pitch = std::atan(along);
    result.roll = std::atan(across);
    result.grade = std::hypot(along, across);
    return result;
}
bool Terrain::water_at(double n, double w, double reference, double max_step) const {
    bool wet = false;
    for (const auto &region : water_regions)
        if (region.contains(n, w)) {
            wet = true;
            break;
        }
    if (!wet)
        return false;
    double ground = height(n, w);
    each_surface(n, w, [&](const auto &surface) {
        if (surface.drivable)
            if (auto h = surface.height(n, w))
                if (*h >= ground && *h <= reference + max_step)
                    wet = false;
    });
    return wet;
}
bool Terrain::blocked(double n, double w, double bottom, double top, double radius) const {
    bool result = false;
    each_obstacle(n, w, radius, [&](const auto &box) {
        if (box.overlaps(n, w, bottom, top, radius))
            result = true;
    });
    return result;
}
bool Terrain::line_of_sight(const std::array<double, 3> &a, const std::array<double, 3> &b) const {
    if (std::min(a[2], b[2]) > maximum_height + 1)
        return true;
    double sample_spacing = spacing;
    for (const auto &tile : detail_tiles)
        sample_spacing = std::min(sample_spacing, tile.spacing);
    const int n = std::max(2, int(std::ceil(std::hypot(std::hypot(a[0] - b[0], a[1] - b[1]), a[2] - b[2]) /
                                            std::max(5.0, sample_spacing / 4))));
    for (int i = 1; i < n; ++i) {
        const double t = double(i) / n;
        if (a[2] + (b[2] - a[2]) * t < collision_height(a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            return false;
    }
    return true;
}
} // namespace bvr_sim
