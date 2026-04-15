#include "opengl_viewer.hxx"

#include "c3utils/c3utils.hxx"
#include "resource_paths.hxx"
#include "rubbish_can/SL.hxx"

#include <algorithm>
#include <array>
#include <chrono>
#include <cmath>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <GL/gl.h>
#pragma comment(lib, "opengl32.lib")
#endif

namespace bvr_sim {

OpenGLViewer::OpenGLViewer()
    : running_(false),
      stop_requested_(false),
      supported_(false) {
#ifdef _WIN32
    supported_ = true;
#else
    supported_ = false;
#endif
}

OpenGLViewer::~OpenGLViewer() {
    stop();
}

void OpenGLViewer::set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> provider) {
    snapshot_provider_ = std::move(provider);
}

void OpenGLViewer::set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) {
    command_submitter_ = std::move(submitter);
}

void OpenGLViewer::start() {
    if (running_.load()) {
        return;
    }

    stop_requested_ = false;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }
    viewer_thread_ = std::thread(&OpenGLViewer::run_loop, this);
}

void OpenGLViewer::stop() noexcept {
    stop_requested_ = true;
    if (viewer_thread_.joinable()) {
        viewer_thread_.join();
    }
    running_ = false;
}

bool OpenGLViewer::is_running() const noexcept {
    return running_.load();
}

bool OpenGLViewer::is_supported() const noexcept {
    return supported_.load();
}

json::JSON OpenGLViewer::get_status() const {
    json::JSON status = json::JSON::Make(json::JSON::Class::Object);
    status["running"] = json::Boolean(is_running());
    status["supported"] = json::Boolean(is_supported());
#ifdef _WIN32
    status["platform"] = json::String("windows");
    status["backend"] = json::String("win32_wgl");
#else
    status["platform"] = json::String("linux_or_other");
    status["backend"] = json::String("stub");
#endif

    std::lock_guard<std::mutex> lock(state_mutex_);
    status["last_error"] = json::String(last_error_);
    status["focus_uid"] = json::String(focus_uid_);
    status["last_sim_time"] = json::Float(last_sim_time_);
    status["last_object_count"] = json::Integral(last_object_count_);
    return status;
}

void OpenGLViewer::submit_command(const TelemetryCommand& command) const {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

#ifndef _WIN32

void OpenGLViewer::run_loop() noexcept {
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = "OpenGL viewer is currently implemented for Windows only";
        focus_uid_.clear();
        last_sim_time_ = 0.0;
        last_object_count_ = 0;
    }
    running_ = false;
}

#else

namespace {

using c3u::deg2rad;
using c3u::rad2deg;

struct ViewerState {
    enum class CameraMode {
        Free,
        FollowObject,
    };

