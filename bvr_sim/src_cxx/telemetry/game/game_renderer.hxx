#pragma once

#include "../telemetry_command_queue.hxx"
#include "../telemetry_types.hxx"
#include "game_types.hxx"

#include <functional>
#include <memory>
#include <string>

namespace bvr_sim {

struct RendererCameraState {
    std::string input_mode = "follow";   // "follow" | "control"
    std::string camera_mode = "follow";  // "follow" | "free" | "fixed"
    std::string target_uid;
    int focus_index = 0;
    double distance = 500.0;
    double yaw = 0.70;
    double pitch = 0.55;
    double fov_y = 100.0;
    bool roll_locked = true;
    bool mouse_aim_enabled = true;
    bool has_target = false;
    double target[3]{0.0, 0.0, 0.0};
};

struct RendererFrameInput {
    const WorldSnapshot* snapshot = nullptr;
    double sim_time = 0.0;
    long object_count = 0;
};

struct RendererFrameStats {
    long command_count = 0;
    long draw_calls = 0;
    long vertex_count = 0;
};

class IRenderer {
public:
    virtual ~IRenderer() = default;
    virtual bool initialize(std::string& error) = 0;
    virtual void destroy() = 0;

    // Process OS messages; returns false if window was closed
    virtual bool process_messages() = 0;

    // Apply external camera state (from GameMode commands)
    virtual void apply_camera_state(const RendererCameraState& state) = 0;

    // Read back current camera state (for GameMode status reporting)
    virtual RendererCameraState get_camera_state() const = 0;

    // Update input state (camera, focus cycling, action control, pylon/fire)
    virtual void update_input(const WorldSnapshot* snapshot, float dt_seconds) = 0;

    virtual bool render_frame(const RendererFrameInput& input, RendererFrameStats& out_stats) = 0;
    virtual bool is_window_closed() const = 0;

    virtual bool get_shadows_enabled() const = 0;
    virtual bool get_material_system_enabled() const = 0;

    virtual void set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) = 0;
};

std::unique_ptr<IRenderer> create_dx11_renderer();
std::unique_ptr<IRenderer> create_dx12_renderer();

} // namespace bvr_sim
