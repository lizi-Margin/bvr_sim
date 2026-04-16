#include "dx11_game_viewer.hxx"
#include "dx11_game_viewer_internal.hxx"

#include <algorithm>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

namespace bvr_sim {

DX11GameViewer::DX11GameViewer()
    : running_(false),
      stop_requested_(false),
      supported_(false) {
#ifdef _WIN32
    supported_ = true;
#else
    supported_ = false;
#endif
}

DX11GameViewer::~DX11GameViewer() {
    stop();
}

void DX11GameViewer::set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> provider) {
    snapshot_provider_ = std::move(provider);
}

void DX11GameViewer::set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) {
    command_submitter_ = std::move(submitter);
}

void DX11GameViewer::start() {
    if (running_.load()) {
        return;
    }

    stop_requested_ = false;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }
    viewer_thread_ = std::thread(&DX11GameViewer::run_loop, this);
}

void DX11GameViewer::stop() noexcept {
    stop_requested_ = true;
    if (viewer_thread_.joinable()) {
        viewer_thread_.join();
    }
    running_ = false;
}

bool DX11GameViewer::is_running() const noexcept {
    return running_.load();
}

bool DX11GameViewer::is_supported() const noexcept {
    return supported_.load();
}

json::JSON DX11GameViewer::get_status() const {
    json::JSON status = json::JSON::Make(json::JSON::Class::Object);
    status["running"] = json::Boolean(is_running());
    status["supported"] = json::Boolean(is_supported());
#ifdef _WIN32
    status["platform"] = json::String("windows");
    status["backend"] = json::String("dx11");
#else
    status["platform"] = json::String("linux_or_other");
    status["backend"] = json::String("stub");
#endif

    std::lock_guard<std::mutex> lock(state_mutex_);
    status["last_error"] = json::String(last_error_);
    status["last_sim_time"] = json::Float(last_sim_time_);
    status["last_object_count"] = json::Integral(last_object_count_);
    status["last_command_count"] = json::Integral(last_command_count_);
    status["last_draw_calls"] = json::Integral(last_draw_calls_);
    status["last_vertex_count"] = json::Integral(last_vertex_count_);
    status["shadows_enabled"] = json::Boolean(shadows_enabled_);
    status["material_system_enabled"] = json::Boolean(material_system_enabled_);
    return status;
}

void DX11GameViewer::submit_command(const TelemetryCommand& command) const {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

#ifndef _WIN32

void DX11GameViewer::run_loop() noexcept {
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = "DX11 game viewer is currently implemented for Windows only";
        last_sim_time_ = 0.0;
        last_object_count_ = 0;
        last_command_count_ = 0;
        last_draw_calls_ = 0;
        last_vertex_count_ = 0;
    }
    running_ = false;
}

#else

void DX11GameViewer::run_loop() noexcept {
    Win32Window window;
    D3D11Context d3d11;

    std::string error;
    if (!create_window(window, error)) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = error;
        running_ = false;
        return;
    }

    if (!create_d3d11(window.hwnd, d3d11, error)) {
        destroy_window(window);
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

    auto previous_time = std::chrono::steady_clock::now();

    while (!stop_requested_.load()) {
        MSG msg = {};
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) {
                stop_requested_ = true;
                break;
            }
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }

        const auto now = std::chrono::steady_clock::now();
        const float dt_seconds = std::clamp(
            std::chrono::duration_cast<std::chrono::duration<float>>(now - previous_time).count(),
            0.001f,
            0.05f
        );
        previous_time = now;
        update_camera(window.input, dt_seconds);

        UINT width = 1;
        UINT height = 1;
        update_viewport_from_client_rect(window.hwnd, d3d11.context, width, height);
        if (!resize_swap_chain_if_needed(d3d11, window.hwnd, width, height, error)) {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_error_ = error;
            break;
        }

        auto snapshot = snapshot_provider_ ? snapshot_provider_() : std::shared_ptr<const WorldSnapshot>();
        window.input.snapshot_uids.clear();
        if (snapshot) {
            window.input.snapshot_uids.reserve(snapshot->objects.size());
            for (const auto& object : snapshot->objects) {
                if (object.alive) {
                    window.input.snapshot_uids.push_back(object.uid);
                }
            }
            if (window.input.camera_mode == ViewerInputState::CameraMode::FollowObject) {
                const bool focus_missing = window.input.focus_uid.empty()
                    || std::find(window.input.snapshot_uids.begin(), window.input.snapshot_uids.end(), window.input.focus_uid)
                           == window.input.snapshot_uids.end();
                if (focus_missing) {
                    window.input.focus_uid = window.input.snapshot_uids.empty() ? std::string{} : window.input.snapshot_uids.front();
                }
            }
        } else {
            window.input.focus_uid.clear();
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_sim_time_ = snapshot ? snapshot->sim_time : 0.0;
            last_object_count_ = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;
            shadows_enabled_ = window.input.shadows_enabled;
            material_system_enabled_ = window.input.material_system_enabled;
        }

        const RenderScene scene = build_render_scene(window.input, width, height, snapshot.get());
        const RenderCommandList command_list = record_render_commands(scene);
        RenderFrameStats frame_stats;
        if (!execute_render_commands(d3d11, command_list, frame_stats)) {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_error_ = "DX11 render command execution failed";
            break;
        }

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_command_count_ = frame_stats.command_count;
            last_draw_calls_ = frame_stats.draw_calls;
            last_vertex_count_ = frame_stats.vertex_count;
            shadows_enabled_ = window.input.shadows_enabled;
            material_system_enabled_ = window.input.material_system_enabled;
        }

        d3d11.swap_chain->Present(1, 0);
        draw_hud_text(window.hwnd, window.input, snapshot ? snapshot->sim_time : 0.0, snapshot ? static_cast<long>(snapshot->objects.size()) : 0L, frame_stats);
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    destroy_d3d11(d3d11);
    destroy_window(window);
    running_ = false;
}

#endif

} // namespace bvr_sim
