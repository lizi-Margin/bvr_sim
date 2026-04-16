#include "dx11_game_viewer_internal.hxx"

#include <array>
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

} // namespace

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
        view_projection,
        true
    ));
    command_list.commands.push_back(make_draw_command(
        std::move(scene.grid_vertices),
        D3D11_PRIMITIVE_TOPOLOGY_LINELIST,
        view_projection,
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

#endif

} // namespace bvr_sim
