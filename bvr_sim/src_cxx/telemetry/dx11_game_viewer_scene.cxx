#include "dx11_game_viewer_internal.hxx"
#include "resource_paths.hxx"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

namespace bvr_sim {

#ifdef _WIN32

namespace {

constexpr float kPi = 3.1415926535f;

MeshLibrary& mesh_library() {
    static MeshLibrary library;
    return library;
}

std::string canonicalize_mesh_name(std::string mesh_name) {
    std::replace(mesh_name.begin(), mesh_name.end(), '_', '-');
    return mesh_name;
}

std::string map_model_to_mesh_name(const std::string& model_name) {
    static const std::unordered_map<std::string, std::string> k_model_mesh_map = {
        {"F15", "FixedWing.F-15"},
        {"F15-original", "FixedWing.F-15"},
        {"F16", "FixedWing.F-16"},
        {"F16-original", "FixedWing.F-16"},
        {"F18", "FixedWing.F-18C"},
        {"F18-original", "FixedWing.F-18C"},
        {"F22", "FixedWing.F-22"},
        {"F22-original", "FixedWing.F-22"},
        {"AIM-120", "Missile.AIM-120C"},
        {"AIM-120C", "Missile.AIM-120C"},
        {"AIM-120C5", "Missile.AIM-120C"},
        {"AIM-120C7", "Missile.AIM-120C"},
        {"AIM-120C-MModelA", "Missile.AIM-120C"},
        {"AIM-120C-MModelA-Poor", "Missile.AIM-120C"},
        {"AIM-9", "Missile.AIM-9M"},
        {"AIM-9M", "Missile.AIM-9M"},
        {"AIM-9M-Omni", "Missile.AIM-9M"},
    };

    const auto canonical_model = canonicalize_mesh_name(model_name);
    const auto it = k_model_mesh_map.find(canonical_model);
    if (it != k_model_mesh_map.end()) {
        return it->second;
    }
    return "";
}

Float3 make_float3(float x, float y, float z) {
    Float3 v;
    v.x = x;
    v.y = y;
    v.z = z;
    return v;
}

Float3 add(const Float3& a, const Float3& b) {
    return make_float3(a.x + b.x, a.y + b.y, a.z + b.z);
}

Float3 sub(const Float3& a, const Float3& b) {
    return make_float3(a.x - b.x, a.y - b.y, a.z - b.z);
}

Float3 scale(const Float3& v, float s) {
    return make_float3(v.x * s, v.y * s, v.z * s);
}

float dot(const Float3& a, const Float3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Float3 cross(const Float3& a, const Float3& b) {
    return make_float3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    );
}

Float3 normalize(const Float3& v) {
    const float len_sq = dot(v, v);
    if (len_sq <= 1e-8f) {
        return make_float3(0.0f, 0.0f, 0.0f);
    }
    const float inv_len = 1.0f / std::sqrt(len_sq);
    return scale(v, inv_len);
}

std::vector<std::string> split_whitespace(const std::string& line) {
    std::istringstream iss(line);
    std::vector<std::string> tokens;
    std::string token;
    while (iss >> token) {
        tokens.push_back(token);
    }
    return tokens;
}

int parse_obj_index(const std::string& token) {
    if (token.empty()) {
        return -1;
    }
    const auto slash_pos = token.find('/');
    const auto index_token = slash_pos == std::string::npos ? token : token.substr(0, slash_pos);
    if (index_token.empty()) {
        return -1;
    }
    return std::stoi(index_token);
}

bool load_obj_mesh(const std::filesystem::path& path, MeshData& mesh, std::string& error) {
    std::ifstream input(path);
    if (!input.is_open()) {
        error = "failed to open " + path.string();
        return false;
    }

    std::vector<std::array<float, 3>> positions;
    mesh.vertices.clear();

    std::string line;
    while (std::getline(input, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }

        const auto tokens = split_whitespace(line);
        if (tokens.empty()) {
            continue;
        }

        if (tokens[0] == "v" && tokens.size() >= 4) {
            positions.push_back({
                std::stof(tokens[1]),
                std::stof(tokens[2]),
                std::stof(tokens[3])
            });
            continue;
        }

        if (tokens[0] == "f" && tokens.size() >= 4) {
            std::vector<int> face_indices;
            face_indices.reserve(tokens.size() - 1);
            for (size_t i = 1; i < tokens.size(); ++i) {
                const int obj_index = parse_obj_index(tokens[i]);
                if (obj_index == 0) {
                    continue;
                }
                const int vertex_index = obj_index > 0 ? obj_index - 1 : static_cast<int>(positions.size()) + obj_index;
                if (vertex_index < 0 || vertex_index >= static_cast<int>(positions.size())) {
                    continue;
                }
                face_indices.push_back(vertex_index);
            }

            if (face_indices.size() < 3) {
                continue;
            }

            for (size_t i = 1; i + 1 < face_indices.size(); ++i) {
                mesh.vertices.push_back(positions[face_indices[0]]);
                mesh.vertices.push_back(positions[face_indices[i]]);
                mesh.vertices.push_back(positions[face_indices[i + 1]]);
            }
        }
    }

    if (mesh.vertices.empty()) {
        error = "mesh has no triangle vertices: " + path.string();
        return false;
    }

    std::array<float, 3> min_v = mesh.vertices.front();
    std::array<float, 3> max_v = mesh.vertices.front();
    for (const auto& vertex : mesh.vertices) {
        for (int i = 0; i < 3; ++i) {
            min_v[i] = std::min(min_v[i], vertex[i]);
            max_v[i] = std::max(max_v[i], vertex[i]);
        }
    }

    mesh.center = {
        (min_v[0] + max_v[0]) * 0.5f,
        (min_v[1] + max_v[1]) * 0.5f,
        (min_v[2] + max_v[2]) * 0.5f
    };

    mesh.radius = 1.0f;
    for (const auto& vertex : mesh.vertices) {
        const float dx = vertex[0] - mesh.center[0];
        const float dy = vertex[1] - mesh.center[1];
        const float dz = vertex[2] - mesh.center[2];
        mesh.radius = std::max(mesh.radius, std::sqrt(dx * dx + dy * dy + dz * dz));
    }

    mesh.loaded = true;
    return true;
}

MeshData* load_named_mesh(const std::string& mesh_name) {
    auto& library = mesh_library();
    const auto canonical_name = canonicalize_mesh_name(mesh_name);
    auto it = library.meshes.find(canonical_name);
    if (it != library.meshes.end() && it->second.loaded) {
        return &it->second;
    }

    try {
        MeshData mesh;
        std::string error;
        const auto path = resource_paths::get_resource_path("visualization/meshes/" + canonical_name + ".obj");
        if (!load_obj_mesh(path, mesh, error)) {
            return nullptr;
        }
        auto [inserted_it, _] = library.meshes.emplace(canonical_name, std::move(mesh));
        return &inserted_it->second;
    } catch (...) {
        return nullptr;
    }
}

Float4x4 identity_matrix() {
    Float4x4 out{};
    out.m[0][0] = 1.0f;
    out.m[1][1] = 1.0f;
    out.m[2][2] = 1.0f;
    out.m[3][3] = 1.0f;
    return out;
}

Float4x4 multiply(const Float4x4& a, const Float4x4& b) {
    Float4x4 out{};
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) {
            out.m[r][c] = a.m[r][0] * b.m[0][c]
                        + a.m[r][1] * b.m[1][c]
                        + a.m[r][2] * b.m[2][c]
                        + a.m[r][3] * b.m[3][c];
        }
    }
    return out;
}

