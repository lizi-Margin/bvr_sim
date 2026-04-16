#include "dx11_game_viewer_internal.hxx"

#include <array>
#include <string>
#include <utility>
#include <vector>

namespace bvr_sim {

#ifdef _WIN32

namespace {

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

Float4x4 identity_matrix() {
    Float4x4 out{};
    out.m[0][0] = 1.0f;
    out.m[1][1] = 1.0f;
    out.m[2][2] = 1.0f;
    out.m[3][3] = 1.0f;
    return out;
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

    const Float4x4 view_projection = multiply(scene.view, scene.projection);
    const Float4x4 identity_world = identity_matrix();
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
            multiply(batch.world, view_projection),
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
            multiply(batch.world, view_projection),
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

#endif

} // namespace bvr_sim
