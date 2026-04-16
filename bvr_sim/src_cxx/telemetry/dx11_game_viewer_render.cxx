#include "dx11_game_viewer_internal.hxx"
#include "resource_paths.hxx"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#include <d3dcompiler.h>
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#endif

namespace bvr_sim {

#ifdef _WIN32

namespace {

constexpr float kPi = 3.1415926535f;

template <typename T>
void safe_release(T*& ptr) {
    if (ptr) {
        ptr->Release();
        ptr = nullptr;
    }
}

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

RenderCommand make_clear_command(const std::array<float, 4>& clear_color) {
    RenderCommand command;
    command.type = RenderCommandType::Clear;
    command.clear_color = clear_color;
    return command;
}

RenderCommand make_draw_command(
    std::vector<Vertex> vertices,
    D3D11_PRIMITIVE_TOPOLOGY topology,
    const Float4x4& world_view_proj,
    bool depth_enabled) {
    RenderCommand command;
    command.type = RenderCommandType::Draw;
    command.vertices = std::move(vertices);
    command.topology = topology;
    command.world_view_proj = world_view_proj;
    command.depth_enabled = depth_enabled;
    return command;
}

bool ensure_dynamic_vertex_buffer(D3D11Context& d3d11, UINT required_capacity) {
    if (!d3d11.dynamic_vertex_buffer || d3d11.dynamic_vertex_capacity < required_capacity) {
        safe_release(d3d11.dynamic_vertex_buffer);
        d3d11.common_pipeline_bound = false;
        d3d11.dynamic_vertex_capacity = std::max<UINT>(required_capacity, std::max<UINT>(4096, d3d11.dynamic_vertex_capacity * 2));

        D3D11_BUFFER_DESC vb_desc = {};
        vb_desc.ByteWidth = d3d11.dynamic_vertex_capacity * sizeof(Vertex);
        vb_desc.Usage = D3D11_USAGE_DYNAMIC;
        vb_desc.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb_desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

        HRESULT create_hr = d3d11.device->CreateBuffer(&vb_desc, nullptr, &d3d11.dynamic_vertex_buffer);
        if (FAILED(create_hr) || !d3d11.dynamic_vertex_buffer) {
            d3d11.dynamic_vertex_capacity = 0;
            return false;
        }
    }
    return true;
}

bool upload_vertices(D3D11Context& d3d11, const std::vector<Vertex>& vertices) {
    if (!ensure_dynamic_vertex_buffer(d3d11, static_cast<UINT>(vertices.size()))) {
        return false;
    }
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.dynamic_vertex_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (FAILED(hr)) {
        return false;
    }
    std::memcpy(mapped.pData, vertices.data(), vertices.size() * sizeof(Vertex));
    d3d11.context->Unmap(d3d11.dynamic_vertex_buffer, 0);
    return true;
}

bool upload_scene_constants(D3D11Context& d3d11, const Float4x4& world_view_proj) {
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.constant_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (SUCCEEDED(hr)) {
        SceneConstants constants{};
        constants.world_view_proj = world_view_proj;
        std::memcpy(mapped.pData, &constants, sizeof(constants));
        d3d11.context->Unmap(d3d11.constant_buffer, 0);
    } else {
        return false;
    }
    return true;
}

void bind_draw_state(D3D11Context& d3d11, D3D11_PRIMITIVE_TOPOLOGY topology, bool depth_enabled) {
    UINT stride = sizeof(Vertex);
    UINT offset = 0;
    if (!d3d11.common_pipeline_bound) {
        d3d11.context->IASetVertexBuffers(0, 1, &d3d11.dynamic_vertex_buffer, &stride, &offset);
        d3d11.context->VSSetShader(d3d11.vertex_shader, nullptr, 0);
        d3d11.context->PSSetShader(d3d11.pixel_shader, nullptr, 0);
        d3d11.context->VSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
        d3d11.context->IASetInputLayout(d3d11.input_layout);
        d3d11.context->RSSetState(d3d11.rasterizer_state);
        d3d11.common_pipeline_bound = true;
    }
    if (d3d11.current_topology != topology) {
        d3d11.context->IASetPrimitiveTopology(topology);
        d3d11.current_topology = topology;
    }
    ID3D11DepthStencilState* depth_state = depth_enabled ? d3d11.depth_state : d3d11.depth_disabled_state;
    if (d3d11.current_depth_state != depth_state) {
        d3d11.context->OMSetDepthStencilState(depth_state, 0);
        d3d11.current_depth_state = depth_state;
    }
}

bool upload_and_draw(
    D3D11Context& d3d11,
    const std::vector<Vertex>& vertices,
    D3D11_PRIMITIVE_TOPOLOGY topology,
    const Float4x4& world_view_proj,
    bool depth_enabled,
    RenderFrameStats& stats) {
    if (vertices.empty()) {
        return true;
    }
    if (!upload_vertices(d3d11, vertices) || !upload_scene_constants(d3d11, world_view_proj)) {
        return false;
    }
    bind_draw_state(d3d11, topology, depth_enabled);
    d3d11.context->Draw(static_cast<UINT>(vertices.size()), 0);

    ++stats.draw_calls;
    stats.vertex_count += static_cast<long>(vertices.size());
    return true;
}

LRESULT CALLBACK dx11_window_proc(HWND hwnd, UINT msg, WPARAM w_param, LPARAM l_param) {
    Win32Window* window = reinterpret_cast<Win32Window*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
    switch (msg) {
    case WM_NCCREATE: {
        CREATESTRUCT* create_struct = reinterpret_cast<CREATESTRUCT*>(l_param);
        SetWindowLongPtr(hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(create_struct->lpCreateParams));
        return TRUE;
    }
    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    case WM_LBUTTONDOWN:
        if (window) {
            window->input.dragging = true;
            window->input.last_mouse_x = GET_X_LPARAM(l_param);
            window->input.last_mouse_y = GET_Y_LPARAM(l_param);
            SetCapture(hwnd);
        }
        return 0;
    case WM_LBUTTONUP:
        if (window) {
            window->input.dragging = false;
            ReleaseCapture();
        }
        return 0;
    case WM_MOUSEMOVE:
        if (window && window->input.dragging) {
            const int mouse_x = GET_X_LPARAM(l_param);
            const int mouse_y = GET_Y_LPARAM(l_param);
            const int dx = mouse_x - window->input.last_mouse_x;
            const int dy = mouse_y - window->input.last_mouse_y;
            window->input.last_mouse_x = mouse_x;
            window->input.last_mouse_y = mouse_y;
            window->input.camera_yaw += static_cast<float>(dx) * 0.006f;
            window->input.camera_pitch += static_cast<float>(dy) * 0.0045f;
            window->input.camera_pitch = std::clamp(window->input.camera_pitch, 0.12f, 1.45f);
        }
        return 0;
    case WM_MOUSEWHEEL:
        if (window) {
            const int delta = GET_WHEEL_DELTA_WPARAM(w_param);
            window->input.camera_distance -= static_cast<float>(delta) * 6.4f;
            window->input.camera_distance = std::clamp(window->input.camera_distance, 3000.0f, 180000.0f);
        }
        return 0;
    case WM_KEYDOWN:
        if (!window) {
            break;
        }
        if (w_param == 'W') window->input.move_forward = true;
        if (w_param == 'S') window->input.move_backward = true;
        if (w_param == 'A') window->input.move_left = true;
        if (w_param == 'D') window->input.move_right = true;
        if (w_param == 'Q') window->input.move_down = true;
        if (w_param == 'E') window->input.move_up = true;
        return 0;
    case WM_KEYUP:
        if (!window) {
            break;
        }
        if (w_param == 'W') window->input.move_forward = false;
        if (w_param == 'S') window->input.move_backward = false;
        if (w_param == 'A') window->input.move_left = false;
        if (w_param == 'D') window->input.move_right = false;
        if (w_param == 'Q') window->input.move_down = false;
        if (w_param == 'E') window->input.move_up = false;
        return 0;
    default:
        break;
    }
    return DefWindowProc(hwnd, msg, w_param, l_param);
}

bool create_depth_buffer(D3D11Context& d3d11, int width, int height, std::string& error) {
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);