    HINSTANCE instance = nullptr;
    HWND hwnd = nullptr;
    HDC dc = nullptr;
    HGLRC rc = nullptr;
    OpenGLViewer* owner = nullptr;
    bool should_close = false;
    bool paused = false;
    CameraMode camera_mode = CameraMode::Free;
    float camera_yaw = 0.65f;
    float camera_pitch = 0.55f;
    float camera_distance = 22000.0f;
    float camera_fov_y = 50.0f;
    float camera_target_x = 0.0f;
    float camera_target_y = 0.0f;
    float camera_target_z = 0.0f;
    bool move_forward = false;
    bool move_backward = false;
    bool move_left = false;
    bool move_right = false;
    bool move_up = false;
    bool move_down = false;
    bool mouse_in_window = false;
    bool has_mouse_reference = false;
    int last_mouse_x = 0;
    int last_mouse_y = 0;
    GLuint font_base = 0;
    double render_fps = 0.0;
    int fps_frame_counter = 0;
    std::chrono::steady_clock::time_point fps_window_start = std::chrono::steady_clock::now();
    std::string selected_uid;
    std::string focus_uid;
    std::vector<std::string> snapshot_uids;
};

struct MeshData {
    std::vector<std::array<float, 3>> vertices;
    std::array<float, 3> center{0.0f, 0.0f, 0.0f};
    float radius = 1.0f;
    bool loaded = false;
};

struct MeshLibrary {
    std::unordered_map<std::string, MeshData> meshes;
};

struct ModelOffset {
    float yaw_deg = 0.0f;
    float pitch_deg = 0.0f;
    float roll_deg = 0.0f;
};

MeshLibrary& mesh_library() {
    static MeshLibrary library;
    return library;
}

std::string canonicalize_mesh_name(std::string mesh_name) {
    std::replace(mesh_name.begin(), mesh_name.end(), '_', '-');
    return mesh_name;
}

std::string map_model_to_mesh_name(const std::string& model_name) {
    static const std::unordered_map<std::string, std::string> kModelMeshMap = {
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
    const auto it = kModelMeshMap.find(canonical_model);
    if (it != kModelMeshMap.end()) {
        return it->second;
    }
    return "";
}

ViewerState* get_viewer_state(HWND hwnd) {
    return reinterpret_cast<ViewerState*>(GetWindowLongPtr(hwnd, GWLP_USERDATA));
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

void perspective_gl(double fov_y_degrees, double aspect, double z_near, double z_far) {
    const double fH = std::tan(deg2rad(fov_y_degrees) * 0.5) * z_near;
    const double fW = fH * aspect;
    glFrustum(-fW, fW, -fH, fH, z_near, z_far);
}

void normalize(float& x, float& y, float& z) {
    const float length = std::sqrt(x * x + y * y + z * z);
    if (length <= 1e-6f) {
        return;
    }
    x /= length;
    y /= length;
    z /= length;
}

void cross(
    float ax, float ay, float az,
    float bx, float by, float bz,
    float& rx, float& ry, float& rz) {
    rx = ay * bz - az * by;
    ry = az * bx - ax * bz;
    rz = ax * by - ay * bx;
}

void look_at_gl(
    float eye_x, float eye_y, float eye_z,
    float center_x, float center_y, float center_z,
    float up_x, float up_y, float up_z) {
    float fx = center_x - eye_x;
    float fy = center_y - eye_y;
    float fz = center_z - eye_z;
    normalize(fx, fy, fz);

    normalize(up_x, up_y, up_z);

    float sx = 0.0f;
    float sy = 0.0f;
    float sz = 0.0f;
    cross(fx, fy, fz, up_x, up_y, up_z, sx, sy, sz);
    normalize(sx, sy, sz);

    float ux = 0.0f;
    float uy = 0.0f;
    float uz = 0.0f;
    cross(sx, sy, sz, fx, fy, fz, ux, uy, uz);

    const GLfloat matrix[16] = {
        sx, ux, -fx, 0.0f,
        sy, uy, -fy, 0.0f,
        sz, uz, -fz, 0.0f,
        0.0f, 0.0f, 0.0f, 1.0f
    };
    glMultMatrixf(matrix);
    glTranslatef(-eye_x, -eye_y, -eye_z);
}

void draw_ground_plane(float size) {
    glDisable(GL_LIGHTING);

    glBegin(GL_QUADS);
    glColor3f(0.11f, 0.15f, 0.11f);
    glVertex3f(-size, -4.0f, -size);
    glVertex3f(size, -4.0f, -size);
    glColor3f(0.15f, 0.20f, 0.14f);
    glVertex3f(size, -4.0f, size);
    glVertex3f(-size, -4.0f, size);
    glEnd();
}

void draw_ground_pattern(float size, float cell_size) {
    if (cell_size <= 1.0f) {
        return;
    }

    const int cell_count = static_cast<int>(std::ceil((size * 2.0f) / cell_size));
    const float start = -0.5f * static_cast<float>(cell_count) * cell_size;

    glBegin(GL_QUADS);
    for (int ix = 0; ix < cell_count; ++ix) {
        for (int iz = 0; iz < cell_count; ++iz) {
            const float x0 = start + static_cast<float>(ix) * cell_size;
            const float x1 = x0 + cell_size;
            const float z0 = start + static_cast<float>(iz) * cell_size;
            const float z1 = z0 + cell_size;
            const bool even = ((ix + iz) % 2) == 0;
            if (even) {
                glColor4f(0.20f, 0.25f, 0.18f, 0.16f);
            } else {
                glColor4f(0.13f, 0.18f, 0.13f, 0.11f);
            }
            glVertex3f(x0, -3.9f, z0);
            glVertex3f(x1, -3.9f, z0);
            glVertex3f(x1, -3.9f, z1);
            glVertex3f(x0, -3.9f, z1);
        }
    }
    glEnd();
}

void draw_grid(float size, int half_count) {
    draw_ground_plane(size);

    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    draw_ground_pattern(size, 4000.0f);

    glLineWidth(1.0f);
    glColor4f(0.22f, 0.30f, 0.24f, 0.35f);
    glBegin(GL_LINES);
    for (int i = -half_count * 4; i <= half_count * 4; ++i) {
        const float value = size * static_cast<float>(i) / static_cast<float>(half_count * 4);
        glVertex3f(value, -3.7f, -size);
        glVertex3f(value, -3.7f, size);
        glVertex3f(-size, -3.7f, value);
        glVertex3f(size, -3.7f, value);
    }
    glEnd();

    glLineWidth(1.6f);
    glColor4f(0.34f, 0.44f, 0.36f, 0.62f);
    glBegin(GL_LINES);
    for (int i = -half_count; i <= half_count; ++i) {
        const float value = size * static_cast<float>(i) / static_cast<float>(half_count);
        glVertex3f(value, -3.6f, -size);
        glVertex3f(value, -3.6f, size);
        glVertex3f(-size, -3.6f, value);
        glVertex3f(size, -3.6f, value);
    }
    glEnd();

    glLineWidth(2.4f);
    glColor4f(0.58f, 0.66f, 0.56f, 0.85f);
    glBegin(GL_LINES);
    glVertex3f(0.0f, -3.5f, -size);
    glVertex3f(0.0f, -3.5f, size);
    glVertex3f(-size, -3.5f, 0.0f);
    glVertex3f(size, -3.5f, 0.0f);
    glEnd();

    glDisable(GL_BLEND);
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
                int vertex_index = obj_index > 0 ? obj_index - 1 : static_cast<int>(positions.size()) + obj_index;
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
            SL::get().printf("[OpenGLViewer] failed to load mesh %s: %s\n", canonical_name.c_str(), error.c_str());
            return nullptr;
        }
        auto [inserted_it, _] = library.meshes.emplace(canonical_name, std::move(mesh));
        return &inserted_it->second;
    } catch (const std::exception& ex) {
        SL::get().printf("[OpenGLViewer] mesh resource lookup failed for %s: %s\n", canonical_name.c_str(), ex.what());
        return nullptr;
    }
}

std::array<float, 3> compute_face_normal(
    const std::array<float, 3>& a,
    const std::array<float, 3>& b,
    const std::array<float, 3>& c) {
    const float ux = b[0] - a[0];
    const float uy = b[1] - a[1];
    const float uz = b[2] - a[2];
    const float vx = c[0] - a[0];
    const float vy = c[1] - a[1];
    const float vz = c[2] - a[2];
    float nx = uy * vz - uz * vy;
    float ny = uz * vx - ux * vz;
    float nz = ux * vy - uy * vx;
    normalize(nx, ny, nz);
    return {nx, ny, nz};
}

void draw_obj_mesh(const MeshData& mesh, float world_radius) {
    if (!mesh.loaded || mesh.vertices.empty() || mesh.radius <= 1e-6f) {
        return;
    }

    const float scale = world_radius / mesh.radius;
    glPushMatrix();
    glScalef(scale, scale, scale);
    glTranslatef(-mesh.center[0], -mesh.center[1], -mesh.center[2]);

    glBegin(GL_TRIANGLES);
    for (size_t i = 0; i + 2 < mesh.vertices.size(); i += 3) {
        const auto normal = compute_face_normal(mesh.vertices[i], mesh.vertices[i + 1], mesh.vertices[i + 2]);
        glNormal3f(normal[0], normal[1], normal[2]);
        glVertex3f(mesh.vertices[i][0], mesh.vertices[i][1], mesh.vertices[i][2]);
        glVertex3f(mesh.vertices[i + 1][0], mesh.vertices[i + 1][1], mesh.vertices[i + 1][2]);
        glVertex3f(mesh.vertices[i + 2][0], mesh.vertices[i + 2][1], mesh.vertices[i + 2][2]);
    }
    glEnd();
    glPopMatrix();
}

void draw_obj_mesh_unlit(const MeshData& mesh, float world_radius) {
    if (!mesh.loaded || mesh.vertices.empty() || mesh.radius <= 1e-6f) {
        return;
    }

    const float scale = world_radius / mesh.radius;
    glPushMatrix();
    glScalef(scale, scale, scale);
    glTranslatef(-mesh.center[0], -mesh.center[1], -mesh.center[2]);

    glBegin(GL_TRIANGLES);
    for (const auto& vertex : mesh.vertices) {
        glVertex3f(vertex[0], vertex[1], vertex[2]);
    }
    glEnd();
    glPopMatrix();
}

void draw_box(float sx, float sy, float sz) {
    const float hx = sx * 0.5f;
    const float hy = sy * 0.5f;
    const float hz = sz * 0.5f;
    glBegin(GL_QUADS);
    glNormal3f(0.0f, 0.0f, 1.0f);
    glVertex3f(-hx, -hy, hz); glVertex3f(hx, -hy, hz); glVertex3f(hx, hy, hz); glVertex3f(-hx, hy, hz);
    glNormal3f(0.0f, 0.0f, -1.0f);
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, hy, -hz); glVertex3f(hx, hy, -hz); glVertex3f(hx, -hy, -hz);
    glNormal3f(-1.0f, 0.0f, 0.0f);
    glVertex3f(-hx, -hy, -hz); glVertex3f(-hx, -hy, hz); glVertex3f(-hx, hy, hz); glVertex3f(-hx, hy, -hz);
    glNormal3f(1.0f, 0.0f, 0.0f);
    glVertex3f(hx, -hy, -hz); glVertex3f(hx, hy, -hz); glVertex3f(hx, hy, hz); glVertex3f(hx, -hy, hz);
    glNormal3f(0.0f, 1.0f, 0.0f);
    glVertex3f(-hx, hy, -hz); glVertex3f(-hx, hy, hz); glVertex3f(hx, hy, hz); glVertex3f(hx, hy, -hz);
    glNormal3f(0.0f, -1.0f, 0.0f);
    glVertex3f(-hx, -hy, -hz); glVertex3f(hx, -hy, -hz); glVertex3f(hx, -hy, hz); glVertex3f(-hx, -hy, hz);
    glEnd();
}

