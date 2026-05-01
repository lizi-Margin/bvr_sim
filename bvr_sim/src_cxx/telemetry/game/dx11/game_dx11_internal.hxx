#pragma once

#include "../game_config.hxx"
#include "../../telemetry_types.hxx"
#include "../game_types.hxx"

#include <array>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#define WIN32_LEAN_AND_MEAN
#include <d3d11.h>
#include <windows.h>
#include <windowsx.h>
#endif

namespace bvr_sim {

#ifdef _WIN32

struct DX11Vertex {
    float position[3];
    float color[3];
    float normal[3];
    float uv[2];
};

struct SceneConstants {
    Float4x4 world_view_proj;
    Float4x4 world;
    std::array<float, 4> light_direction_ambient{0.0f, 1.0f, 0.0f, 0.35f};
    std::array<float, 4> light_color_intensity{1.0f, 0.96f, 0.88f, 0.85f};
    std::array<float, 4> material_flags{1.0f, 0.0f, 0.0f, 0.0f};
    std::array<float, 4> camera_position_fog_start{0.0f, 0.0f, 0.0f, 65000.0f};
    std::array<float, 4> fog_color_density{0.72f, 0.80f, 0.84f, 0.000018f};
    std::array<float, 4> ambient_sky_ground{0.44f, 0.18f, 0.0f, 0.0f};
    std::array<float, 4> material_tint{1.0f, 0.0f, 0.0f, 0.0f};
};

enum class RenderCommandType {
    Clear,
    Draw,
};

struct RenderCommand {
    RenderCommandType type = RenderCommandType::Clear;
    std::vector<DX11Vertex> vertices;
    D3D11_PRIMITIVE_TOPOLOGY topology = D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST;
    Float4x4 world_view_proj{};
    Float4x4 world{};
    Float3 camera_position{};
    bool depth_enabled = true;
    bool depth_write_enabled = true;
    bool lighting_enabled = true;
    bool blend_enabled = false;
    bool use_material_system = true;
    bool terrain_material = false;
    std::string material_key = "sky";
    float specular_strength = 0.15f;
    float specular_power = 32.0f;
    float opacity = 1.0f;
    std::array<float, 4> clear_color{0.0f, 0.0f, 0.0f, 1.0f};
};

struct RenderCommandList {
    std::vector<RenderCommand> commands;
};

struct RenderFrameStats {
    long command_count = 0;
    long draw_calls = 0;
    long vertex_count = 0;
};

struct RenderScene {
    Float4x4 view{};
    Float4x4 projection{};
    Float4x4 clip_space{};
    Float3 camera_position{};
    std::vector<DX11Vertex> sky_vertices;
    std::vector<DX11Vertex> ground_vertices;
    std::vector<DX11Vertex> grid_vertices;

    struct ObjectBatch {
        std::vector<DX11Vertex> vertices;
        Float4x4 world{};
        std::string material_key = "aircraft_default";
        bool use_material_system = true;
    };

    std::vector<ObjectBatch> shadow_batches;
    std::vector<ObjectBatch> object_batches;
};

struct ViewerInputState {
    enum class InputMode {
        Control,
        Follow,
    };

    enum class CameraMode {
        Free,
        FollowObject,
    };

