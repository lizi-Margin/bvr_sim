#include "dx11/game_dx11_internal.hxx"
#include "c3utils/c3utils.hxx"


#include <algorithm>
#include <array>
#include <cctype>
#include <cmath>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

namespace bvr_sim {

#ifdef _WIN32

namespace {

RenderCommand make_clear_command(const std::array<float, 4>& clear_color) {
    RenderCommand command;
    command.type = RenderCommandType::Clear;
    command.clear_color = clear_color;
    return command;
}

RenderCommand make_draw_command(
    std::vector<DX11Vertex> vertices,
    D3D11_PRIMITIVE_TOPOLOGY topology,
    const Float4x4& world_view_proj,
    const Float4x4& world,
    const Float3& camera_position,
    bool depth_enabled,
    bool depth_write_enabled,
    bool lighting_enabled,
    bool blend_enabled,
    bool use_material_system,
    bool terrain_material,
    std::string material_key,
    float specular_strength,
    float specular_power,
    float opacity) {
    RenderCommand command;
    command.type = RenderCommandType::Draw;
    command.vertices = std::move(vertices);
    command.topology = topology;
    command.world_view_proj = world_view_proj;
    command.world = world;
    command.camera_position = camera_position;
    command.depth_enabled = depth_enabled;
    command.depth_write_enabled = depth_write_enabled;
    command.lighting_enabled = lighting_enabled;
    command.blend_enabled = blend_enabled;
    command.use_material_system = use_material_system;
    command.terrain_material = terrain_material;
    command.material_key = std::move(material_key);
    command.specular_strength = specular_strength;
    command.specular_power = specular_power;
    command.opacity = opacity;
    return command;
}

void apply_camera_basis(RenderCommand& command, const RenderScene& scene) {
    command.camera_forward = scene.camera_forward;
    command.camera_right = scene.camera_right;
    command.camera_up = scene.camera_up;
    command.camera_tan_half_fov_y = scene.camera_tan_half_fov_y;
    command.camera_aspect = scene.camera_aspect;
}

Float3 make_vec3(float x, float y, float z) {
    return Float3{x, y, z};
}

Float3 add_vec3(const Float3& a, const Float3& b) {
    return make_vec3(a.x + b.x, a.y + b.y, a.z + b.z);
}

Float3 sub_vec3(const Float3& a, const Float3& b) {
    return make_vec3(a.x - b.x, a.y - b.y, a.z - b.z);
}

Float3 scale_vec3(const Float3& v, float s) {
    return make_vec3(v.x * s, v.y * s, v.z * s);
}

float dot_vec3(const Float3& a, const Float3& b) {
    return a.x * b.x + a.y * b.y + a.z * b.z;
}

Float3 cross_vec3(const Float3& a, const Float3& b) {
    return make_vec3(
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    );
}

Float3 normalize_vec3(const Float3& v) {
    const float len_sq = dot_vec3(v, v);
    if (len_sq <= 1e-8f) {
        return make_vec3(0.0f, 1.0f, 0.0f);
    }
    return scale_vec3(v, 1.0f / std::sqrt(len_sq));
}

Float4x4 look_at_row_matrix(const Float3& eye, const Float3& target, const Float3& up_hint) {
    const Float3 forward = normalize_vec3(sub_vec3(target, eye));
    const Float3 right = normalize_vec3(cross_vec3(up_hint, forward));
    const Float3 up = cross_vec3(forward, right);

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
    out.m[3][0] = -dot_vec3(right, eye);
    out.m[3][1] = -dot_vec3(up, eye);
    out.m[3][2] = -dot_vec3(forward, eye);
    return out;
}

Float4x4 orthographic_matrix(float width, float height, float z_near, float z_far) {
    Float4x4 out{};
    out.m[0][0] = 2.0f / width;
    out.m[1][1] = 2.0f / height;
    out.m[2][2] = 1.0f / (z_far - z_near);
    out.m[3][2] = -z_near / (z_far - z_near);
    out.m[3][3] = 1.0f;
    return out;
}

Float4x4 build_shadow_view_projection(const Float3& center) {
    const Float3 light_dir = normalize_vec3(make_vec3(
        GameLightingConfig::k_sun_dir_x,
        GameLightingConfig::k_sun_dir_y,
        GameLightingConfig::k_sun_dir_z
    ));
    const Float3 light_eye = sub_vec3(center, scale_vec3(light_dir, 12000.0f));
    const Float3 up_hint = std::abs(light_dir.y) > 0.92f ? make_vec3(0.0f, 0.0f, 1.0f) : make_vec3(0.0f, 1.0f, 0.0f);
    const Float4x4 view = look_at_row_matrix(light_eye, center, up_hint);
    const Float4x4 projection = orthographic_matrix(6000.0f, 6000.0f, 10.0f, 26000.0f);
    return view * projection;
}

std::vector<std::string> make_hud_lines(
    const ViewerInputState& input,
    double sim_time,
    long object_count,
    const RenderFrameStats& stats) {
    std::vector<std::string> lines;
    lines.reserve(5);

    char line1[256];
    std::snprintf(
        line1,
        sizeof(line1),
        "SimTime %.2f  Objects %ld  Draws %ld  Vertices %ld",
        sim_time,
        object_count,
        stats.draw_calls,
        stats.vertex_count);
    lines.emplace_back(line1);

    char line2[320];
    const char* mode_text = input.input_mode == ViewerInputState::InputMode::Control ? "control" : "follow";
    const char* focus_text = input.focus_uid.empty() ? "free" : "object";
    std::snprintf(
        line2,
        sizeof(line2),
        "Camera Target (%.1f, %.1f, %.1f)  FOV %.1f  Dist %.1f  Mode %s  Focus %s",
        input.camera_target.x,
        input.camera_target.y,
        input.camera_target.z,
        input.camera_fov_y,
        input.camera_distance,
        mode_text,
        focus_text);
    lines.emplace_back(line2);

    char line3[192];
    std::snprintf(
        line3,
        sizeof(line3),
        "Shadows %s  Materials %s  RollLock %s",
        input.shadows_enabled ? "on" : "off",
        input.material_system_enabled ? "full" : "simple",
        input.camera_roll_locked ? "on" : "off");
    lines.emplace_back(line3);

    lines.emplace_back("Move: W A S D  Vertical: Q/E  Look: drag mouse  Zoom: wheel  Hold CapsLock: free look");
    lines.emplace_back("View: +/- FOV  F1 control/next  F2 follow/next  F3 shadows  F4 materials  F5 roll");
    return lines;
}

std::vector<std::string> make_focus_aircraft_lines(const ViewerInputState& input, const WorldSnapshot* snapshot) {
    std::vector<std::string> lines;
    lines.reserve(16);
    if (!snapshot || input.focus_uid.empty()) {
        lines.emplace_back("Aircraft: N/A");
        return lines;
    }

    auto focused_it = std::find_if(
        snapshot->objects.begin(),
        snapshot->objects.end(),
        [&input](const TelemetryObjectState& obj) { return obj.uid == input.focus_uid; });
    if (focused_it == snapshot->objects.end()) {
        lines.emplace_back("Aircraft: N/A");
        return lines;
    }

    const TelemetryObjectState& obj = *focused_it;
    const json::JSON& reg = obj.debug_register;
    lines.emplace_back("Aircraft: " + obj.uid);

    const double speed_mps = std::sqrt(
        obj.velocity[0] * obj.velocity[0]
        + obj.velocity[1] * obj.velocity[1]
        + obj.velocity[2] * obj.velocity[2]);
    const double speed_kmh = speed_mps * 3.6;
    const double altitude_ft = obj.position[2] * 3.280839895013123;
    double mach = 0.0;
    if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("mach", json::JSON::Class::Floating)) {
        mach = reg.at("mach").ToFloat();
    } else {
        mach = c3utils::get_mach(speed_mps, obj.position[2]);
    }