    D3D11_TEXTURE2D_DESC depth_desc = {};
    depth_desc.Width = static_cast<UINT>(std::max(1, width));
    depth_desc.Height = static_cast<UINT>(std::max(1, height));
    depth_desc.MipLevels = 1;
    depth_desc.ArraySize = 1;
    depth_desc.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;
    depth_desc.SampleDesc.Count = 1;
    depth_desc.Usage = D3D11_USAGE_DEFAULT;
    depth_desc.BindFlags = D3D11_BIND_DEPTH_STENCIL;

    HRESULT hr = d3d11.device->CreateTexture2D(&depth_desc, nullptr, &d3d11.depth_texture);
    if (FAILED(hr) || !d3d11.depth_texture) {
        error = "CreateTexture2D(depth) failed";
        return false;
    }

    hr = d3d11.device->CreateDepthStencilView(d3d11.depth_texture, nullptr, &d3d11.dsv);
    if (FAILED(hr) || !d3d11.dsv) {
        error = "CreateDepthStencilView failed";
        return false;
    }
    return true;
}

bool create_render_targets_from_swap_chain(D3D11Context& d3d11, HWND hwnd, std::string& error) {
    safe_release(d3d11.rtv);

    ID3D11Texture2D* back_buffer = nullptr;
    HRESULT hr = d3d11.swap_chain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back_buffer));
    if (FAILED(hr) || !back_buffer) {
        error = "IDXGISwapChain::GetBuffer failed";
        return false;
    }

    hr = d3d11.device->CreateRenderTargetView(back_buffer, nullptr, &d3d11.rtv);
    safe_release(back_buffer);
    if (FAILED(hr) || !d3d11.rtv) {
        error = "CreateRenderTargetView failed";
        return false;
    }

    RECT rect = {};
    GetClientRect(hwnd, &rect);
    return create_depth_buffer(d3d11, rect.right - rect.left, rect.bottom - rect.top, error);
}

} // namespace

