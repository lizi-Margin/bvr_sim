#pragma once

#include "telemetry_types.hxx"

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

struct Float3 {
    float x = 0.0f;
    float y = 0.0f;
    float z = 0.0f;
};

struct Float4x4 {
    float m[4][4]{};
};

struct Vertex {
    float position[3];
    float color[3];
};

struct SceneConstants {
    Float4x4 world_view_proj;
};

enum class RenderCommandType {
    Clear,
    Draw,
};

struct RenderCommand {
    RenderCommandType type = RenderCommandType::Clear;
    std::vector<Vertex> vertices;
    D3D11_PRIMITIVE_TOPOLOGY topology = D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST;
    Float4x4 world_view_proj{};
    bool depth_enabled = true;
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
    std::vector<Vertex> sky_vertices;
    std::vector<Vertex> ground_vertices;
    std::vector<Vertex> grid_vertices;

    struct ObjectBatch {
        std::vector<Vertex> vertices;
        Float4x4 world{};
    };

    std::vector<ObjectBatch> object_batches;
};

struct ViewerInputState {
    bool move_forward = false;
    bool move_backward = false;
    bool move_left = false;
    bool move_right = false;
    bool move_up = false;
    bool move_down = false;
    bool dragging = false;
    int last_mouse_x = 0;
    int last_mouse_y = 0;
    float camera_yaw = 0.70f;
    float camera_pitch = 0.55f;
    float camera_distance = 30000.0f;
    Float3 camera_target{0.0f, 6000.0f, 0.0f};
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
    UINT dynamic_vertex_capacity = 0;
    ID3D11RasterizerState* rasterizer_state = nullptr;
    ID3D11DepthStencilState* depth_state = nullptr;
    ID3D11DepthStencilState* depth_disabled_state = nullptr;
    UINT back_buffer_width = 0;
    UINT back_buffer_height = 0;
    bool common_pipeline_bound = false;
    D3D11_PRIMITIVE_TOPOLOGY current_topology = D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
    ID3D11DepthStencilState* current_depth_state = nullptr;
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

void update_camera(ViewerInputState& input, float dt_seconds);
bool create_window(Win32Window& window, std::string& error);
void destroy_window(Win32Window& window);
bool create_d3d11(HWND hwnd, D3D11Context& d3d11, std::string& error);
void destroy_d3d11(D3D11Context& d3d11);
bool resize_swap_chain_if_needed(D3D11Context& d3d11, HWND hwnd, UINT width, UINT height, std::string& error);
void update_viewport_from_client_rect(HWND hwnd, ID3D11DeviceContext* context, UINT& out_width, UINT& out_height);
RenderScene build_render_scene(const ViewerInputState& input, UINT width, UINT height, const WorldSnapshot* snapshot);
RenderCommandList record_render_commands(RenderScene scene);
bool execute_render_commands(D3D11Context& d3d11, const RenderCommandList& command_list, RenderFrameStats& out_stats);
void draw_hud_text(HWND hwnd, const ViewerInputState& input, double sim_time, long object_count, const RenderFrameStats& stats);

#endif

} // namespace bvr_sim