Float4x4 translation_matrix(float x, float y, float z) {
    Float4x4 out = identity_matrix();
    out.m[3][0] = x;
    out.m[3][1] = y;
    out.m[3][2] = z;
    return out;
}

Float4x4 scale_matrix(float sx, float sy, float sz) {
    Float4x4 out{};
    out.m[0][0] = sx;
    out.m[1][1] = sy;
    out.m[2][2] = sz;
    out.m[3][3] = 1.0f;
    return out;
}

Float4x4 rotation_x_matrix(float angle) {
    Float4x4 out = identity_matrix();
    const float c = std::cos(angle);
    const float s = std::sin(angle);
    out.m[1][1] = c;
    out.m[1][2] = s;
    out.m[2][1] = -s;
    out.m[2][2] = c;
    return out;
}

Float4x4 rotation_y_matrix(float angle) {
    Float4x4 out = identity_matrix();
    const float c = std::cos(angle);
    const float s = std::sin(angle);
    out.m[0][0] = c;
    out.m[0][2] = -s;
    out.m[2][0] = s;
    out.m[2][2] = c;
    return out;
}

Float4x4 rotation_z_matrix(float angle) {
    Float4x4 out = identity_matrix();
    const float c = std::cos(angle);
    const float s = std::sin(angle);
    out.m[0][0] = c;
    out.m[0][1] = s;
    out.m[1][0] = -s;
    out.m[1][1] = c;
    return out;
}