void update_camera(ViewerInputState& input, float dt_seconds) {
    const Float3 forward = make_float3(std::cos(input.camera_yaw), 0.0f, std::sin(input.camera_yaw));
    const Float3 right = make_float3(-forward.z, 0.0f, forward.x);
    const float move_speed = std::max(1200.0f, input.camera_distance * 0.40f) * dt_seconds;

    if (input.move_forward) input.camera_target = add(input.camera_target, scale(forward, move_speed));
    if (input.move_backward) input.camera_target = add(input.camera_target, scale(forward, -move_speed));
    if (input.move_left) input.camera_target = add(input.camera_target, scale(right, -move_speed));
    if (input.move_right) input.camera_target = add(input.camera_target, scale(right, move_speed));
    if (input.move_up) input.camera_target.y += move_speed;
    if (input.move_down) input.camera_target.y -= move_speed;
}

bool create_window(Win32Window& window, std::string& error) {
    window.instance = GetModuleHandle(nullptr);
    const char* class_name = "BvrSimDX11GameViewerWindow";

    WNDCLASS wc = {};
    wc.lpfnWndProc = dx11_window_proc;
    wc.hInstance = window.instance;
    wc.lpszClassName = class_name;
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);

    if (!RegisterClass(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        error = "RegisterClass failed";
        return false;
    }

    window.hwnd = CreateWindowEx(
        0,
        class_name,
        "BVR Sim DX11 Game Viewer",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1440,
        900,
        nullptr,
        nullptr,
        window.instance,
        &window
    );
    if (!window.hwnd) {
        error = "CreateWindowEx failed";
        return false;
    }

    ShowWindow(window.hwnd, SW_SHOW);
    UpdateWindow(window.hwnd);
    return true;
}

void destroy_window(Win32Window& window) {
    if (window.hwnd) {
        DestroyWindow(window.hwnd);
        window.hwnd = nullptr;
    }
}