void set_object_material(const std::array<float, 3>& color, float alpha_scale) {
    const GLfloat specular[] = {0.55f, 0.55f, 0.55f, 1.0f};
    const GLfloat shininess[] = {36.0f};
    glColor4f(color[0] * alpha_scale, color[1] * alpha_scale, color[2] * alpha_scale, alpha_scale);
    glMaterialfv(GL_FRONT_AND_BACK, GL_SPECULAR, specular);
    glMaterialfv(GL_FRONT_AND_BACK, GL_SHININESS, shininess);
}

std::array<float, 16> build_shadow_matrix(
    const std::array<float, 4>& plane,
    const std::array<float, 4>& light) {
    std::array<float, 16> matrix{};
    const float dot = plane[0] * light[0] + plane[1] * light[1] + plane[2] * light[2] + plane[3] * light[3];

    matrix[0] = dot - light[0] * plane[0];
    matrix[4] = -light[0] * plane[1];
    matrix[8] = -light[0] * plane[2];
    matrix[12] = -light[0] * plane[3];

    matrix[1] = -light[1] * plane[0];
    matrix[5] = dot - light[1] * plane[1];
    matrix[9] = -light[1] * plane[2];
    matrix[13] = -light[1] * plane[3];

    matrix[2] = -light[2] * plane[0];
    matrix[6] = -light[2] * plane[1];
    matrix[10] = dot - light[2] * plane[2];
    matrix[14] = -light[2] * plane[3];

    matrix[3] = -light[3] * plane[0];
    matrix[7] = -light[3] * plane[1];
    matrix[11] = -light[3] * plane[2];
    matrix[15] = dot - light[3] * plane[3];
    return matrix;
}

void configure_scene_lighting() {
    glEnable(GL_LIGHTING);
    glEnable(GL_LIGHT0);
    glEnable(GL_COLOR_MATERIAL);
    glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE);
    glEnable(GL_NORMALIZE);

    const GLfloat ambient[] = {0.20f, 0.22f, 0.26f, 1.0f};
    const GLfloat diffuse[] = {0.95f, 0.92f, 0.84f, 1.0f};
    const GLfloat specular[] = {0.75f, 0.75f, 0.75f, 1.0f};
    const GLfloat position[] = {16000.0f, 24000.0f, 12000.0f, 1.0f};
    const GLfloat global_ambient[] = {0.08f, 0.09f, 0.11f, 1.0f};

    glLightModelfv(GL_LIGHT_MODEL_AMBIENT, global_ambient);
    glLightfv(GL_LIGHT0, GL_AMBIENT, ambient);
    glLightfv(GL_LIGHT0, GL_DIFFUSE, diffuse);
    glLightfv(GL_LIGHT0, GL_SPECULAR, specular);
    glLightfv(GL_LIGHT0, GL_POSITION, position);
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