    char line_speed_alt[256];
    std::snprintf(
        line_speed_alt,
        sizeof(line_speed_alt),
        "SPD %.0f km/h  MACH %.2f  ALT %.0f ft",
        speed_kmh,
        mach,
        altitude_ft);
    lines.emplace_back(line_speed_alt);

    lines.emplace_back("Pylons:");
    bool has_pylon_line = false;
    if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("pylon_mounts", json::JSON::Class::Object)) {
        const auto pylon_mounts = reg.at("pylon_mounts");
        for (const auto& kv : pylon_mounts.ObjectRange()) {
            const std::string pylon_name = kv.first;
            std::string weapon_name = "";
            if (kv.second.JSONType() == json::JSON::Class::String) {
                weapon_name = kv.second.ToString();
            }
            const bool selected = !input.selected_pylon_name.empty() && pylon_name == input.selected_pylon_name;
            lines.emplace_back(std::string(selected ? "> " : "  ") + pylon_name + "-" + (weapon_name.empty() ? "EMPTY" : weapon_name));
            has_pylon_line = true;
        }
    }
    if (!has_pylon_line) {
        lines.emplace_back("  N/A");
    }

    return lines;
}

bool glyph_bit(char c, int x, int y) {
    const char uc = static_cast<char>(std::toupper(static_cast<unsigned char>(c)));
    if (x < 0 || x >= 5 || y < 0 || y >= 7) {
        return false;
    }
    if (uc >= '0' && uc <= '9') {
        static const unsigned char digits[10][7] = {
            {0x0E,0x11,0x13,0x15,0x19,0x11,0x0E},{0x04,0x0C,0x14,0x04,0x04,0x04,0x1F},
            {0x0E,0x11,0x01,0x02,0x04,0x08,0x1F},{0x1E,0x01,0x01,0x0E,0x01,0x01,0x1E},
            {0x02,0x06,0x0A,0x12,0x1F,0x02,0x02},{0x1F,0x10,0x10,0x1E,0x01,0x01,0x1E},
            {0x0E,0x10,0x10,0x1E,0x11,0x11,0x0E},{0x1F,0x01,0x02,0x04,0x08,0x08,0x08},
            {0x0E,0x11,0x11,0x0E,0x11,0x11,0x0E},{0x0E,0x11,0x11,0x0F,0x01,0x01,0x0E},
        };
        return ((digits[uc - '0'][y] >> (4 - x)) & 1U) != 0;
    }
    if (uc >= 'A' && uc <= 'Z') {
        static const unsigned char letters[26][7] = {
            {0x0E,0x11,0x11,0x1F,0x11,0x11,0x11},{0x1E,0x11,0x11,0x1E,0x11,0x11,0x1E},
            {0x0E,0x11,0x10,0x10,0x10,0x11,0x0E},{0x1C,0x12,0x11,0x11,0x11,0x12,0x1C},
            {0x1F,0x10,0x10,0x1E,0x10,0x10,0x1F},{0x1F,0x10,0x10,0x1E,0x10,0x10,0x10},
            {0x0E,0x11,0x10,0x17,0x11,0x11,0x0F},{0x11,0x11,0x11,0x1F,0x11,0x11,0x11},
            {0x0E,0x04,0x04,0x04,0x04,0x04,0x0E},{0x01,0x01,0x01,0x01,0x11,0x11,0x0E},
            {0x11,0x12,0x14,0x18,0x14,0x12,0x11},{0x10,0x10,0x10,0x10,0x10,0x10,0x1F},
            {0x11,0x1B,0x15,0x15,0x11,0x11,0x11},{0x11,0x19,0x15,0x13,0x11,0x11,0x11},
            {0x0E,0x11,0x11,0x11,0x11,0x11,0x0E},{0x1E,0x11,0x11,0x1E,0x10,0x10,0x10},
            {0x0E,0x11,0x11,0x11,0x15,0x12,0x0D},{0x1E,0x11,0x11,0x1E,0x14,0x12,0x11},
            {0x0E,0x11,0x10,0x0E,0x01,0x11,0x0E},{0x1F,0x04,0x04,0x04,0x04,0x04,0x04},
            {0x11,0x11,0x11,0x11,0x11,0x11,0x0E},{0x11,0x11,0x11,0x11,0x11,0x0A,0x04},
            {0x11,0x11,0x11,0x15,0x15,0x1B,0x11},{0x11,0x11,0x0A,0x04,0x0A,0x11,0x11},
            {0x11,0x11,0x0A,0x04,0x04,0x04,0x04},{0x1F,0x01,0x02,0x04,0x08,0x10,0x1F},
        };
        return ((letters[uc - 'A'][y] >> (4 - x)) & 1U) != 0;
    }

    switch (uc) {
    case ' ': return false;
    case '.': return (x == 2 && y == 6);
    case ',': return (x == 2 && y == 6) || (x == 1 && y == 6);
    case ':': return (x == 2 && (y == 2 || y == 5));
    case '/': return (x + y == 6);
    case '-': return (y == 3 && x >= 1 && x <= 3);
    case '+': return ((x == 2 && y >= 1 && y <= 5) || (y == 3 && x >= 0 && x <= 4));
    case '>': return ((x == y - 1 && y >= 1 && y <= 3) || (x == 5 - y && y >= 3 && y <= 5));
    case '(': return ((x == 3 && y >= 1 && y <= 5) || ((y == 0 || y == 6) && x == 4));
    case ')': return ((x == 1 && y >= 1 && y <= 5) || ((y == 0 || y == 6) && x == 0));
    default: return false;
    }
}