    bool move_forward = false;
    bool move_backward = false;
    bool move_left = false;
    bool move_right = false;
    bool move_up = false;
    bool move_down = false;
    bool dragging = false;
    bool mouse_has_reference = false;
    int last_mouse_x = 0;
    int last_mouse_y = 0;
    int mouse_x = 0;
    int mouse_y = 0;
    int client_width = 1;
    int client_height = 1;
    float mouse_aim_x = 0.0f;
    float mouse_aim_y = 0.0f;
    bool mouse_aim_enabled = true;
    InputMode input_mode = InputMode::Control;
    CameraMode camera_mode = CameraMode::FollowObject;
    float camera_yaw = 0.70f;
    float camera_pitch = 0.55f;
    float aim_yaw = 0.70f;
    float aim_pitch = 0.55f;
    float camera_distance = GameCameraConfig::k_min_distance;
    Float3 camera_target{0.0f, 6000.0f, 0.0f};
    float camera_fov_y = 100.0f;
    bool shadows_enabled = true;
    bool material_system_enabled = false;
    bool camera_roll_locked = true;
    bool capslock_held = false;
    bool ctrl_aileron_left = false;
    bool ctrl_aileron_right = false;
    bool ctrl_elevator_up = false;
    bool ctrl_elevator_down = false;
    bool ctrl_rudder_left = false;
    bool ctrl_rudder_right = false;
    bool fire_r_armed = false;
    bool fire_once_requested = false;
    bool pylon_cycle_ctrl_armed = false;
    bool pylon_cycle_requested = false;
    std::string selected_pylon_name;
    int focus_cycle_index = -1; // -1 means free camera slot
    std::string focus_uid;
    std::vector<std::string> snapshot_uids;
};

struct Win32Window {
    HINSTANCE instance = nullptr;
    HWND hwnd = nullptr;
    ViewerInputState input;
};

struct D3D11Context {
    ID3D11Device* device = nullptr;
    ID3D11DeviceContext* context = nullptr;
    IDXGISwapChain* swap_chain = nullptr;
    ID3D11RenderTargetView* rtv = nullptr;
    ID3D11Texture2D* depth_texture = nullptr;
    ID3D11DepthStencilView* dsv = nullptr;
    ID3D11VertexShader* vertex_shader = nullptr;
    ID3D11PixelShader* pixel_shader = nullptr;
    ID3D11InputLayout* input_layout = nullptr;
    ID3D11Buffer* constant_buffer = nullptr;
    ID3D11Buffer* dynamic_vertex_buffer = nullptr;
    ID3D11ShaderResourceView* white_texture_srv = nullptr;
    ID3D11ShaderResourceView* flat_normal_texture_srv = nullptr;
    ID3D11ShaderResourceView* black_texture_srv = nullptr;
    ID3D11ShaderResourceView* terrain_texture_srv = nullptr;
    ID3D11ShaderResourceView* object_texture_srv = nullptr;
    ID3D11ShaderResourceView* object_normal_texture_srv = nullptr;
    ID3D11ShaderResourceView* object_roughness_texture_srv = nullptr;
    ID3D11ShaderResourceView* object_metallic_texture_srv = nullptr;
    ID3D11SamplerState* texture_sampler = nullptr;
    struct MaterialResource {
        std::string key;
        bool terrain = false;
        float team_tint_strength = 1.0f;
        float specular_strength = 0.15f;
        float specular_power = 32.0f;
        float fog_start = 65000.0f;
        float fog_density = 0.000010f;
        std::array<float, 3> fog_color{0.74f, 0.81f, 0.85f};
        ID3D11ShaderResourceView* albedo_srv = nullptr;
        ID3D11ShaderResourceView* normal_srv = nullptr;
        ID3D11ShaderResourceView* roughness_srv = nullptr;
        ID3D11ShaderResourceView* metallic_srv = nullptr;
        bool owns_albedo = false;
        bool owns_normal = false;
        bool owns_roughness = false;
        bool owns_metallic = false;
    };
    std::unordered_map<std::string, MaterialResource> materials;
    std::unordered_map<std::string, ID3D11ShaderResourceView*> material_texture_cache;
    UINT dynamic_vertex_capacity = 0;
    ID3D11RasterizerState* rasterizer_state = nullptr;
    ID3D11DepthStencilState* depth_state = nullptr;
    ID3D11DepthStencilState* depth_readonly_state = nullptr;
    ID3D11DepthStencilState* depth_disabled_state = nullptr;
    ID3D11BlendState* alpha_blend_state = nullptr;
    UINT back_buffer_width = 0;
    UINT back_buffer_height = 0;
    bool common_pipeline_bound = false;
    D3D11_PRIMITIVE_TOPOLOGY current_topology = D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
    ID3D11DepthStencilState* current_depth_state = nullptr;
    bool blend_enabled = false;
    std::string current_material_key;
    bool material_textures_bound = false;
};

void update_camera(ViewerInputState& input, float dt_seconds);
bool create_window(Win32Window& window, std::string& error);
void destroy_window(Win32Window& window);
bool create_d3d11(HWND hwnd, D3D11Context& d3d11, std::string& error);
void destroy_d3d11(D3D11Context& d3d11);
bool resize_swap_chain_if_needed(D3D11Context& d3d11, HWND hwnd, UINT width, UINT height, std::string& error);
void update_viewport_from_client_rect(HWND hwnd, ID3D11DeviceContext* context, UINT& out_width, UINT& out_height);
RenderScene build_render_scene(const ViewerInputState& input, UINT width, UINT height, const WorldSnapshot* snapshot);
RenderCommandList record_render_commands(RenderScene scene);
void append_hud_render_commands(
    RenderCommandList& command_list,
    UINT width,
    UINT height,
    const ViewerInputState& input,
    const WorldSnapshot* snapshot,
    double sim_time,
    long object_count,
    const RenderFrameStats& stats);
bool execute_render_commands(D3D11Context& d3d11, const RenderCommandList& command_list, RenderFrameStats& out_stats);
void draw_hud_text(HWND hwnd, const ViewerInputState& input, double sim_time, long object_count, const RenderFrameStats& stats);

#endif

} // namespace bvr_sim


