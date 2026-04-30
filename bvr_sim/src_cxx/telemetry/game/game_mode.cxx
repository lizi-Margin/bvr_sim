#include "game_mode.hxx"
#include "dx11/game_dx11_internal.hxx"
#include "c3utils/c3utils.hxx"

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
        }

        const int object_count = static_cast<int>(window.input.snapshot_uids.size());
        if (object_count <= 0) {
            window.input.focus_cycle_index = -1;
            window.input.focus_uid.clear();
            window.input.camera_mode = ViewerInputState::CameraMode::Free;
        } else {
            if (!window.input.focus_uid.empty()) {
                auto it = std::find(window.input.snapshot_uids.begin(), window.input.snapshot_uids.end(), window.input.focus_uid);
                if (it != window.input.snapshot_uids.end()) {
                    window.input.focus_cycle_index = static_cast<int>(std::distance(window.input.snapshot_uids.begin(), it));
                } else {
                    window.input.focus_cycle_index = -1;
                    window.input.focus_uid.clear();
                }
            }

            if (window.input.focus_cycle_index >= 0 && window.input.focus_cycle_index < object_count) {
                window.input.focus_uid = window.input.snapshot_uids[static_cast<size_t>(window.input.focus_cycle_index)];
                window.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
            } else {
                window.input.focus_cycle_index = -1;
                window.input.focus_uid.clear();
                window.input.camera_mode = ViewerInputState::CameraMode::Free;
            }
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_sim_time_ = snapshot ? snapshot->sim_time : 0.0;
            last_object_count_ = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;
            shadows_enabled_ = window.input.shadows_enabled;
            material_system_enabled_ = window.input.material_system_enabled;
        }

        constexpr int kGameModeActionPenalty = -1;
        if (window.input.mouse_aim_enabled
            && window.input.input_mode == ViewerInputState::InputMode::Control
            && window.input.camera_mode == ViewerInputState::CameraMode::FollowObject
            && !window.input.focus_uid.empty()) {
            float delta_heading = 0.0f;
            float delta_altitude = 0.0f;
            const float delta_speed = 0.0f;

            if (snapshot) {
                auto focused_it = std::find_if(
                    snapshot->objects.begin(),
                    snapshot->objects.end(),
                    [&window](const TelemetryObjectState& obj) { return obj.uid == window.input.focus_uid; });
                if (focused_it != snapshot->objects.end()) {
                    const float cy = std::cos(window.input.camera_yaw);
                    const float sy = std::sin(window.input.camera_yaw);
                    const float cp = std::cos(window.input.camera_pitch);
                    const float sp = std::sin(window.input.camera_pitch);

                    // camera forward in viewer frame, then convert viewer(N,U,W) -> NWU
                    const float fwd_n = -cp * cy;
                    const float fwd_w = -cp * sy;
                    const float fwd_u = -sp;

                    const float desired_heading = std::atan2(fwd_w, fwd_n);
                    const float desired_pitch = -std::atan2(fwd_u, std::sqrt(fwd_n * fwd_n + fwd_w * fwd_w));

                    const float current_pitch = static_cast<float>(focused_it->orientation[1]);
                    const float current_yaw = static_cast<float>(focused_it->orientation[2]);
                    const float heading_err = static_cast<float>(c3utils::norm_pi(desired_heading - current_yaw));
                    const float pitch_err = desired_pitch - current_pitch;

                    const float max_heading = static_cast<float>(c3utils::deg2rad(85.0));
                    const float max_pitch = static_cast<float>(c3utils::deg2rad(45.0));
                    delta_heading = std::clamp(heading_err / max_heading, -1.0f, 1.0f);
                    delta_altitude = std::clamp(-(pitch_err / max_pitch), -1.0f, 1.0f);
                }
            }

            auto submit_action_component = [this, &window, kGameModeActionPenalty](const char* key, double value) {
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::ObjectDebug;
                command.target_uid = window.input.focus_uid;
                command.payload = json::JSON::Make(json::JSON::Class::Object);
                command.payload["register_key"] = json::String(key);
                command.payload["value"] = json::Float(value);
                command.payload["penalty"] = json::Integral(kGameModeActionPenalty);
                submit_command(command);
            };
            action_control_uid_ = window.input.focus_uid;
            submit_action_component("delta_heading", delta_heading);
            submit_action_component("delta_altitude", delta_altitude);
            submit_action_component("delta_speed", delta_speed);
        } else {
            action_control_uid_.clear();
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