void append_text_quad_vertices(
    std::vector<DX11Vertex>& out_vertices,
    float x0,
    float y0,
    float x1,
    float y1,
    const Float3& color,
    float opacity) {
    const float z = 0.0f;
    const float nx = 0.0f;
    const float ny = 0.0f;
    const float nz = 1.0f;
    const float c0 = color.x * opacity;
    const float c1 = color.y * opacity;
    const float c2 = color.z * opacity;
    out_vertices.push_back(DX11Vertex{{x0,y0,z},{c0,c1,c2},{nx,ny,nz},{0.0f,0.0f}});
    out_vertices.push_back(DX11Vertex{{x1,y0,z},{c0,c1,c2},{nx,ny,nz},{1.0f,0.0f}});
    out_vertices.push_back(DX11Vertex{{x1,y1,z},{c0,c1,c2},{nx,ny,nz},{1.0f,1.0f}});
    out_vertices.push_back(DX11Vertex{{x0,y0,z},{c0,c1,c2},{nx,ny,nz},{0.0f,0.0f}});
    out_vertices.push_back(DX11Vertex{{x1,y1,z},{c0,c1,c2},{nx,ny,nz},{1.0f,1.0f}});
    out_vertices.push_back(DX11Vertex{{x0,y1,z},{c0,c1,c2},{nx,ny,nz},{0.0f,1.0f}});
}