ModelOffset get_model_offset(const TelemetryObjectState&) {
    ModelOffset offset;
    // Tacview OBJ assets are authored with +Y as up and +Z as left,
    // but nose points opposite the viewer's local +X forward axis.
    offset.yaw_deg = 270.0f;
    return offset;
}

void apply_model_offset(const ModelOffset& offset) {
    if (std::fabs(offset.yaw_deg) > 1e-4f) {
        glRotatef(offset.yaw_deg, 0.0f, 1.0f, 0.0f);
    }
    if (std::fabs(offset.pitch_deg) > 1e-4f) {
        glRotatef(offset.pitch_deg, 0.0f, 0.0f, 1.0f);
    }
    if (std::fabs(offset.roll_deg) > 1e-4f) {
        glRotatef(offset.roll_deg, 1.0f, 0.0f, 0.0f);
    }
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

void draw_aircraft_primitive() {

    glBegin(GL_TRIANGLES);
    glVertex3f(180.0f, 0.0f, 0.0f);
    glVertex3f(-120.0f, 40.0f, 90.0f);
    glVertex3f(-120.0f, 40.0f, -90.0f);

    glVertex3f(180.0f, 0.0f, 0.0f);
    glVertex3f(-120.0f, -40.0f, -90.0f);
    glVertex3f(-120.0f, -40.0f, 90.0f);
    glEnd();

    glBegin(GL_QUADS);
    glVertex3f(-10.0f, 0.0f, -260.0f);
    glVertex3f(70.0f, 0.0f, -30.0f);
    glVertex3f(-40.0f, 0.0f, 30.0f);
    glVertex3f(-110.0f, 0.0f, -180.0f);

    glVertex3f(-10.0f, 0.0f, 260.0f);
    glVertex3f(-110.0f, 0.0f, 180.0f);
    glVertex3f(-40.0f, 0.0f, -30.0f);
    glVertex3f(70.0f, 0.0f, 30.0f);
    glEnd();
}

void draw_missile_primitive() {
    draw_box(220.0f, 24.0f, 24.0f);
    glBegin(GL_TRIANGLES);
    glVertex3f(-20.0f, 0.0f, 0.0f);
    glVertex3f(-90.0f, 0.0f, 70.0f);
    glVertex3f(-90.0f, 0.0f, -70.0f);
    glEnd();
}

void draw_ground_unit() {
    draw_box(180.0f, 90.0f, 180.0f);
}

void draw_object_geometry(const TelemetryObjectState& object, bool unlit) {
    const std::string mesh_asset = resolve_mesh_asset_name(object);
    if (!mesh_asset.empty()) {
        if (MeshData* mesh = load_named_mesh(mesh_asset)) {
            glPushMatrix();
            apply_model_offset(get_model_offset(object));
            if (unlit) {
                draw_obj_mesh_unlit(*mesh, object_world_radius(object));
            } else {
                draw_obj_mesh(*mesh, object_world_radius(object));
            }
            glPopMatrix();
            return;
        }
    }

    if (is_aircraft_object(object)) {
        draw_aircraft_primitive();
        return;
    }
    if (is_missile_object(object)) {
        draw_missile_primitive();
        return;
    }
    draw_ground_unit();
}

void draw_local_axes_marker(float axis_length) {
    glLineWidth(3.0f);
    glBegin(GL_LINES);
    glColor3f(1.0f, 0.22f, 0.22f);
    glVertex3f(0.0f, 0.0f, 0.0f);
    glVertex3f(axis_length, 0.0f, 0.0f);

    glColor3f(0.25f, 1.0f, 0.25f);
    glVertex3f(0.0f, 0.0f, 0.0f);
    glVertex3f(0.0f, axis_length, 0.0f);

    glColor3f(0.3f, 0.65f, 1.0f);
    glVertex3f(0.0f, 0.0f, 0.0f);
    glVertex3f(0.0f, 0.0f, axis_length);
    glEnd();

    glBegin(GL_LINES);
    glColor3f(1.0f, 0.22f, 0.22f);
    glVertex3f(axis_length, 0.0f, 0.0f);
    glVertex3f(axis_length - 45.0f, 18.0f, 0.0f);
    glVertex3f(axis_length, 0.0f, 0.0f);
    glVertex3f(axis_length - 45.0f, -18.0f, 0.0f);

    glColor3f(0.25f, 1.0f, 0.25f);
    glVertex3f(0.0f, axis_length, 0.0f);
    glVertex3f(18.0f, axis_length - 45.0f, 0.0f);
    glVertex3f(0.0f, axis_length, 0.0f);
    glVertex3f(-18.0f, axis_length - 45.0f, 0.0f);

    glColor3f(0.3f, 0.65f, 1.0f);
    glVertex3f(0.0f, 0.0f, axis_length);
    glVertex3f(0.0f, 18.0f, axis_length - 45.0f);
    glVertex3f(0.0f, 0.0f, axis_length);
    glVertex3f(0.0f, -18.0f, axis_length - 45.0f);
    glEnd();
    glLineWidth(1.0f);
}

bool initialize_font_display_lists(ViewerState& state) {
    state.font_base = glGenLists(96);
    if (state.font_base == 0) {
        return false;
    }

    HFONT font = CreateFontA(
        -16,
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
        "Consolas");
    if (!font) {
        return false;
    }

    HGDIOBJ previous = SelectObject(state.dc, font);
    const BOOL ok = wglUseFontBitmapsA(state.dc, 32, 96, state.font_base);
    SelectObject(state.dc, previous);
    DeleteObject(font);
    return ok == TRUE;
}

void destroy_font_display_lists(ViewerState& state) {
    if (state.font_base != 0) {
        glDeleteLists(state.font_base, 96);
        state.font_base = 0;
    }
}

void render_text_2d(const ViewerState& state, int x, int y, const std::string& text) {
    if (state.font_base == 0 || text.empty()) {
        return;
    }
    glRasterPos2i(x, y);
    glListBase(state.font_base - 32);
    glCallLists(static_cast<GLsizei>(text.size()), GL_UNSIGNED_BYTE, text.c_str());
}

void begin_2d_overlay(int width, int height) {
    glMatrixMode(GL_PROJECTION);
    glPushMatrix();
    glLoadIdentity();
    glOrtho(0.0, static_cast<double>(width), static_cast<double>(height), 0.0, -1.0, 1.0);

    glMatrixMode(GL_MODELVIEW);
    glPushMatrix();
    glLoadIdentity();

    glDisable(GL_DEPTH_TEST);
}

void end_2d_overlay() {
    glEnable(GL_DEPTH_TEST);

    glMatrixMode(GL_MODELVIEW);
    glPopMatrix();

    glMatrixMode(GL_PROJECTION);
    glPopMatrix();
}

std::string format_vec3(float x, float y, float z) {
    std::ostringstream oss;
    oss << std::fixed << std::setprecision(0) << "(" << x << ", " << y << ", " << z << ")";
    return oss.str();
}

std::string shorten_text(const std::string& text, size_t max_length) {
    if (text.size() <= max_length) {
        return text;
    }
    if (max_length <= 3) {
        return text.substr(0, max_length);
    }
    return text.substr(0, max_length - 3) + "...";
}

std::string resolve_mesh_file_name(const TelemetryObjectState& object) {
    const std::string mesh_asset = resolve_mesh_asset_name(object);
    if (!mesh_asset.empty()) {
        return mesh_asset + ".obj";
    }
    return "<builtin>";
}

void render_hud(
    const ViewerState& view_state,
    int width,
    int height,
    float eye_x,
    float eye_y,
    float eye_z,
    const std::shared_ptr<const WorldSnapshot>& snapshot) {
    begin_2d_overlay(width, height);
    glColor3f(0.88f, 0.94f, 0.98f);

    const double sim_time = snapshot ? snapshot->sim_time : 0.0;
    const long object_count = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;

    std::ostringstream line1;
    line1 << std::fixed << std::setprecision(1)
          << "RenderFPS " << view_state.render_fps
          << "  "
          << "FOV " << view_state.camera_fov_y
          << "  Dist " << view_state.camera_distance
          << "  Pitch " << rad2deg(view_state.camera_pitch)
          << "  Yaw " << rad2deg(view_state.camera_yaw);
    render_text_2d(view_state, 14, 24, line1.str());

    std::ostringstream line2;
    line2 << std::fixed << std::setprecision(2)
          << "SimTime " << sim_time
          << "  Objects " << object_count
          << "  Mode " << (view_state.camera_mode == ViewerState::CameraMode::Free ? "free" : "follow")
          << "  Focus " << (view_state.focus_uid.empty() ? "<none>" : view_state.focus_uid);
    render_text_2d(view_state, 14, 46, line2.str());

    std::ostringstream line3;
    line3 << std::fixed << std::setprecision(0)
          << "Camera " << format_vec3(eye_x, eye_y, eye_z)
          << "  Target " << format_vec3(view_state.camera_target_x, view_state.camera_target_y, view_state.camera_target_z);
    render_text_2d(view_state, 14, 68, line3.str());

    render_text_2d(view_state, 14, height - 74, "Move: W A S D  Vertical: Q/E  Look: mouse in window");
    render_text_2d(view_state, 14, height - 52, "View: arrows pitch/yaw  FOV: +/-  Pause: Space  Step: N  F1 free  F2 follow/next");

    const int panel_x = std::max(420, width - 620);
    render_text_2d(view_state, panel_x, 24, "UID                  Model         Mesh File                 Roll   Pitch    Yaw");

    int row = 0;
    const int row_height = 18;
    const int max_rows = std::max(0, (height - 90) / row_height);
    for (const auto& object : snapshot ? snapshot->objects : std::vector<TelemetryObjectState>{}) {
        if (row >= max_rows) {
            break;
        }

        const double roll_deg = rad2deg(object.orientation[0]);
        const double pitch_deg = rad2deg(object.orientation[1]);
        const double yaw_deg = rad2deg(object.orientation[2]);
        const std::string model_name = object.mesh_name.empty() ? object.type : object.mesh_name;
        const std::string mesh_file_name = resolve_mesh_file_name(object);

        std::ostringstream item_line;
        item_line << std::left << std::setw(21) << shorten_text(object.uid, 21)
                  << std::setw(14) << shorten_text(model_name, 14)
                  << std::setw(26) << shorten_text(mesh_file_name, 26)
                  << std::right << std::setw(7) << std::fixed << std::setprecision(1) << roll_deg
                  << std::setw(8) << pitch_deg
                  << std::setw(8) << yaw_deg;
        render_text_2d(view_state, panel_x, 44 + row * row_height, item_line.str());
        ++row;
    }

    end_2d_overlay();
}

void cycle_follow_target(ViewerState& state) {
    if (state.snapshot_uids.empty()) {
        state.camera_mode = ViewerState::CameraMode::FollowObject;
        state.focus_uid.clear();
        return;
    }

    state.camera_mode = ViewerState::CameraMode::FollowObject;
    if (state.focus_uid.empty()) {
        state.focus_uid = state.snapshot_uids.front();
        return;
    }

    auto current = std::find(state.snapshot_uids.begin(), state.snapshot_uids.end(), state.focus_uid);
    if (current == state.snapshot_uids.end() || ++current == state.snapshot_uids.end()) {
        state.focus_uid = state.snapshot_uids.front();
        return;
    }
    state.focus_uid = *current;
}

LRESULT CALLBACK viewer_window_proc(HWND hwnd, UINT msg, WPARAM w_param, LPARAM l_param) {
    ViewerState* state = get_viewer_state(hwnd);
    switch (msg) {
    case WM_CLOSE:
        if (state) {
            state->should_close = true;
        }
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    case WM_MOUSEMOVE:
        if (state) {
            const int mouse_x = GET_X_LPARAM(l_param);
            const int mouse_y = GET_Y_LPARAM(l_param);

            if (!state->mouse_in_window) {
                TRACKMOUSEEVENT tme = {};
                tme.cbSize = sizeof(TRACKMOUSEEVENT);
                tme.dwFlags = TME_LEAVE;
                tme.hwndTrack = hwnd;
                TrackMouseEvent(&tme);
                state->mouse_in_window = true;
                state->has_mouse_reference = false;
            }

            if (state->has_mouse_reference) {
                const int dx = mouse_x - state->last_mouse_x;
                const int dy = mouse_y - state->last_mouse_y;
                state->camera_yaw += static_cast<float>(dx) * 0.006f;
                state->camera_pitch += static_cast<float>(dy) * 0.0045f;
                state->camera_pitch = std::clamp(state->camera_pitch, 0.05f, 1.5f);
            }

            state->last_mouse_x = mouse_x;
            state->last_mouse_y = mouse_y;
            state->has_mouse_reference = true;
        }
        return 0;
    case WM_MOUSELEAVE:
        if (state) {
            state->mouse_in_window = false;
            state->has_mouse_reference = false;
        }
        return 0;
    case WM_MOUSEWHEEL:
        if (state) {
            const int delta = GET_WHEEL_DELTA_WPARAM(w_param);
            state->camera_distance -= static_cast<float>(delta) * 6.4f;
            state->camera_distance = std::clamp(state->camera_distance, 1500.0f, 160000.0f);
        }
        return 0;
    case WM_KEYDOWN:
        if (!state || !state->owner) {
            break;
        }
        if (w_param == VK_ESCAPE) {
            state->should_close = true;
            DestroyWindow(hwnd);
            return 0;
        }
        if (w_param == VK_SPACE) {
            TelemetryCommand command;
            command.kind = state->paused ? TelemetryCommandKind::Resume : TelemetryCommandKind::Pause;
            state->owner->submit_command(command);
            state->paused = !state->paused;
            return 0;
        }
        if (w_param == 'N') {
            TelemetryCommand command;
            command.kind = TelemetryCommandKind::Step;
            command.payload = json::JSON::Make(json::JSON::Class::Object);
            command.payload["steps"] = json::Integral(1);
            state->owner->submit_command(command);
            return 0;
        }
        if (w_param == VK_F1) {
            state->camera_mode = ViewerState::CameraMode::Free;
            state->focus_uid.clear();
            return 0;
        }
        if (w_param == VK_F2) {
            cycle_follow_target(*state);
            return 0;
        }
        if (w_param == VK_OEM_PLUS || w_param == VK_ADD) {
            state->camera_fov_y = std::max(20.0f, state->camera_fov_y - 2.0f);
            return 0;
        }
        if (w_param == VK_OEM_MINUS || w_param == VK_SUBTRACT) {
            state->camera_fov_y = std::min(110.0f, state->camera_fov_y + 2.0f);
            return 0;
        }
        if (w_param == VK_LEFT) {
            state->camera_yaw -= 0.08f;
            return 0;
        }
        if (w_param == VK_RIGHT) {
            state->camera_yaw += 0.08f;
            return 0;
        }
        if (w_param == VK_UP) {
            state->camera_pitch = std::max(0.12f, state->camera_pitch - 0.06f);
            return 0;
        }
        if (w_param == VK_DOWN) {
            state->camera_pitch = std::min(1.4f, state->camera_pitch + 0.06f);
            return 0;
        }
        if (w_param == 'W') {
            state->move_forward = true;
            return 0;
        }
        if (w_param == 'S') {
            state->move_backward = true;
            return 0;
        }
        if (w_param == 'A') {
            state->move_left = true;
            return 0;
        }
        if (w_param == 'D') {
            state->move_right = true;
            return 0;
        }
        if (w_param == 'Q') {
            state->move_down = true;
            return 0;
        }
        if (w_param == 'E') {
            state->move_up = true;
            return 0;
        }
        break;
    case WM_KEYUP:
        if (!state) {
            break;
        }
        if (w_param == 'W') {
            state->move_forward = false;
            return 0;
        }
        if (w_param == 'S') {
            state->move_backward = false;
            return 0;
        }
        if (w_param == 'A') {
            state->move_left = false;
            return 0;
        }
        if (w_param == 'D') {
            state->move_right = false;
            return 0;
        }
        if (w_param == 'Q') {
            state->move_down = false;
            return 0;
        }
        if (w_param == 'E') {
            state->move_up = false;
            return 0;
        }
        break;
    default:
        break;
    }
    return DefWindowProc(hwnd, msg, w_param, l_param);
}

bool create_gl_window(ViewerState& state, std::string& error) {
    state.instance = GetModuleHandle(nullptr);

    WNDCLASS wc = {};
    wc.style = CS_OWNDC;
    wc.lpfnWndProc = viewer_window_proc;
    wc.hInstance = state.instance;
    wc.lpszClassName = "BvrSimOpenGLViewerWindow";
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);

    if (!RegisterClass(&wc) && GetLastError() != ERROR_CLASS_ALREADY_EXISTS) {
        error = "RegisterClass failed";
        return false;
    }

    state.hwnd = CreateWindowEx(
        0,
        wc.lpszClassName,
        "BVR Sim OpenGL Viewer",
        WS_OVERLAPPEDWINDOW | WS_VISIBLE,
        CW_USEDEFAULT,
        CW_USEDEFAULT,
        1280,
        820,
        nullptr,
        nullptr,
        state.instance,
        nullptr
    );
    if (!state.hwnd) {
        error = "CreateWindowEx failed";
        return false;
    }

    SetWindowLongPtr(state.hwnd, GWLP_USERDATA, reinterpret_cast<LONG_PTR>(&state));

    state.dc = GetDC(state.hwnd);
    if (!state.dc) {
        error = "GetDC failed";
        return false;
    }

    PIXELFORMATDESCRIPTOR pfd = {};
    pfd.nSize = sizeof(PIXELFORMATDESCRIPTOR);
    pfd.nVersion = 1;
    pfd.dwFlags = PFD_DRAW_TO_WINDOW | PFD_SUPPORT_OPENGL | PFD_DOUBLEBUFFER;
    pfd.iPixelType = PFD_TYPE_RGBA;
    pfd.cColorBits = 32;
    pfd.cDepthBits = 24;
    pfd.iLayerType = PFD_MAIN_PLANE;

    const int format = ChoosePixelFormat(state.dc, &pfd);
    if (format == 0 || !SetPixelFormat(state.dc, format, &pfd)) {
        error = "SetPixelFormat failed";
        return false;
    }

    state.rc = wglCreateContext(state.dc);
    if (!state.rc || !wglMakeCurrent(state.dc, state.rc)) {
        error = "wglCreateContext failed";
        return false;
    }

    if (!initialize_font_display_lists(state)) {
        error = "wglUseFontBitmaps failed";
        return false;
    }

    ShowWindow(state.hwnd, SW_SHOW);
    UpdateWindow(state.hwnd);
    return true;
}

