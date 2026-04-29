#include "dx11/game_dx11_internal.hxx"


#include <array>
#include <cctype>
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
    std::snprintf(
        line2,
        sizeof(line2),
        "Camera Target (%.1f, %.1f, %.1f)  FOV %.1f  Dist %.1f  Mode %s",
        input.camera_target.x,
        input.camera_target.y,
        input.camera_target.z,
        input.camera_fov_y,
        input.camera_distance,
        input.camera_mode == ViewerInputState::CameraMode::Free ? "free" : "follow");
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

    lines.emplace_back("Move: W A S D  Vertical: Q/E  Look: drag mouse  Zoom: wheel");
    lines.emplace_back("View: +/- FOV  F1 free  F2 follow/next  F3 shadows  F4 materials  F5 roll lock");
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

} // namespace

RenderCommandList record_render_commands(RenderScene scene) {
    RenderCommandList command_list;
    command_list.commands.reserve(4 + scene.object_batches.size());

    command_list.commands.push_back(make_clear_command({0.54f, 0.66f, 0.74f, 1.0f}));
    command_list.commands.push_back(make_draw_command(
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
    ));

    const Float4x4 view_projection = scene.view * scene.projection;
    const Float4x4 identity_world = Float4x4::identity();
    command_list.commands.push_back(make_draw_command(
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
    ));
    command_list.commands.push_back(make_draw_command(
        std::move(scene.grid_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_LINELIST,
        view_projection,
        identity_world,
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
    ));

    for (auto& batch : scene.shadow_batches) {
        command_list.commands.push_back(make_draw_command(
            std::move(batch.vertices),
            D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST,
            batch.world * view_projection,
            batch.world,
            scene.camera_position,
            true,
            false,
            false,
            true,
            false,
            false,
            "sky",
            0.0f,
            1.0f,
            0.22f
        ));
    }

    for (auto& batch : scene.object_batches) {
        command_list.commands.push_back(make_draw_command(
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
        ));
    }

    return command_list;
}

void append_hud_render_commands(
    RenderCommandList& command_list,
    UINT width,
    UINT height,
    const ViewerInputState& input,
    double sim_time,
    long object_count,
    const RenderFrameStats& stats) {
    if (width < 32 || height < 32) {
        return;
    }

    const std::vector<std::string> lines = make_hud_lines(input, sim_time, object_count, stats);
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
    int y = 16;
    for (const std::string& line : lines) {
        int x = x_start;
        for (char c : line) {
            for (int gy = 0; gy < 7; ++gy) {
                for (int gx = 0; gx < 5; ++gx) {
                    if (!glyph_bit(c, gx, gy)) {
                        continue;
                    }
                    const float sx0 = static_cast<float>(x + gx * pixel_scale + 1);
                    const float sy0 = static_cast<float>(y + gy * pixel_scale + 1);
                    const float sx1 = sx0 + static_cast<float>(pixel_scale);
                    const float sy1 = sy0 + static_cast<float>(pixel_scale);
                    const Float3 s0 = to_ndc(sx0, sy0);
                    const Float3 s1 = to_ndc(sx1, sy1);
                    append_text_quad_vertices(vertices, s0.x, s0.y, s1.x, s1.y, shadow_color, 0.8f);

                    const float tx0 = static_cast<float>(x + gx * pixel_scale);
                    const float ty0 = static_cast<float>(y + gy * pixel_scale);
                    const float tx1 = tx0 + static_cast<float>(pixel_scale);
                    const float ty1 = ty0 + static_cast<float>(pixel_scale);
                    const Float3 t0 = to_ndc(tx0, ty0);
                    const Float3 t1 = to_ndc(tx1, ty1);
                    append_text_quad_vertices(vertices, t0.x, t0.y, t1.x, t1.y, text_color, 1.0f);
                }
            }
            x += glyph_w + glyph_gap;
        }
        y += line_h;
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
}

#endif

} // namespace bvr_sim