void append_line_segment(
    std::vector<DX11Vertex>& out_vertices,
    float x0,
    float y0,
    float x1,
    float y1,
    const Float3& color,
    float opacity) {
    const float z = 0.0f;
    const float nx = 0.0f;
    const float ny = 0.0f;
    const float nz = 1.0f;
    const float c0 = color.x * opacity;
    const float c1 = color.y * opacity;
    const float c2 = color.z * opacity;
    out_vertices.push_back(DX11Vertex{{x0,y0,z},{c0,c1,c2},{nx,ny,nz},{0.0f,0.0f}});
    out_vertices.push_back(DX11Vertex{{x1,y1,z},{c0,c1,c2},{nx,ny,nz},{0.0f,0.0f}});
}

bool project_direction_to_ndc(
    const Float3& dir,
    const Float3& cam_forward,
    const Float3& cam_right,
    const Float3& cam_up,
    float fov_x,
    float fov_y,
    float clamp_abs,
    float& out_x,
    float& out_y) {
    const float f = dir.x * cam_forward.x + dir.y * cam_forward.y + dir.z * cam_forward.z;
    if (f <= 0.02f) {
        return false;
    }
    const float r = dir.x * cam_right.x + dir.y * cam_right.y + dir.z * cam_right.z;
    const float u = dir.x * cam_up.x + dir.y * cam_up.y + dir.z * cam_up.z;
    out_x = std::clamp((r / f) / std::tan(fov_x * 0.5f), -clamp_abs, clamp_abs);
    out_y = std::clamp((u / f) / std::tan(fov_y * 0.5f), -clamp_abs, clamp_abs);
    return true;
}

} // namespace