void destroy_gl_window(ViewerState& state) {
    destroy_font_display_lists(state);
    if (state.rc) {
        wglMakeCurrent(nullptr, nullptr);
        wglDeleteContext(state.rc);
        state.rc = nullptr;
    }
    if (state.dc && state.hwnd) {
        ReleaseDC(state.hwnd, state.dc);
        state.dc = nullptr;
    }
    if (state.hwnd) {
        DestroyWindow(state.hwnd);
        state.hwnd = nullptr;
    }
}

void render_scene(ViewerState& view_state, const std::shared_ptr<const WorldSnapshot>& snapshot) {
    RECT rect{};
    GetClientRect(view_state.hwnd, &rect);
    const int width = std::max(1L, rect.right - rect.left);
    const int height = std::max(1L, rect.bottom - rect.top);

    glViewport(0, 0, width, height);
    glClearColor(0.04f, 0.07f, 0.11f, 1.0f);
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    glEnable(GL_DEPTH_TEST);
    glDisable(GL_CULL_FACE);
    glShadeModel(GL_SMOOTH);
    configure_scene_lighting();

    glMatrixMode(GL_PROJECTION);
    glLoadIdentity();
    perspective_gl(view_state.camera_fov_y, static_cast<double>(width) / static_cast<double>(height), 10.0, 400000.0);

    if (view_state.camera_mode == ViewerState::CameraMode::FollowObject && snapshot && !view_state.focus_uid.empty()) {
        for (const auto& object : snapshot->objects) {
            if (object.uid == view_state.focus_uid) {
                view_state.camera_target_x = static_cast<float>(object.position[0]);
                view_state.camera_target_y = static_cast<float>(object.position[2]);
                view_state.camera_target_z = static_cast<float>(object.position[1]);
                break;
            }
        }
    }

    const float target_x = view_state.camera_target_x;
    const float target_y = view_state.camera_target_y;
    const float target_z = view_state.camera_target_z;

    const float eye_x = target_x + std::cos(view_state.camera_yaw) * std::cos(view_state.camera_pitch) * view_state.camera_distance;
    const float eye_y = target_y + std::sin(view_state.camera_pitch) * view_state.camera_distance;
    const float eye_z = target_z + std::sin(view_state.camera_yaw) * std::cos(view_state.camera_pitch) * view_state.camera_distance;

    glMatrixMode(GL_MODELVIEW);
    glLoadIdentity();
    look_at_gl(eye_x, eye_y, eye_z, target_x, target_y, target_z, 0.0f, 1.0f, 0.0f);

    const std::array<float, 4> shadow_plane = {0.0f, 1.0f, 0.0f, 0.0f};
    const std::array<float, 4> shadow_light = {16000.0f, 24000.0f, 12000.0f, 1.0f};
    const auto shadow_matrix = build_shadow_matrix(shadow_plane, shadow_light);

    draw_grid(320000.0f, 32);

    if (snapshot) {
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
        for (const auto& object : snapshot->objects) {
            const auto color = team_color(object);
            const auto& orientation = object.orientation;
            const float pos_x = static_cast<float>(object.position[0]);
            const float pos_y = static_cast<float>(object.position[2]);
            const float pos_z = static_cast<float>(object.position[1]);
            const float alpha_scale = object.alive ? 1.0f : 0.35f;

            glPushMatrix();
            glMultMatrixf(shadow_matrix.data());
            glTranslatef(pos_x, pos_y + 2.0f, pos_z);
            glRotatef(static_cast<float>(rad2deg(orientation[2])), 0.0f, 1.0f, 0.0f);
            glRotatef(static_cast<float>(rad2deg(orientation[1])), 0.0f, 0.0f, 1.0f);
            glRotatef(static_cast<float>(rad2deg(orientation[0])), 1.0f, 0.0f, 0.0f);
            glDisable(GL_LIGHTING);
            glDepthMask(GL_FALSE);
            glColor4f(0.0f, 0.0f, 0.0f, 0.22f * alpha_scale);
            draw_object_geometry(object, true);
            glDepthMask(GL_TRUE);
            glEnable(GL_LIGHTING);
            glPopMatrix();

            glPushMatrix();
            glTranslatef(pos_x, pos_y, pos_z);
            glRotatef(static_cast<float>(rad2deg(orientation[2])), 0.0f, 1.0f, 0.0f);
            glRotatef(static_cast<float>(rad2deg(orientation[1])), 0.0f, 0.0f, 1.0f);
            glRotatef(static_cast<float>(rad2deg(orientation[0])), 1.0f, 0.0f, 0.0f);
            set_object_material(color, alpha_scale);
            draw_object_geometry(object, false);

            const bool focused = !view_state.focus_uid.empty() && view_state.focus_uid == object.uid;
            if (focused) {
                glDisable(GL_LIGHTING);
                draw_local_axes_marker(420.0f);
                glEnable(GL_LIGHTING);
            }
            glPopMatrix();
        }
        glDisable(GL_BLEND);
    }

    glDisable(GL_LIGHTING);
    glDisable(GL_LIGHT0);
    glDisable(GL_COLOR_MATERIAL);
    glDisable(GL_NORMALIZE);
    render_hud(view_state, width, height, eye_x, eye_y, eye_z, snapshot);
    SwapBuffers(view_state.dc);
}

