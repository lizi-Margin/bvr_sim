#include "game_mode.hxx"
#include "dx11/game_dx11_internal.hxx"

#include <algorithm>
#include <chrono>
#include <memory>
#include <string>
#include <thread>

namespace bvr_sim {

GameMode::GameMode()
    : running_(false),
      stop_requested_(false),
      supported_(false) {
#ifdef _WIN32
    supported_ = true;
#else
    supported_ = false;
#endif
}

GameMode::~GameMode() {
    stop();
}

void GameMode::set_snapshot_provider(std::function<std::shared_ptr<const WorldSnapshot>()> provider) {
    snapshot_provider_ = std::move(provider);
}

void GameMode::set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) {
    command_submitter_ = std::move(submitter);
}

void GameMode::start() {
    if (running_.load()) {
        return;
    }

    stop_requested_ = false;
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_.clear();
    }
    viewer_thread_ = std::thread(&GameMode::run_loop, this);
}

void GameMode::stop() noexcept {
    stop_requested_ = true;
    if (viewer_thread_.joinable()) {
        viewer_thread_.join();
    }
    running_ = false;
}

bool GameMode::is_running() const noexcept {
    return running_.load();
}

bool GameMode::is_supported() const noexcept {
    return supported_.load();
}

json::JSON GameMode::get_status() const {
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

void GameMode::submit_command(const TelemetryCommand& command) const {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

#ifndef _WIN32

void GameMode::run_loop() noexcept {
    {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = "DX11 Game Mode is currently implemented for Windows only";
        last_sim_time_ = 0.0;
        last_object_count_ = 0;
        last_command_count_ = 0;
        last_draw_calls_ = 0;
        last_vertex_count_ = 0;
    }
    running_ = false;
}

#else

void GameMode::run_loop() noexcept {
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

        if (window.input.mouse_aim_enabled
            && window.input.camera_mode == ViewerInputState::CameraMode::FollowObject
            && !window.input.focus_uid.empty()) {
            const float delta_heading = std::clamp(-window.input.mouse_aim_x, -1.0f, 1.0f);
            const float delta_altitude = std::clamp(-window.input.mouse_aim_y, -1.0f, 1.0f);
            const float delta_speed = 0.0f;

            auto submit_action_component = [this, &window](const char* key, double value) {
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::ObjectDebug;
                command.target_uid = window.input.focus_uid;
                command.payload = json::JSON::Make(json::JSON::Class::Object);
                command.payload["register_key"] = json::String(key);
                command.payload["value"] = json::Float(value);
                submit_command(command);
            };
            auto submit_action_bool = [this, &window](const char* key, bool value) {
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::ObjectDebug;
                command.target_uid = window.input.focus_uid;
                command.payload = json::JSON::Make(json::JSON::Class::Object);
                command.payload["register_key"] = json::String(key);
                command.payload["value"] = json::Boolean(value);
                submit_command(command);
            };

            submit_action_bool("manual_control", true);
            submit_action_component("delta_heading", delta_heading);
            submit_action_component("delta_altitude", delta_altitude);
            submit_action_component("delta_speed", delta_speed);
        }

        const RenderScene scene = build_render_scene(window.input, width, height, snapshot.get());
        RenderCommandList command_list = record_render_commands(scene);
        RenderFrameStats hud_stats;
        for (const auto& command : command_list.commands) {
            if (command.type == RenderCommandType::Draw && !command.vertices.empty()) {
                ++hud_stats.draw_calls;
                hud_stats.vertex_count += static_cast<long>(command.vertices.size());
            }
        }
        append_hud_render_commands(
            command_list,
            width,
            height,
            window.input,
            snapshot ? snapshot->sim_time : 0.0,
            snapshot ? static_cast<long>(snapshot->objects.size()) : 0L,
            hud_stats);
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
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    destroy_d3d11(d3d11);
    destroy_window(window);
    running_ = false;
}

#endif

} // namespace bvr_sim