Float4x4 perspective_matrix(float fov_y_radians, float aspect, float z_near, float z_far) {
    Float4x4 out{};
    const float y_scale = 1.0f / std::tan(fov_y_radians * 0.5f);
    const float x_scale = y_scale / aspect;
    out.m[0][0] = x_scale;
    out.m[1][1] = y_scale;
    out.m[2][2] = z_far / (z_far - z_near);
    out.m[2][3] = 1.0f;
    out.m[3][2] = (-z_near * z_far) / (z_far - z_near);
    return out;
}

Float4x4 orthographic_identity_clip_matrix() {
    return identity_matrix();
}

Float4x4 look_at_matrix(const Float3& eye, const Float3& target, const Float3& up_hint) {
    const Float3 forward = normalize(sub(target, eye));
    const Float3 right = normalize(cross(up_hint, forward));
    const Float3 up = cross(forward, right);

    Float4x4 out = identity_matrix();
    out.m[0][0] = right.x;
    out.m[1][0] = right.y;
    out.m[2][0] = right.z;
    out.m[0][1] = up.x;
    out.m[1][1] = up.y;
    out.m[2][1] = up.z;
    out.m[0][2] = forward.x;
    out.m[1][2] = forward.y;
    out.m[2][2] = forward.z;
    out.m[3][0] = -dot(right, eye);
    out.m[3][1] = -dot(up, eye);
    out.m[3][2] = -dot(forward, eye);
    return out;
}

bool is_aircraft_object(const TelemetryObjectState& object) {
    return object.type.find("Aircraft") != std::string::npos;
}

bool is_missile_object(const TelemetryObjectState& object) {
    return object.type.find("Missile") != std::string::npos;
}

float object_world_radius(const TelemetryObjectState& object) {
    if (is_missile_object(object)) {
        return 180.0f;
    }
    if (is_aircraft_object(object)) {
        return 320.0f;
    }
    return 180.0f;
}

std::string resolve_mesh_asset_name(const TelemetryObjectState& object) {
    const std::string mapped_mesh = map_model_to_mesh_name(object.mesh_name);
    if (!mapped_mesh.empty() && load_named_mesh(mapped_mesh) != nullptr) {
        return mapped_mesh;
    }
    if (is_aircraft_object(object) && load_named_mesh("aircraft") != nullptr) {
        return "aircraft";
    }
    if (is_missile_object(object) && load_named_mesh("missile") != nullptr) {
        return "missile";
    }
    return "";
}

std::array<float, 3> team_color(const TelemetryObjectState& object) {
    if (object.team == "Blue") {
        return {0.34f, 0.73f, 1.0f};
    }
    if (object.team == "Red") {
        return {1.0f, 0.42f, 0.34f};
    }
    return {0.85f, 0.85f, 0.78f};
}