void destroy_d3d11(D3D11Context& d3d11) {
    safe_release(d3d11.depth_disabled_state);
    safe_release(d3d11.depth_state);
    safe_release(d3d11.rasterizer_state);
    safe_release(d3d11.dynamic_vertex_buffer);
    safe_release(d3d11.constant_buffer);
    safe_release(d3d11.input_layout);
    safe_release(d3d11.pixel_shader);
    safe_release(d3d11.vertex_shader);
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);
    safe_release(d3d11.rtv);
    safe_release(d3d11.swap_chain);
    safe_release(d3d11.context);
    safe_release(d3d11.device);
}

bool create_d3d11(HWND hwnd, D3D11Context& d3d11, std::string& error) {
    DXGI_SWAP_CHAIN_DESC swap_desc = {};
    swap_desc.BufferCount = 2;
    swap_desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    swap_desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    swap_desc.OutputWindow = hwnd;
    swap_desc.SampleDesc.Count = 1;
    swap_desc.Windowed = TRUE;
    swap_desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    UINT create_flags = 0;
#if defined(_DEBUG)
    create_flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

    D3D_FEATURE_LEVEL feature_level = D3D_FEATURE_LEVEL_11_0;
    HRESULT hr = D3D11CreateDeviceAndSwapChain(
        nullptr,
        D3D_DRIVER_TYPE_HARDWARE,
        nullptr,
        create_flags,
        nullptr,
        0,
        D3D11_SDK_VERSION,
        &swap_desc,
        &d3d11.swap_chain,
        &d3d11.device,
        &feature_level,
        &d3d11.context
    );
    if (FAILED(hr) && (create_flags & D3D11_CREATE_DEVICE_DEBUG)) {
        create_flags &= ~D3D11_CREATE_DEVICE_DEBUG;
        hr = D3D11CreateDeviceAndSwapChain(
            nullptr,
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            create_flags,
            nullptr,
            0,
            D3D11_SDK_VERSION,
            &swap_desc,
            &d3d11.swap_chain,
            &d3d11.device,
            &feature_level,
            &d3d11.context
        );
    }
    if (FAILED(hr) || !d3d11.device || !d3d11.context || !d3d11.swap_chain) {
        error = "D3D11CreateDeviceAndSwapChain failed";
        return false;
    }

    if (!create_render_targets_from_swap_chain(d3d11, hwnd, error)) {
        return false;
    }

    const char* shader_source =
        "cbuffer SceneConstants : register(b0) {\n"
        "    float4x4 u_world_view_proj;\n"
        "};\n"
        "struct VSInput {\n"
        "    float3 position : POSITION;\n"
        "    float3 color : COLOR;\n"
        "};\n"
        "struct PSInput {\n"
        "    float4 position : SV_POSITION;\n"
        "    float3 color : COLOR;\n"
        "};\n"
        "PSInput vs_main(VSInput input) {\n"
        "    PSInput output;\n"
        "    output.position = mul(float4(input.position, 1.0), u_world_view_proj);\n"
        "    output.color = input.color;\n"
        "    return output;\n"
        "}\n"
        "float4 ps_main(PSInput input) : SV_TARGET {\n"
        "    return float4(input.color, 1.0);\n"
        "}\n";

    ID3DBlob* vs_blob = nullptr;
    ID3DBlob* ps_blob = nullptr;
    ID3DBlob* error_blob = nullptr;
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "vs_main", "vs_4_0", 0, 0, &vs_blob, &error_blob);
    if (FAILED(hr) || !vs_blob) {
        safe_release(error_blob);
        error = "D3DCompile(vs_main) failed";
        return false;
    }
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "ps_main", "ps_4_0", 0, 0, &ps_blob, &error_blob);
    safe_release(error_blob);
    if (FAILED(hr) || !ps_blob) {
        safe_release(vs_blob);
        error = "D3DCompile(ps_main) failed";
        return false;
    }

    hr = d3d11.device->CreateVertexShader(vs_blob->GetBufferPointer(), vs_blob->GetBufferSize(), nullptr, &d3d11.vertex_shader);
    if (FAILED(hr) || !d3d11.vertex_shader) {
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreateVertexShader failed";
        return false;
    }
    hr = d3d11.device->CreatePixelShader(ps_blob->GetBufferPointer(), ps_blob->GetBufferSize(), nullptr, &d3d11.pixel_shader);
    if (FAILED(hr) || !d3d11.pixel_shader) {
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreatePixelShader failed";
        return false;
    }

    D3D11_INPUT_ELEMENT_DESC input_layout_desc[] = {
        {"POSITION", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(Vertex, position)), D3D11_INPUT_PER_VERTEX_DATA, 0},
        {"COLOR", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(Vertex, color)), D3D11_INPUT_PER_VERTEX_DATA, 0},
    };
    hr = d3d11.device->CreateInputLayout(
        input_layout_desc,
        2,
        vs_blob->GetBufferPointer(),
        vs_blob->GetBufferSize(),
        &d3d11.input_layout
    );
    safe_release(vs_blob);
    safe_release(ps_blob);
    if (FAILED(hr) || !d3d11.input_layout) {
        error = "CreateInputLayout failed";
        return false;
    }

    D3D11_BUFFER_DESC cb_desc = {};
    cb_desc.ByteWidth = sizeof(SceneConstants);
    cb_desc.Usage = D3D11_USAGE_DYNAMIC;
    cb_desc.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cb_desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    hr = d3d11.device->CreateBuffer(&cb_desc, nullptr, &d3d11.constant_buffer);
    if (FAILED(hr) || !d3d11.constant_buffer) {
        error = "CreateBuffer(constant_buffer) failed";
        return false;
    }

    D3D11_RASTERIZER_DESC raster_desc = {};
    raster_desc.FillMode = D3D11_FILL_SOLID;
    raster_desc.CullMode = D3D11_CULL_BACK;
    raster_desc.DepthClipEnable = TRUE;
    hr = d3d11.device->CreateRasterizerState(&raster_desc, &d3d11.rasterizer_state);
    if (FAILED(hr) || !d3d11.rasterizer_state) {
        error = "CreateRasterizerState failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_desc = {};
    depth_desc.DepthEnable = TRUE;
    depth_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
    depth_desc.DepthFunc = D3D11_COMPARISON_LESS_EQUAL;
    hr = d3d11.device->CreateDepthStencilState(&depth_desc, &d3d11.depth_state);
    if (FAILED(hr) || !d3d11.depth_state) {
        error = "CreateDepthStencilState failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_disabled_desc = {};
    depth_disabled_desc.DepthEnable = FALSE;
    depth_disabled_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    depth_disabled_desc.DepthFunc = D3D11_COMPARISON_ALWAYS;
    hr = d3d11.device->CreateDepthStencilState(&depth_disabled_desc, &d3d11.depth_disabled_state);
    if (FAILED(hr) || !d3d11.depth_disabled_state) {
        error = "CreateDepthStencilState(depth_disabled) failed";
        return false;
    }

    return true;
}

bool resize_swap_chain_if_needed(D3D11Context& d3d11, HWND hwnd, UINT width, UINT height, std::string& error) {
    if (width == 0 || height == 0) {
        return true;
    }
    if (d3d11.back_buffer_width == width && d3d11.back_buffer_height == height && d3d11.rtv && d3d11.dsv) {
        return true;
    }

    safe_release(d3d11.rtv);
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);
    HRESULT hr = d3d11.swap_chain->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, 0);
    if (FAILED(hr)) {
        error = "ResizeBuffers failed";
        return false;
    }
    if (!create_render_targets_from_swap_chain(d3d11, hwnd, error)) {
        return false;
    }
    d3d11.back_buffer_width = width;
    d3d11.back_buffer_height = height;
    return true;
}