void update_camera_motion(ViewerState& view_state) {
    if (view_state.camera_mode == ViewerState::CameraMode::FollowObject
        || (!view_state.move_forward
            && !view_state.move_backward
            && !view_state.move_left
            && !view_state.move_right
            && !view_state.move_up
            && !view_state.move_down)) {
        return;
    }

    const float planar_yaw = view_state.camera_yaw;
    const float forward_x = std::cos(planar_yaw);
    const float forward_z = std::sin(planar_yaw);
    const float right_x = -forward_z;
    const float right_z = forward_x;

    float move_x = 0.0f;
    float move_y = 0.0f;
    float move_z = 0.0f;
    if (view_state.move_forward) {
        move_x -= forward_x;
        move_z -= forward_z;
    }
    if (view_state.move_backward) {
        move_x += forward_x;
        move_z += forward_z;
    }
    if (view_state.move_right) {
        move_x -= right_x;
        move_z -= right_z;
    }
    if (view_state.move_left) {
        move_x += right_x;
        move_z += right_z;
    }
    if (view_state.move_up) {
        move_y += 1.0f;
    }
    if (view_state.move_down) {
        move_y -= 1.0f;
    }

    const float length = std::sqrt(move_x * move_x + move_y * move_y + move_z * move_z);
    if (length <= 1e-6f) {
        return;
    }
    move_x /= length;
    move_y /= length;
    move_z /= length;

    const float speed = std::max(120.0f, view_state.camera_distance * 0.015f);
    view_state.camera_target_x += move_x * speed;
    view_state.camera_target_y += move_y * speed;
    view_state.camera_target_z += move_z * speed;
}