void append_box(std::vector<Vertex>& vertices, float sx, float sy, float sz, const std::array<float, 3>& color) {
    const float hx = sx * 0.5f;
    const float hy = sy * 0.5f;
    const float hz = sz * 0.5f;
    const float r = color[0];
    const float g = color[1];
    const float b = color[2];

    auto push_triangle = [&](Float3 a, Float3 c, Float3 d) {
        vertices.push_back({{a.x, a.y, a.z}, {r, g, b}});
        vertices.push_back({{c.x, c.y, c.z}, {r, g, b}});
        vertices.push_back({{d.x, d.y, d.z}, {r, g, b}});
    };
    auto push_quad = [&](Float3 a, Float3 c, Float3 d, Float3 e) {
        push_triangle(a, c, d);
        push_triangle(a, d, e);
    };

    push_quad(make_float3(-hx, -hy, hz), make_float3(hx, -hy, hz), make_float3(hx, hy, hz), make_float3(-hx, hy, hz));
    push_quad(make_float3(-hx, -hy, -hz), make_float3(-hx, hy, -hz), make_float3(hx, hy, -hz), make_float3(hx, -hy, -hz));
    push_quad(make_float3(-hx, -hy, -hz), make_float3(-hx, -hy, hz), make_float3(-hx, hy, hz), make_float3(-hx, hy, -hz));
    push_quad(make_float3(hx, -hy, -hz), make_float3(hx, hy, -hz), make_float3(hx, hy, hz), make_float3(hx, -hy, hz));
    push_quad(make_float3(-hx, hy, -hz), make_float3(-hx, hy, hz), make_float3(hx, hy, hz), make_float3(hx, hy, -hz));
    push_quad(make_float3(-hx, -hy, -hz), make_float3(hx, -hy, -hz), make_float3(hx, -hy, hz), make_float3(-hx, -hy, hz));
}

void append_aircraft_primitive(std::vector<Vertex>& vertices, const std::array<float, 3>& color) {
    const float r = color[0];
    const float g = color[1];
    const float b = color[2];
    auto push_triangle = [&](Float3 a, Float3 c, Float3 d) {
        vertices.push_back({{a.x, a.y, a.z}, {r, g, b}});
        vertices.push_back({{c.x, c.y, c.z}, {r, g, b}});
        vertices.push_back({{d.x, d.y, d.z}, {r, g, b}});
    };

    push_triangle(make_float3(180.0f, 0.0f, 0.0f), make_float3(-120.0f, 40.0f, 90.0f), make_float3(-120.0f, 40.0f, -90.0f));
    push_triangle(make_float3(180.0f, 0.0f, 0.0f), make_float3(-120.0f, -40.0f, -90.0f), make_float3(-120.0f, -40.0f, 90.0f));

    append_box(vertices, 150.0f, 16.0f, 520.0f, color);
}

void append_missile_primitive(std::vector<Vertex>& vertices, const std::array<float, 3>& color) {
    append_box(vertices, 220.0f, 24.0f, 24.0f, color);
}

void append_ground_primitive(std::vector<Vertex>& vertices, const std::array<float, 3>& color) {
    append_box(vertices, 180.0f, 90.0f, 180.0f, color);
}

void append_obj_mesh(std::vector<Vertex>& vertices, const MeshData& mesh, float world_radius, const std::array<float, 3>& color) {
    if (!mesh.loaded || mesh.vertices.empty() || mesh.radius <= 1e-6f) {
        return;
    }

    const float scale_value = world_radius / mesh.radius;
    for (const auto& vertex : mesh.vertices) {
        vertices.push_back({
            {
                (vertex[0] - mesh.center[0]) * scale_value,
                (vertex[1] - mesh.center[1]) * scale_value,
                (vertex[2] - mesh.center[2]) * scale_value
            },
            {color[0], color[1], color[2]}
        });
    }
}

void append_ground_plane(std::vector<Vertex>& vertices, float size) {
    const std::array<float, 3> near_color = {0.16f, 0.22f, 0.18f};
    const std::array<float, 3> far_color = {0.22f, 0.28f, 0.21f};

    auto push_vertex = [&](float x, float y, float z, const std::array<float, 3>& color) {
        vertices.push_back({{x, y, z}, {color[0], color[1], color[2]}});
    };

    push_vertex(-size, 0.0f, -size, far_color);
    push_vertex(size, 0.0f, -size, far_color);
    push_vertex(size, 0.0f, size, near_color);

    push_vertex(-size, 0.0f, -size, far_color);
    push_vertex(size, 0.0f, size, near_color);
    push_vertex(-size, 0.0f, size, near_color);
}