void update_viewport_from_client_rect(HWND hwnd, ID3D11DeviceContext* context, UINT& out_width, UINT& out_height) {
    RECT rect = {};
    GetClientRect(hwnd, &rect);
    out_width = static_cast<UINT>(std::max(1L, rect.right - rect.left));
    out_height = static_cast<UINT>(std::max(1L, rect.bottom - rect.top));

    D3D11_VIEWPORT viewport = {};
    viewport.TopLeftX = 0.0f;
    viewport.TopLeftY = 0.0f;
    viewport.Width = static_cast<float>(out_width);
    viewport.Height = static_cast<float>(out_height);
    viewport.MinDepth = 0.0f;
    viewport.MaxDepth = 1.0f;
    context->RSSetViewports(1, &viewport);
}

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

RenderCommandList record_render_commands(RenderScene scene) {
    RenderCommandList command_list;
    command_list.commands.reserve(4 + scene.object_batches.size());

    command_list.commands.push_back(make_clear_command({0.54f, 0.66f, 0.74f, 1.0f}));
    command_list.commands.push_back(make_draw_command(
        std::move(scene.sky_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
        scene.clip_space,
        false
    ));

    const Float4x4 view_projection = multiply(scene.view, scene.projection);
    command_list.commands.push_back(make_draw_command(
        std::move(scene.ground_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
        multiply(identity_matrix(), view_projection),
        true
    ));
    command_list.commands.push_back(make_draw_command(
        std::move(scene.grid_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_LINELIST,
        multiply(identity_matrix(), view_projection),
        true
    ));

    for (auto& batch : scene.object_batches) {
        command_list.commands.push_back(make_draw_command(
            std::move(batch.vertices),
            D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
            multiply(batch.world, view_projection),
            true
        ));
    }

    return command_list;
}

bool execute_render_commands(D3D11Context& d3d11, const RenderCommandList& command_list, RenderFrameStats& out_stats) {
    out_stats = {};
    out_stats.command_count = static_cast<long>(command_list.commands.size());

    ID3D11RenderTargetView* render_targets[1] = {d3d11.rtv};
    d3d11.context->OMSetRenderTargets(1, render_targets, d3d11.dsv);

    for (const RenderCommand& command : command_list.commands) {
        if (command.type == RenderCommandType::Clear) {
            d3d11.context->ClearRenderTargetView(d3d11.rtv, command.clear_color.data());
            d3d11.context->ClearDepthStencilView(d3d11.dsv, D3D11_CLEAR_DEPTH | D3D11_CLEAR_STENCIL, 1.0f, 0);
            continue;
        }

        if (!upload_and_draw(d3d11, command.vertices, command.topology, command.world_view_proj, command.depth_enabled, out_stats)) {
            return false;
        }
    }

    return true;
}

void draw_hud_text(HWND hwnd, const ViewerInputState& input, double sim_time, long object_count, const RenderFrameStats& stats) {
    HDC dc = GetDC(hwnd);
    if (!dc) {
        return;
    }

    RECT rect = {};
    GetClientRect(hwnd, &rect);
    SetBkMode(dc, TRANSPARENT);
    SetTextColor(dc, RGB(230, 240, 248));

    HFONT font = CreateFontA(
        -18,
        0,
        0,
        0,
        FW_MEDIUM,
        FALSE,
        FALSE,
        FALSE,
        ANSI_CHARSET,
        OUT_TT_PRECIS,
        CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY,
        FF_DONTCARE | DEFAULT_PITCH,
        "Consolas"
    );
    HFONT old_font = font ? static_cast<HFONT>(SelectObject(dc, font)) : nullptr;

    auto draw_line = [&](int x, int y, const std::string& text) {
        TextOutA(dc, x, y, text.c_str(), static_cast<int>(text.size()));
    };

    std::ostringstream line1;
    line1 << std::fixed << std::setprecision(2)
          << "SimTime " << sim_time
          << "  Objects " << object_count
          << "  Draws " << stats.draw_calls
          << "  Vertices " << stats.vertex_count;
    draw_line(16, 16, line1.str());

    std::ostringstream line2;
    line2 << std::fixed << std::setprecision(1)
          << "Camera Target (" << input.camera_target.x << ", " << input.camera_target.y << ", " << input.camera_target.z << ")"
          << "  Dist " << input.camera_distance;
    draw_line(16, 40, line2.str());

    draw_line(16, rect.bottom - 34, "Move: W A S D  Vertical: Q/E  Look: drag mouse  Zoom: wheel");

    if (font && old_font) {
        SelectObject(dc, old_font);
    }
    if (font) {
        DeleteObject(font);
    }
    ReleaseDC(hwnd, dc);
}

#endif

} // namespace bvr_sim