void update_render_fps(ViewerState& view_state) {
    ++view_state.fps_frame_counter;
    const auto now = std::chrono::steady_clock::now();
    const auto elapsed = std::chrono::duration<double>(now - view_state.fps_window_start).count();
    if (elapsed >= 0.5) {
        view_state.render_fps = static_cast<double>(view_state.fps_frame_counter) / elapsed;
        view_state.fps_frame_counter = 0;
        view_state.fps_window_start = now;
    }
}

}

void OpenGLViewer::run_loop() noexcept {
    ViewerState view_state;
    view_state.owner = this;

    std::string error;
    if (!create_gl_window(view_state, error)) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = error;
        running_ = false;
        return;
    }

    running_ = true;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }

    while (!stop_requested_.load() && !view_state.should_close) {
        MSG msg;
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) {
                view_state.should_close = true;
                break;
            }
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }

        auto snapshot = snapshot_provider_ ? snapshot_provider_() : std::shared_ptr<const WorldSnapshot>();
        if (snapshot) {
            view_state.paused = snapshot->paused;
            view_state.snapshot_uids.clear();
            view_state.snapshot_uids.reserve(snapshot->objects.size());
            for (const auto& object : snapshot->objects) {
                view_state.snapshot_uids.push_back(object.uid);
            }
            if (view_state.camera_mode == ViewerState::CameraMode::FollowObject
                && !view_state.focus_uid.empty()
                && std::find(view_state.snapshot_uids.begin(), view_state.snapshot_uids.end(), view_state.focus_uid) == view_state.snapshot_uids.end()) {
                if (view_state.snapshot_uids.empty()) {
                    view_state.focus_uid.clear();
                } else {
                    view_state.focus_uid = view_state.snapshot_uids.front();
                }
            }
        } else {
            view_state.snapshot_uids.clear();
        }
        update_camera_motion(view_state);
        update_render_fps(view_state);
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_sim_time_ = snapshot ? snapshot->sim_time : 0.0;
            last_object_count_ = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;
            focus_uid_ = view_state.focus_uid;
        }

        render_scene(view_state, snapshot);
        std::this_thread::sleep_for(std::chrono::milliseconds(0));
    }

    destroy_gl_window(view_state);
    running_ = false;
}

#endif

}