void append_sky_quad(std::vector<Vertex>& vertices) {
    const std::array<float, 3> top = {0.20f, 0.39f, 0.62f};
    const std::array<float, 3> horizon = {0.77f, 0.83f, 0.88f};

    auto push_vertex = [&](float x, float y, const std::array<float, 3>& color) {
        vertices.push_back({{x, y, 0.0f}, {color[0], color[1], color[2]}});
    };

    push_vertex(-1.0f, 1.0f, top);
    push_vertex(1.0f, 1.0f, top);
    push_vertex(1.0f, -1.0f, horizon);

    push_vertex(-1.0f, 1.0f, top);
    push_vertex(1.0f, -1.0f, horizon);
    push_vertex(-1.0f, -1.0f, horizon);
}

void append_grid(std::vector<Vertex>& vertices, float size, int half_count) {
    const float r = 0.24f;
    const float g = 0.29f;
    const float b = 0.25f;
    for (int i = -half_count; i <= half_count; ++i) {
        const float value = size * static_cast<float>(i) / static_cast<float>(half_count);
        vertices.push_back({{value, 0.0f, -size}, {r, g, b}});
        vertices.push_back({{value, 0.0f, size}, {r, g, b}});
        vertices.push_back({{-size, 0.0f, value}, {r, g, b}});
        vertices.push_back({{size, 0.0f, value}, {r, g, b}});
    }
}

Float4x4 build_object_world_matrix(const TelemetryObjectState& object) {
    const float scale_value = object_world_radius(object) / 180.0f;
    const Float4x4 scale_m = scale_matrix(scale_value, scale_value, scale_value);
    const Float4x4 model_offset = rotation_y_matrix(270.0f * kPi / 180.0f);
    const Float4x4 roll_m = rotation_x_matrix(static_cast<float>(object.orientation[0]));
    const Float4x4 pitch_m = rotation_z_matrix(static_cast<float>(object.orientation[1]));
    const Float4x4 yaw_m = rotation_y_matrix(static_cast<float>(object.orientation[2]));
    const Float4x4 translation_m = translation_matrix(
        static_cast<float>(object.position[0]),
        static_cast<float>(object.position[2]),
        static_cast<float>(object.position[1])
    );
    return multiply(multiply(multiply(multiply(scale_m, model_offset), roll_m), pitch_m), multiply(yaw_m, translation_m));
}

void create_object_geometry(const TelemetryObjectState& object, std::vector<Vertex>& vertices) {
    const auto color = team_color(object);
    const std::string mesh_asset = resolve_mesh_asset_name(object);
    if (!mesh_asset.empty()) {
        if (MeshData* mesh = load_named_mesh(mesh_asset)) {
            append_obj_mesh(vertices, *mesh, object_world_radius(object), color);
            return;
        }
    }
    if (is_aircraft_object(object)) {
        append_aircraft_primitive(vertices, color);
        return;
    }
    if (is_missile_object(object)) {
        append_missile_primitive(vertices, color);
        return;
    }
    append_ground_primitive(vertices, color);
}

} // namespace

RenderScene build_render_scene(const ViewerInputState& input, UINT width, UINT height, const WorldSnapshot* snapshot) {
    RenderScene scene;

    const float aspect = static_cast<float>(width) / static_cast<float>(std::max(1U, height));
    const Float3 eye = add(
        input.camera_target,
        make_float3(
            std::cos(input.camera_pitch) * std::cos(input.camera_yaw) * input.camera_distance,
            std::sin(input.camera_pitch) * input.camera_distance,
            std::cos(input.camera_pitch) * std::sin(input.camera_yaw) * input.camera_distance
        )
    );

    scene.view = look_at_matrix(eye, input.camera_target, make_float3(0.0f, 1.0f, 0.0f));
    scene.projection = perspective_matrix(50.0f * kPi / 180.0f, aspect, 10.0f, 500000.0f);
    scene.clip_space = orthographic_identity_clip_matrix();

    append_sky_quad(scene.sky_vertices);
    append_ground_plane(scene.ground_vertices, 140000.0f);
    append_grid(scene.grid_vertices, 120000.0f, 18);

    if (!snapshot) {
        return scene;
    }

    scene.object_batches.reserve(snapshot->objects.size());
    for (const auto& object : snapshot->objects) {
        if (!object.alive) {
            continue;
        }

        RenderScene::ObjectBatch batch;
        create_object_geometry(object, batch.vertices);
        batch.world = build_object_world_matrix(object);
        scene.object_batches.push_back(std::move(batch));
    }

    return scene;
}

#endif

} // namespace bvr_sim
