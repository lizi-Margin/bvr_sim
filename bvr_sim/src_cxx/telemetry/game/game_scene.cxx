#include "dx11/game_dx11_internal.hxx"
#include "c3utils/c3utils.hxx"
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

MeshLibrary& mesh_library() {
    static MeshLibrary library;
    return library;
}

std::string canonicalize_mesh_name(std::string mesh_name) {
    std::replace(mesh_name.begin(), mesh_name.end(), '_', '-');
    return mesh_name;
}

std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input.is_open()) {
        return "";
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::string extract_json_object_block(const std::string& text, const std::string& key) {
    const std::string marker = "\"" + key + "\"";
    const size_t marker_pos = text.find(marker);
    if (marker_pos == std::string::npos) {
        return "";
    }
    const size_t open_pos = text.find('{', marker_pos + marker.size());
    if (open_pos == std::string::npos) {
        return "";
    }

    int depth = 0;
    for (size_t i = open_pos; i < text.size(); ++i) {
        if (text[i] == '{') {
            ++depth;
        } else if (text[i] == '}') {
            --depth;
            if (depth == 0) {
                return text.substr(open_pos, i - open_pos + 1);
            }
        }
    }
    return "";
}

std::unordered_map<std::string, std::string> load_model_material_map() {
    std::unordered_map<std::string, std::string> map;
    try {
        const std::string manifest = read_text_file(resource_paths::get_resource_path("visualization/materials/materials.json"));
        const std::string block = extract_json_object_block(manifest, "model_materials");
        if (block.empty()) {
            return map;
        }

        size_t pos = 0;
        while (true) {
            const size_t key_start = block.find('"', pos);
            if (key_start == std::string::npos) {
                break;
            }
            const size_t key_end = block.find('"', key_start + 1);
            if (key_end == std::string::npos) {
                break;
            }
            const size_t colon = block.find(':', key_end + 1);
            if (colon == std::string::npos) {
                break;
            }
            const size_t value_start = block.find('"', colon + 1);
            if (value_start == std::string::npos) {
                break;
            }
            const size_t value_end = block.find('"', value_start + 1);
            if (value_end == std::string::npos) {
                break;
            }

            map[canonicalize_mesh_name(block.substr(key_start + 1, key_end - key_start - 1))] =
                block.substr(value_start + 1, value_end - value_start - 1);
            pos = value_end + 1;
        }
    } catch (...) {
        map.clear();
    }
    return map;
}

const std::unordered_map<std::string, std::string>& model_material_map() {
    static const std::unordered_map<std::string, std::string> map = load_model_material_map();
    return map;
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

struct ObjFaceVertex {
    int position = -1;
    int uv = -1;
    int normal = -1;
};

int resolve_obj_index(int index, int count) {
    if (index == 0) {
        return -1;
    }
    const int resolved = index > 0 ? index - 1 : count + index;
    return resolved >= 0 && resolved < count ? resolved : -1;
}

ObjFaceVertex parse_obj_face_vertex(const std::string& token, int position_count, int uv_count, int normal_count) {
    ObjFaceVertex out;
    std::array<std::string, 3> parts;
    size_t part_index = 0;
    size_t start = 0;
    while (part_index < parts.size()) {
        const size_t slash = token.find('/', start);
        parts[part_index++] = token.substr(start, slash == std::string::npos ? std::string::npos : slash - start);
        if (slash == std::string::npos) {
            break;
        }
        start = slash + 1;
    }

    if (!parts[0].empty()) {
        out.position = resolve_obj_index(std::stoi(parts[0]), position_count);
    }
    if (!parts[1].empty()) {
        out.uv = resolve_obj_index(std::stoi(parts[1]), uv_count);
    }
    if (!parts[2].empty()) {
        out.normal = resolve_obj_index(std::stoi(parts[2]), normal_count);
    }
    return out;
}

bool load_obj_mesh(const std::filesystem::path& path, MeshData& mesh, std::string& error) {
    std::ifstream input(path);
    if (!input.is_open()) {
        error = "failed to open " + path.string();
        return false;
    }

    std::vector<std::array<float, 3>> positions;
    std::vector<std::array<float, 2>> uvs;
    std::vector<std::array<float, 3>> normals;
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

        if (tokens[0] == "vt" && tokens.size() >= 3) {
            uvs.push_back({
                std::stof(tokens[1]),
                1.0f - std::stof(tokens[2])
            });
            continue;
        }

        if (tokens[0] == "vn" && tokens.size() >= 4) {
            normals.push_back({
                std::stof(tokens[1]),
                std::stof(tokens[2]),
                std::stof(tokens[3])
            });
            continue;
        }

        if (tokens[0] == "f" && tokens.size() >= 4) {
            std::vector<ObjFaceVertex> face_vertices;
            face_vertices.reserve(tokens.size() - 1);
            for (size_t i = 1; i < tokens.size(); ++i) {
                const ObjFaceVertex face_vertex = parse_obj_face_vertex(
                    tokens[i],
                    static_cast<int>(positions.size()),
                    static_cast<int>(uvs.size()),
                    static_cast<int>(normals.size())
                );
                if (face_vertex.position < 0) {
                    continue;
                }
                face_vertices.push_back(face_vertex);
            }

            if (face_vertices.size() < 3) {
                continue;
            }

            auto make_mesh_vertex = [&](const ObjFaceVertex& source) {
                MeshData::MeshVertex mesh_vertex;
                mesh_vertex.position = positions[source.position];
                if (source.uv >= 0) {
                    mesh_vertex.uv = uvs[source.uv];
                }
                if (source.normal >= 0) {
                    mesh_vertex.normal = normals[source.normal];
                    mesh_vertex.has_normal = true;
                }
                return mesh_vertex;
            };

            for (size_t i = 1; i + 1 < face_vertices.size(); ++i) {
                MeshData::MeshVertex a = make_mesh_vertex(face_vertices[0]);
                MeshData::MeshVertex b = make_mesh_vertex(face_vertices[i]);
                MeshData::MeshVertex c = make_mesh_vertex(face_vertices[i + 1]);
                if (!a.has_normal || !b.has_normal || !c.has_normal) {
                    const Float3 pa = make_float3(a.position[0], a.position[1], a.position[2]);
                    const Float3 pb = make_float3(b.position[0], b.position[1], b.position[2]);
                    const Float3 pc = make_float3(c.position[0], c.position[1], c.position[2]);
                    const Float3 face_normal = normalize(cross(sub(pb, pa), sub(pc, pa)));
                    const std::array<float, 3> normal = {face_normal.x, face_normal.y, face_normal.z};
                    if (!a.has_normal) {
                        a.normal = normal;
                    }
                    if (!b.has_normal) {
                        b.normal = normal;
                    }
                    if (!c.has_normal) {
                        c.normal = normal;
                    }
                }
                mesh.vertices.push_back(a);
                mesh.vertices.push_back(b);
                mesh.vertices.push_back(c);
            }
        }
    }

    if (mesh.vertices.empty()) {
        error = "mesh has no triangle vertices: " + path.string();
        return false;
    }

    std::array<float, 3> min_v = mesh.vertices.front().position;
    std::array<float, 3> max_v = mesh.vertices.front().position;
    for (const auto& mesh_vertex : mesh.vertices) {
        for (int i = 0; i < 3; ++i) {
            min_v[i] = std::min(min_v[i], mesh_vertex.position[i]);
            max_v[i] = std::max(max_v[i], mesh_vertex.position[i]);
        }
    }

    mesh.center = {
        (min_v[0] + max_v[0]) * 0.5f,
        (min_v[1] + max_v[1]) * 0.5f,
        (min_v[2] + max_v[2]) * 0.5f
    };

    mesh.radius = 1.0f;
    for (const auto& mesh_vertex : mesh.vertices) {
        const float dx = mesh_vertex.position[0] - mesh.center[0];
        const float dy = mesh_vertex.position[1] - mesh.center[1];
        const float dz = mesh_vertex.position[2] - mesh.center[2];
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

Float4x4 build_object_rotation_matrix(const TelemetryObjectState& object) {
    const Float3x3 sim_matrix = Float3x3::from_sim_orientation(object.orientation);
    const Float3x3 viewer_matrix = sim_matrix.convert_nwu_to_viewer();
    return viewer_matrix.to_row_vector_mat4();
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
    return Float4x4::identity();
}

Float4x4 look_at_matrix(const Float3& eye, const Float3& target, const Float3& up_hint) {
    const Float3 forward = normalize(sub(target, eye));
    const Float3 right = normalize(cross(up_hint, forward));
    const Float3 up = cross(forward, right);

    Float4x4 out = Float4x4::identity();
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

std::string resolve_material_key(const TelemetryObjectState& object) {
    const auto canonical_model = canonicalize_mesh_name(object.mesh_name);
    const auto& map = model_material_map();
    const auto model_it = map.find(canonical_model);
    if (model_it != map.end()) {
        return model_it->second;
    }

    if (is_missile_object(object)) {
        return "missile_default";
    }
    if (is_aircraft_object(object)) {
        return "aircraft_default";
    }
    return "aircraft_default";
}

std::array<float, 3> team_color(const TelemetryObjectState& object) {
    if (object.team == "Blue") {
        return {0.26f, 0.72f, 1.0f};
    }
    if (object.team == "Red") {
        return {1.0f, 0.30f, 0.24f};
    }
    return {0.92f, 0.92f, 0.84f};
}

void push_vertex(
    std::vector<DX11Vertex>& vertices,
    const Float3& position,
    const std::array<float, 3>& color,
    const Float3& normal,
    const std::array<float, 2>& uv = {0.0f, 0.0f}) {
    vertices.push_back({
        {position.x, position.y, position.z},
        {color[0], color[1], color[2]},
        {normal.x, normal.y, normal.z},
        {uv[0], uv[1]}
    });
}

void push_lit_triangle(std::vector<DX11Vertex>& vertices, Float3 a, Float3 c, Float3 d, const std::array<float, 3>& color) {
    const Float3 normal = normalize(cross(sub(c, a), sub(d, a)));
    push_vertex(vertices, a, color, normal);
    push_vertex(vertices, c, color, normal);
    push_vertex(vertices, d, color, normal);
}

void append_box(std::vector<DX11Vertex>& vertices, float sx, float sy, float sz, const std::array<float, 3>& color) {
    const float hx = sx * 0.5f;
    const float hy = sy * 0.5f;
    const float hz = sz * 0.5f;
    auto push_triangle = [&](Float3 a, Float3 c, Float3 d) {
        push_lit_triangle(vertices, a, c, d, color);
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

void append_aircraft_primitive(std::vector<DX11Vertex>& vertices, const std::array<float, 3>& color) {
    auto push_triangle = [&](Float3 a, Float3 c, Float3 d) {
        push_lit_triangle(vertices, a, c, d, color);
    };

    push_triangle(make_float3(180.0f, 0.0f, 0.0f), make_float3(-120.0f, 40.0f, 90.0f), make_float3(-120.0f, 40.0f, -90.0f));
    push_triangle(make_float3(180.0f, 0.0f, 0.0f), make_float3(-120.0f, -40.0f, -90.0f), make_float3(-120.0f, -40.0f, 90.0f));

    append_box(vertices, 150.0f, 16.0f, 520.0f, color);
}

void append_missile_primitive(std::vector<DX11Vertex>& vertices, const std::array<float, 3>& color) {
    append_box(vertices, 220.0f, 24.0f, 24.0f, color);
}

void append_ground_primitive(std::vector<DX11Vertex>& vertices, const std::array<float, 3>& color) {
    append_box(vertices, 180.0f, 90.0f, 180.0f, color);
}

void append_obj_mesh(std::vector<DX11Vertex>& vertices, const MeshData& mesh, float world_radius, const std::array<float, 3>& color) {
    if (!mesh.loaded || mesh.vertices.empty() || mesh.radius <= 1e-6f) {
        return;
    }

    const float scale_value = world_radius / mesh.radius;
    for (size_t i = 0; i + 2 < mesh.vertices.size(); i += 3) {
        const auto make_position = [&](const MeshData::MeshVertex& mesh_vertex) {
            return make_float3(
                (mesh_vertex.position[0] - mesh.center[0]) * scale_value,
                (mesh_vertex.position[1] - mesh.center[1]) * scale_value,
                (mesh_vertex.position[2] - mesh.center[2]) * scale_value
            );
        };
        const auto push_mesh_vertex = [&](const MeshData::MeshVertex& source) {
            const Float3 normal = normalize(make_float3(source.normal[0], source.normal[1], source.normal[2]));
            push_vertex(vertices, make_position(source), color, normal, source.uv);
        };
        push_mesh_vertex(mesh.vertices[i]);
        push_mesh_vertex(mesh.vertices[i + 1]);
        push_mesh_vertex(mesh.vertices[i + 2]);
    }
}

void append_ground_plane(std::vector<DX11Vertex>& vertices, float size) {
    constexpr int kSubdivisions = 28;
    const std::array<float, 3> lowland = {0.17f, 0.24f, 0.17f};
    const std::array<float, 3> highland = {0.28f, 0.31f, 0.22f};
    const Float3 normal = make_float3(0.0f, 1.0f, 0.0f);

    auto color_at = [&](float x, float z) {
        const float band = std::sin(x * 0.00012f + z * 0.00019f) * 0.5f + 0.5f;
        std::array<float, 3> color{};
        for (int i = 0; i < 3; ++i) {
            color[i] = lowland[i] * (1.0f - band) + highland[i] * band;
        }
        return color;
    };

    auto push_ground_vertex = [&](float x, float z) {
        const float u = (x + size) / 18000.0f;
        const float v = (z + size) / 18000.0f;
        push_vertex(vertices, make_float3(x, 0.0f, z), color_at(x, z), normal, {u, v});
    };

    for (int z = 0; z < kSubdivisions; ++z) {
        const float z0 = -size + 2.0f * size * static_cast<float>(z) / static_cast<float>(kSubdivisions);
        const float z1 = -size + 2.0f * size * static_cast<float>(z + 1) / static_cast<float>(kSubdivisions);
        for (int x = 0; x < kSubdivisions; ++x) {
            const float x0 = -size + 2.0f * size * static_cast<float>(x) / static_cast<float>(kSubdivisions);
            const float x1 = -size + 2.0f * size * static_cast<float>(x + 1) / static_cast<float>(kSubdivisions);
            push_ground_vertex(x0, z0);
            push_ground_vertex(x1, z1);
            push_ground_vertex(x1, z0);
            push_ground_vertex(x0, z0);
            push_ground_vertex(x0, z1);
            push_ground_vertex(x1, z1);
        }
    }
}

void append_sky_quad(std::vector<DX11Vertex>& vertices) {
    const std::array<float, 3> top = {0.20f, 0.39f, 0.62f};
    const std::array<float, 3> horizon = {0.77f, 0.83f, 0.88f};

    auto push_sky_vertex = [&](float x, float y, const std::array<float, 3>& color) {
        push_vertex(vertices, make_float3(x, y, 0.0f), color, make_float3(0.0f, 0.0f, -1.0f));
    };

    push_sky_vertex(-1.0f, 1.0f, top);
    push_sky_vertex(1.0f, 1.0f, top);
    push_sky_vertex(1.0f, -1.0f, horizon);

    push_sky_vertex(-1.0f, 1.0f, top);
    push_sky_vertex(1.0f, -1.0f, horizon);
    push_sky_vertex(-1.0f, -1.0f, horizon);
}

void append_grid(std::vector<DX11Vertex>& vertices, float size, int half_count) {
    const float r = 0.24f;
    const float g = 0.29f;
    const float b = 0.25f;
    for (int i = -half_count; i <= half_count; ++i) {
        const float value = size * static_cast<float>(i) / static_cast<float>(half_count);
        const std::array<float, 3> color = {r, g, b};
        const Float3 normal = make_float3(0.0f, 1.0f, 0.0f);
        push_vertex(vertices, make_float3(value, 0.0f, -size), color, normal);
        push_vertex(vertices, make_float3(value, 0.0f, size), color, normal);
        push_vertex(vertices, make_float3(-size, 0.0f, value), color, normal);
        push_vertex(vertices, make_float3(size, 0.0f, value), color, normal);
    }
}

Float4x4 build_object_world_matrix(const TelemetryObjectState& object) {
    const float scale_value = object_world_radius(object) / 180.0f;
    const Float4x4 scale_m = Float4x4::scale(scale_value, scale_value, scale_value);
    const Float4x4 model_offset = Float4x4::rotation_y(static_cast<float>(c3utils::deg2rad(270.0)));
    const Float4x4 rotation_m = build_object_rotation_matrix(object);
    const Float4x4 translation_m = Float4x4::translation(
        static_cast<float>(object.position[0]),
        static_cast<float>(object.position[2]),
        static_cast<float>(object.position[1])
    );
    return scale_m * model_offset * rotation_m * translation_m;
}

Float4x4 build_shadow_world_matrix(const TelemetryObjectState& object) {
    static const std::array<float, 4> shadow_plane = {0.0f, 1.0f, 0.0f, 0.0f};
    static const std::array<float, 4> shadow_light = {16000.0f, 24000.0f, 12000.0f, 1.0f};
    static const Float4x4 shadow_projection = Float4x4::shadow_projection(shadow_plane, shadow_light);
    const Float4x4 lift_translation = Float4x4::translation(
        static_cast<float>(object.position[0]),
        static_cast<float>(object.position[2]) + 2.0f,
        static_cast<float>(object.position[1])
    );
    return build_object_world_matrix(object) * lift_translation * shadow_projection;
}

void create_object_geometry(const TelemetryObjectState& object, std::vector<DX11Vertex>& vertices) {
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
    ViewerInputState resolved_input = input;
    bool use_aircraft_view = false;
    Float3 aircraft_eye{};
    Float3 aircraft_target{};
    Float3 aircraft_up{};

    if (resolved_input.camera_mode == ViewerInputState::CameraMode::FollowObject && snapshot && !resolved_input.focus_uid.empty()) {
        for (const auto& object : snapshot->objects) {
            if (object.uid == resolved_input.focus_uid) {
                const Float3 object_position = make_float3(
                    static_cast<float>(object.position[0]),
                    static_cast<float>(object.position[2]),
                    static_cast<float>(object.position[1])
                );
                if (resolved_input.input_mode == ViewerInputState::InputMode::Control) {
                    aircraft_target = object_position;
                    aircraft_eye = add(
                        aircraft_target,
                        make_float3(
                            std::cos(resolved_input.camera_pitch) * std::cos(resolved_input.camera_yaw) * resolved_input.camera_distance,
                            std::sin(resolved_input.camera_pitch) * resolved_input.camera_distance,
                            std::cos(resolved_input.camera_pitch) * std::sin(resolved_input.camera_yaw) * resolved_input.camera_distance
                        )
                    );
                    aircraft_up = make_float3(0.0f, 1.0f, 0.0f);
                    use_aircraft_view = true;
                    break;
                }

                const Float3x3 orientation = Float3x3::from_sim_orientation(object.orientation).convert_nwu_to_viewer();
                const Float3 forward = normalize(make_float3(orientation.m[0][0], orientation.m[1][0], orientation.m[2][0]));
                const Float3 up = resolved_input.camera_roll_locked
                    ? make_float3(0.0f, 1.0f, 0.0f)
                    : normalize(make_float3(orientation.m[0][1], orientation.m[1][1], orientation.m[2][1]));
                const float follow_distance = std::max(1000.0f, resolved_input.camera_distance);
                const Float3 world_camera_offset = add(
                    scale(forward, -follow_distance),
                    scale(up, follow_distance * 0.28f)
                );
                aircraft_eye = add(object_position, world_camera_offset);
                aircraft_target = add(aircraft_eye, scale(forward, std::max(10000.0f, follow_distance)));
                aircraft_up = up;
                use_aircraft_view = true;
                break;
            }
        }
    }

    const float aspect = static_cast<float>(width) / static_cast<float>(std::max(1U, height));
    Float3 eye{};
    Float3 target{};
    Float3 up = make_float3(0.0f, 1.0f, 0.0f);
    if (use_aircraft_view) {
        eye = aircraft_eye;
        target = aircraft_target;
        up = aircraft_up;
    } else {
        target = resolved_input.camera_target;
        eye = add(
            target,
            make_float3(
                std::cos(resolved_input.camera_pitch) * std::cos(resolved_input.camera_yaw) * resolved_input.camera_distance,
                std::sin(resolved_input.camera_pitch) * resolved_input.camera_distance,
                std::cos(resolved_input.camera_pitch) * std::sin(resolved_input.camera_yaw) * resolved_input.camera_distance
            )
        );
    }

    scene.view = look_at_matrix(eye, target, up);
    scene.projection = perspective_matrix(static_cast<float>(c3utils::deg2rad(resolved_input.camera_fov_y)), aspect, 10.0f, 500000.0f);
    scene.clip_space = orthographic_identity_clip_matrix();
    scene.camera_position = eye;

    append_sky_quad(scene.sky_vertices);
    append_ground_plane(scene.ground_vertices, 140000.0f);
    append_grid(scene.grid_vertices, 120000.0f, 18);

    if (!snapshot) {
        return scene;
    }

    if (resolved_input.shadows_enabled) {
        scene.shadow_batches.reserve(snapshot->objects.size());
    }
    scene.object_batches.reserve(snapshot->objects.size());
    for (const auto& object : snapshot->objects) {
        if (!object.alive) {
            continue;
        }

        if (resolved_input.shadows_enabled) {
            RenderScene::ObjectBatch shadow_batch;
            create_object_geometry(object, shadow_batch.vertices);
            for (auto& vertex : shadow_batch.vertices) {
                vertex.color[0] = 0.0f;
                vertex.color[1] = 0.0f;
                vertex.color[2] = 0.0f;
                vertex.uv[0] = 0.0f;
                vertex.uv[1] = 0.0f;
            }
            shadow_batch.world = build_shadow_world_matrix(object);
            shadow_batch.material_key = "sky";
            shadow_batch.use_material_system = false;
            scene.shadow_batches.push_back(std::move(shadow_batch));
        }

        RenderScene::ObjectBatch batch;
        create_object_geometry(object, batch.vertices);
        batch.world = build_object_world_matrix(object);
        batch.material_key = resolved_input.material_system_enabled ? resolve_material_key(object) : "aircraft_default";
        batch.use_material_system = resolved_input.material_system_enabled;
        scene.object_batches.push_back(std::move(batch));
    }

    return scene;
}

#endif

} // namespace bvr_sim