RenderCommandList record_render_commands(RenderScene scene) {
    RenderCommandList command_list;
    command_list.commands.reserve(4 + scene.object_batches.size());
    command_list.shadow_map_enabled = scene.shadows_enabled;
    command_list.shadow_view_projection = build_shadow_view_projection(scene.shadow_center);

    command_list.commands.push_back(make_clear_command({0.54f, 0.66f, 0.74f, 1.0f}));
    RenderCommand sky_command = make_draw_command(
        std::move(scene.sky_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
        scene.clip_space,
        scene.clip_space,
        scene.camera_position,
        false,
        false,
        false,
        false,
        false,
        false,
        "sky",
        0.0f,
        1.0f,
        1.0f
    );
    apply_camera_basis(sky_command, scene);
    command_list.commands.push_back(std::move(sky_command));

    const Float4x4 view_projection = scene.view * scene.projection;
    const Float4x4 identity_world = Float4x4::identity();
    RenderCommand ground_command = make_draw_command(
        std::move(scene.ground_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
        view_projection,
        identity_world,
        scene.camera_position,
        true,
        true,
        true,
        false,
        true,
        true,
        "terrain",
        0.04f,
        12.0f,
        1.0f
    );
    ground_command.shadow_world_view_proj = identity_world * command_list.shadow_view_projection;
    ground_command.receive_shadows = command_list.shadow_map_enabled;
    apply_camera_basis(ground_command, scene);
    command_list.commands.push_back(std::move(ground_command));

    for (auto& batch : scene.object_batches) {
        RenderCommand shadow_command = make_draw_command(
            batch.vertices,
            D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
            batch.world * command_list.shadow_view_projection,
            batch.world,
            scene.camera_position,
            true,
            true,
            false,
            false,
            false,
            false,
            "sky",
            0.0f,
            1.0f,
            1.0f
        );
        if (command_list.shadow_map_enabled) {
            command_list.shadow_commands.push_back(std::move(shadow_command));
        }

        RenderCommand object_command = make_draw_command(
            std::move(batch.vertices),
            D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
            batch.world * view_projection,
            batch.world,
            scene.camera_position,
            true,
            true,
            true,
            false,
            batch.use_material_system,
            false,
            batch.material_key,
            0.28f,
            48.0f,
            1.0f
        );
        object_command.shadow_world_view_proj = batch.world * command_list.shadow_view_projection;
        object_command.receive_shadows = command_list.shadow_map_enabled;
        apply_camera_basis(object_command, scene);
        command_list.commands.push_back(std::move(object_command));
    }

    return command_list;
}

void append_hud_render_commands(
    RenderCommandList& command_list,
    UINT width,
    UINT height,
    const ViewerInputState& input,
    const WorldSnapshot* snapshot,
    double sim_time,
    long object_count,
    const RenderFrameStats& stats) {
    if (width < 32 || height < 32) {
        return;
    }

    const std::vector<std::string> lines = make_hud_lines(input, sim_time, object_count, stats);
    const std::vector<std::string> aircraft_lines = make_focus_aircraft_lines(input, snapshot);
    const int pixel_scale = 2;
    const int glyph_w = 5 * pixel_scale;
    const int glyph_h = 7 * pixel_scale;
    const int glyph_gap = 1 * pixel_scale;
    const int line_h = glyph_h + 6;

    auto to_ndc = [width, height](float px, float py) -> Float3 {
        const float x = (px / static_cast<float>(width)) * 2.0f - 1.0f;
        const float y = 1.0f - (py / static_cast<float>(height)) * 2.0f;
        return Float3{x, y, 0.0f};
    };

    std::vector<DX11Vertex> vertices;
    vertices.reserve(40000);
    const Float3 text_color{0.95f, 0.98f, 1.0f};
    const Float3 shadow_color{0.02f, 0.05f, 0.08f};

    const int x_start = 16;
    int y_top = 16;
    for (const std::string& line : aircraft_lines) {
        int x = x_start;
        for (char c : line) {
            for (int gy = 0; gy < 7; ++gy) {
                for (int gx = 0; gx < 5; ++gx) {
                    if (!glyph_bit(c, gx, gy)) {
                        continue;
                    }
                    const float sx0 = static_cast<float>(x + gx * pixel_scale + 1);
                    const float sy0 = static_cast<float>(y_top + gy * pixel_scale + 1);
                    const float sx1 = sx0 + static_cast<float>(pixel_scale);
                    const float sy1 = sy0 + static_cast<float>(pixel_scale);
                    const Float3 s0 = to_ndc(sx0, sy0);
                    const Float3 s1 = to_ndc(sx1, sy1);
                    append_text_quad_vertices(vertices, s0.x, s0.y, s1.x, s1.y, shadow_color, 0.8f);

                    const float tx0 = static_cast<float>(x + gx * pixel_scale);
                    const float ty0 = static_cast<float>(y_top + gy * pixel_scale);
                    const float tx1 = tx0 + static_cast<float>(pixel_scale);
                    const float ty1 = ty0 + static_cast<float>(pixel_scale);
                    const Float3 t0 = to_ndc(tx0, ty0);
                    const Float3 t1 = to_ndc(tx1, ty1);
                    append_text_quad_vertices(vertices, t0.x, t0.y, t1.x, t1.y, text_color, 1.0f);
                }
            }
            x += glyph_w + glyph_gap;
        }
        y_top += line_h;
    }

    int y_bottom = static_cast<int>(height) - 16 - static_cast<int>(line_h * static_cast<int>(lines.size()));
    if (y_bottom < 16) {
        y_bottom = 16;
    }
    for (const std::string& line : lines) {
        int x = x_start;
        for (char c : line) {
            for (int gy = 0; gy < 7; ++gy) {
                for (int gx = 0; gx < 5; ++gx) {
                    if (!glyph_bit(c, gx, gy)) {
                        continue;
                    }
                    const float sx0 = static_cast<float>(x + gx * pixel_scale + 1);
                    const float sy0 = static_cast<float>(y_bottom + gy * pixel_scale + 1);
                    const float sx1 = sx0 + static_cast<float>(pixel_scale);
                    const float sy1 = sy0 + static_cast<float>(pixel_scale);
                    const Float3 s0 = to_ndc(sx0, sy0);
                    const Float3 s1 = to_ndc(sx1, sy1);
                    append_text_quad_vertices(vertices, s0.x, s0.y, s1.x, s1.y, shadow_color, 0.8f);

                    const float tx0 = static_cast<float>(x + gx * pixel_scale);
                    const float ty0 = static_cast<float>(y_bottom + gy * pixel_scale);
                    const float tx1 = tx0 + static_cast<float>(pixel_scale);
                    const float ty1 = ty0 + static_cast<float>(pixel_scale);
                    const Float3 t0 = to_ndc(tx0, ty0);
                    const Float3 t1 = to_ndc(tx1, ty1);
                    append_text_quad_vertices(vertices, t0.x, t0.y, t1.x, t1.y, text_color, 1.0f);
                }
            }
            x += glyph_w + glyph_gap;
        }
        y_bottom += line_h;
    }

    if (vertices.empty()) {
        return;
    }

    const Float4x4 identity = Float4x4::identity();
    command_list.commands.push_back(make_draw_command(
        std::move(vertices),
        D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
        identity,
        identity,
        Float3{0.0f, 0.0f, 0.0f},
        false,
        false,
        false,
        true,
        false,
        false,
        "sky",
        0.0f,
        1.0f,
        1.0f
    ));

    const bool show_control_hud =
        input.input_mode == ViewerInputState::InputMode::Control
        && input.camera_mode == ViewerInputState::CameraMode::FollowObject
        && !input.focus_uid.empty();
    if (!show_control_hud) {
        return;
    }

    const float fov_y = std::max(0.25f, input.camera_fov_y * static_cast<float>(3.14159265358979323846 / 180.0));
    const float aspect = std::max(1.0f, static_cast<float>(width) / static_cast<float>(height));
    const float fov_x = 2.0f * std::atan(std::tan(fov_y * 0.5f) * aspect);

    float target_x = 0.0f;
    float target_y = 0.0f;

    float boresight_x = 0.0f;
    float boresight_y = 0.0f;
    bool boresight_valid = false;
    const float cam_cy = std::cos(input.camera_yaw);
    const float cam_sy = std::sin(input.camera_yaw);
    const float cam_cp = std::cos(input.camera_pitch);
    const float cam_sp = std::sin(input.camera_pitch);
    Float3 cam_fwd{-cam_cp * cam_cy, -cam_sp, -cam_cp * cam_sy};
    const Float3 world_up{0.0f, 1.0f, 0.0f};
    Float3 cam_right{
        world_up.y * cam_fwd.z - world_up.z * cam_fwd.y,
        world_up.z * cam_fwd.x - world_up.x * cam_fwd.z,
        world_up.x * cam_fwd.y - world_up.y * cam_fwd.x
    };
    const float right_len = std::sqrt(cam_right.x * cam_right.x + cam_right.y * cam_right.y + cam_right.z * cam_right.z);
    if (right_len > 1e-6f) {
        cam_right.x /= right_len;
        cam_right.y /= right_len;
        cam_right.z /= right_len;
        const Float3 cam_up{
            cam_fwd.y * cam_right.z - cam_fwd.z * cam_right.y,
            cam_fwd.z * cam_right.x - cam_fwd.x * cam_right.z,
            cam_fwd.x * cam_right.y - cam_fwd.y * cam_right.x
        };

        const float aim_cy = std::cos(input.aim_yaw);
        const float aim_sy = std::sin(input.aim_yaw);
        const float aim_cp = std::cos(input.aim_pitch);
        const float aim_sp = std::sin(input.aim_pitch);
        const Float3 aim_fwd{-aim_cp * aim_cy, -aim_sp, -aim_cp * aim_sy};
        project_direction_to_ndc(aim_fwd, cam_fwd, cam_right, cam_up, fov_x, fov_y, 0.95f, target_x, target_y);

        if (snapshot) {
            auto focused_it = std::find_if(
                snapshot->objects.begin(),
                snapshot->objects.end(),
                [&input](const TelemetryObjectState& obj) { return obj.uid == input.focus_uid; });
            if (focused_it != snapshot->objects.end()) {
                const Float3x3 orientation = Float3x3::from_sim_orientation(focused_it->orientation).convert_nwu_to_viewer();
                const Float3 obj_fwd{orientation.m[0][0], orientation.m[1][0], orientation.m[2][0]};

                boresight_valid = project_direction_to_ndc(
                    obj_fwd, cam_fwd, cam_right, cam_up, fov_x, fov_y, 0.98f, boresight_x, boresight_y);
            }
        }
    }

    std::vector<DX11Vertex> hud_lines;
    hud_lines.reserve(256);

    const Float3 boresight_color{0.92f, 0.95f, 1.0f};
    const Float3 target_color{0.35f, 1.0f, 0.62f};
    const Float3 link_color{0.55f, 0.90f, 1.0f};

    const int ring_segments = 24;
    const float ring_radius = 0.035f;
    for (int i = 0; i < ring_segments; ++i) {
        const float a0 = static_cast<float>(i) * static_cast<float>(2.0 * 3.14159265358979323846 / ring_segments);
        const float a1 = static_cast<float>(i + 1) * static_cast<float>(2.0 * 3.14159265358979323846 / ring_segments);
        const float x0 = target_x + std::cos(a0) * ring_radius;
        const float y0 = target_y + std::sin(a0) * ring_radius;
        const float x1 = target_x + std::cos(a1) * ring_radius;
        const float y1 = target_y + std::sin(a1) * ring_radius;
        append_line_segment(hud_lines, x0, y0, x1, y1, target_color, 0.95f);
    }

    if (boresight_valid) {
        const float cross = 0.020f;
        append_line_segment(hud_lines, boresight_x - cross, boresight_y, boresight_x - 0.006f, boresight_y, boresight_color, 0.95f);
        append_line_segment(hud_lines, boresight_x + 0.006f, boresight_y, boresight_x + cross, boresight_y, boresight_color, 0.95f);
        append_line_segment(hud_lines, boresight_x, boresight_y - cross, boresight_x, boresight_y - 0.006f, boresight_color, 0.95f);
        append_line_segment(hud_lines, boresight_x, boresight_y + 0.006f, boresight_x, boresight_y + cross, boresight_color, 0.95f);
        append_line_segment(hud_lines, boresight_x, boresight_y, target_x, target_y, link_color, 0.55f);
    }

    if (!hud_lines.empty()) {
        command_list.commands.push_back(make_draw_command(
            std::move(hud_lines),
            D3D11_PRIMITIVE_TOPOLOGY_LINELIST,
            identity,
            identity,
            Float3{0.0f, 0.0f, 0.0f},
            false,
            false,
            false,
            true,
            false,
            false,
            "sky",
            0.0f,
            1.0f,
            1.0f
        ));
    }
}

#endif

} // namespace bvr_sim





