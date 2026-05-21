#include "game_mode.hxx"
#include "dx11/game_dx11_internal.hxx"
#include "c3utils/c3utils.hxx"

#include <algorithm>
#include <array>
#include <chrono>
#include <memory>
#include <optional>
#include <string>
#include <thread>
#include <vector>

namespace bvr_sim {

namespace {

std::optional<double> json_number_at(const json::JSON& payload, const char* key) {
    if (!payload.hasKey(key)) {
        return std::nullopt;
    }
    const auto& value = payload.at(key);
    if (value.JSONType() == json::JSON::Class::Floating) {
        return value.ToFloat();
    }
    if (value.JSONType() == json::JSON::Class::Integral) {
        return static_cast<double>(value.ToInt());
    }
    return std::nullopt;
}

std::optional<bool> json_bool_at(const json::JSON& payload, const char* key) {
    if (!payload.hasKey(key) || payload.at(key).JSONType() != json::JSON::Class::Boolean) {
        return std::nullopt;
    }
    return payload.at(key).ToBool();
}

std::optional<std::array<double, 3>> json_array3_at(const json::JSON& payload, const char* key) {
    if (!payload.hasKey(key) || payload.at(key).JSONType() != json::JSON::Class::Array) {
        return std::nullopt;
    }
    auto arr = payload.at(key);
    if (arr.size() != 3) {
        return std::nullopt;
    }
    std::array<double, 3> out{0.0, 0.0, 0.0};
    for (size_t i = 0; i < 3; ++i) {
        if (arr[i].JSONType() == json::JSON::Class::Floating) {
            out[i] = arr[i].ToFloat();
        } else if (arr[i].JSONType() == json::JSON::Class::Integral) {
            out[i] = static_cast<double>(arr[i].ToInt());
        } else {
            return std::nullopt;
        }
    }
    return out;
}

} // namespace

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

json::JSON GameMode::state_to_json(const GameModeState& state) {
    json::JSON out = json::JSON::Make(json::JSON::Class::Object);
    out["input_mode"] = json::String(state.input_mode);
    out["camera_mode"] = json::String(state.camera_mode);
    out["target_uid"] = json::String(state.target_uid);
    out["focus_index"] = json::Integral(state.focus_index);
    out["distance"] = json::Float(state.distance);
    out["yaw"] = json::Float(state.yaw);
    out["pitch"] = json::Float(state.pitch);
    out["fov_y"] = json::Float(state.fov_y);
    out["roll_locked"] = json::Boolean(state.roll_locked);
    out["mouse_aim_enabled"] = json::Boolean(state.mouse_aim_enabled);
    if (state.target.has_value()) {
        json::JSON target = json::JSON::Make(json::JSON::Class::Array);
        target.append(json::Float((*state.target)[0]));
        target.append(json::Float((*state.target)[1]));
        target.append(json::Float((*state.target)[2]));
        out["target"] = target;
    }
    return out;
}

void GameMode::apply_state_command(const TelemetryCommand& command) {
    if (command.kind != TelemetryCommandKind::SetGameCamera) {
        return;
    }
    if (command.payload.JSONType() != json::JSON::Class::Object) {
        return;
    }

    std::lock_guard<std::mutex> lock(state_mutex_);
    const auto& payload = command.payload;
    if (payload.hasKey("input_mode", json::JSON::Class::String)) {
        const std::string mode = payload.at("input_mode").ToString();
        if (mode == "follow" || mode == "control") {
            state_.input_mode = mode;
        }
    }
    if (payload.hasKey("mode", json::JSON::Class::String)) {
        const std::string mode = payload.at("mode").ToString();
        if (mode == "follow" || mode == "fixed" || mode == "free") {
            state_.camera_mode = mode;
        }
    }
    if (payload.hasKey("camera_mode", json::JSON::Class::String)) {
        const std::string mode = payload.at("camera_mode").ToString();
        if (mode == "follow" || mode == "fixed" || mode == "free") {
            state_.camera_mode = mode;
        }
    }
    if (!command.target_uid.empty()) {
        state_.target_uid = command.target_uid;
    }
    if (payload.hasKey("target_uid", json::JSON::Class::String)) {
        state_.target_uid = payload.at("target_uid").ToString();
    }
    if (payload.hasKey("focus_index", json::JSON::Class::Integral)) {
        state_.focus_index = static_cast<int>(payload.at("focus_index").ToInt());
    }
    if (auto value = json_number_at(payload, "distance")) {
        state_.distance = std::clamp(*value, 50.0, 1000000.0);
    }
    if (auto value = json_number_at(payload, "yaw")) {
        state_.yaw = *value;
    }
    if (auto value = json_number_at(payload, "pitch")) {
        state_.pitch = std::clamp(*value, -1.45, 1.45);
    }
    if (auto value = json_number_at(payload, "fov_y")) {
        state_.fov_y = std::clamp(*value, 20.0, 120.0);
    }
    if (auto value = json_bool_at(payload, "roll_locked")) {
        state_.roll_locked = *value;
    }
    if (auto value = json_bool_at(payload, "mouse_aim_enabled")) {
        state_.mouse_aim_enabled = *value;
    }
    if (auto value = json_array3_at(payload, "target")) {
        state_.target = *value;
    }
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
    status["state"] = state_to_json(state_);
    return status;
}

void GameMode::submit_command(const TelemetryCommand& command) const {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

void GameMode::queue_viewer_command(const TelemetryCommand& command) {
    apply_state_command(command);
    viewer_command_queue_.push(command);
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

namespace {

void apply_game_mode_state_to_input(const GameMode::GameModeState& state, ViewerInputState& input) {
    input.input_mode = state.input_mode == "control"
        ? ViewerInputState::InputMode::Control
        : ViewerInputState::InputMode::Follow;

    if (state.camera_mode == "follow") {
        input.camera_mode = ViewerInputState::CameraMode::FollowObject;
        input.focus_uid = state.target_uid;
        input.focus_cycle_index = state.target_uid.empty() ? state.focus_index : -1;
    } else {
        input.camera_mode = ViewerInputState::CameraMode::Free;
        input.focus_uid.clear();
        input.focus_cycle_index = -1;
    }

    input.camera_distance = static_cast<float>(state.distance);
    input.camera_yaw = static_cast<float>(state.yaw);
    input.camera_pitch = static_cast<float>(state.pitch);
    input.camera_fov_y = static_cast<float>(state.fov_y);
    input.camera_roll_locked = state.roll_locked;
    input.mouse_aim_enabled = state.mouse_aim_enabled;
    if (state.target.has_value()) {
        input.camera_target = Float3{
            static_cast<float>((*state.target)[0]),
            static_cast<float>((*state.target)[1]),
            static_cast<float>((*state.target)[2])};
    }
}

GameMode::GameModeState make_state_from_input(const ViewerInputState& input) {
    GameMode::GameModeState state;
    state.input_mode = input.input_mode == ViewerInputState::InputMode::Control ? "control" : "follow";
    state.camera_mode = input.camera_mode == ViewerInputState::CameraMode::FollowObject ? "follow" : "free";
    state.target_uid = input.focus_uid;
    state.focus_index = input.focus_cycle_index;
    state.distance = input.camera_distance;
    state.yaw = input.camera_yaw;
    state.pitch = input.camera_pitch;
    state.fov_y = input.camera_fov_y;
    state.roll_locked = input.camera_roll_locked;
    state.mouse_aim_enabled = input.mouse_aim_enabled;
    state.target = std::array<double, 3>{
        input.camera_target.x,
        input.camera_target.y,
        input.camera_target.z};
    return state;
}

} // namespace

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
        while (auto command = viewer_command_queue_.try_pop()) {
            apply_state_command(*command);
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            apply_game_mode_state_to_input(state_, window.input);
        }

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
            window.input.focus_cycle_requested = false;
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

            if (window.input.focus_cycle_requested) {
                const int slot_count = object_count + 1; // object slots + one free camera slot
                int next_index = window.input.focus_cycle_index + 1;
                if (next_index >= slot_count) {
                    next_index = -1;
                }
                window.input.focus_cycle_index = next_index;
                window.input.focus_uid.clear();
                window.input.focus_cycle_requested = false;
            }

            if (window.input.focus_cycle_index >= 0 && window.input.focus_cycle_index < object_count) {
                window.input.focus_uid = window.input.snapshot_uids[static_cast<size_t>(window.input.focus_cycle_index)];
                window.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
            } else if (window.input.input_mode == ViewerInputState::InputMode::Follow
                && window.input.camera_mode == ViewerInputState::CameraMode::FollowObject) {
                window.input.focus_cycle_index = 0;
                window.input.focus_uid = window.input.snapshot_uids.front();
                window.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
            } else {
                window.input.focus_cycle_index = -1;
                window.input.focus_uid.clear();
                window.input.camera_mode = ViewerInputState::CameraMode::Free;
            }
        }
        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            auto updated_state = make_state_from_input(window.input);
            if (state_.camera_mode == "fixed" && updated_state.camera_mode == "free") {
                updated_state.camera_mode = "fixed";
            }
            state_ = updated_state;
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
                    const float cy = std::cos(window.input.aim_yaw);
                    const float sy = std::sin(window.input.aim_yaw);
                    const float cp = std::cos(window.input.aim_pitch);
                    const float sp = std::sin(window.input.aim_pitch);

                    // camera forward in viewer frame, then convert viewer(N,U,W) -> NWU
                    const float fwd_n = -cp * cy;
                    const float fwd_w = -cp * sy;
                    const float fwd_u = -sp;

                    const float desired_heading = std::atan2(fwd_w, fwd_n);
                    const float desired_pitch = -std::atan2(fwd_u, std::sqrt(fwd_n * fwd_n + fwd_w * fwd_w));

                    const float current_yaw = static_cast<float>(focused_it->orientation[2]);
                    const float heading_err = static_cast<float>(c3utils::norm_pi(desired_heading - current_yaw));

                    const float max_heading = static_cast<float>(c3utils::deg2rad(85.0));
                    const float max_pitch = static_cast<float>(c3utils::deg2rad(45));
                    delta_heading = std::clamp(heading_err / max_heading, -1.0f, 1.0f);
                    delta_altitude = std::clamp(-(desired_pitch / max_pitch), -1.0f, 1.0f);
                }
            }

            auto submit_action_component = [this, &window, kGameModeActionPenalty](const char* key, double value) {
                json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
                kv[key] = json::Float(value);
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::Command;
                command.target_uid = window.input.focus_uid;
                command.payload = json::String(
                    "setp " + window.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
                submit_command(command);
            };
            auto submit_action_component_null = [this, &window, kGameModeActionPenalty](const char* key) {
                json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
                kv[key] = json::JSON();
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::Command;
                command.target_uid = window.input.focus_uid;
                command.payload = json::String(
                    "setp " + window.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
                submit_command(command);
            };
            auto submit_action_component_json = [this, &window, kGameModeActionPenalty](const char* key, const json::JSON& value) {
                json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
                kv[key] = value;
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::Command;
                command.target_uid = window.input.focus_uid;
                command.payload = json::String(
                    "setp " + window.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
                submit_command(command);
            };

            const float aileron_cmd = window.input.ctrl_aileron_right ? (window.input.ctrl_aileron_left ? 0.0f : 1.0f)
                                                                       : (window.input.ctrl_aileron_left ? -1.0f : 0.0f);
            const float elevator_cmd = window.input.ctrl_elevator_up ? (window.input.ctrl_elevator_down ? 0.0f : 1.0f)
                                                                      : (window.input.ctrl_elevator_down ? -1.0f : 0.0f);
            const float rudder_cmd = window.input.ctrl_rudder_right ? (window.input.ctrl_rudder_left ? 0.0f : -1.0f)
                                                                     : (window.input.ctrl_rudder_left ? 1.0f : 0.0f);
            const bool any_surface_key_pressed =
                window.input.ctrl_aileron_left || window.input.ctrl_aileron_right
                || window.input.ctrl_elevator_up || window.input.ctrl_elevator_down
                || window.input.ctrl_rudder_left || window.input.ctrl_rudder_right;
            action_control_uid_ = window.input.focus_uid;
            submit_action_component("delta_heading", delta_heading);
            submit_action_component("delta_altitude", delta_altitude);
            submit_action_component("delta_speed", delta_speed);
            if (any_surface_key_pressed) {
                if (snapshot) {
                    auto focused_it = std::find_if(
                        snapshot->objects.begin(),
                        snapshot->objects.end(),
                        [&window](const TelemetryObjectState& obj) { return obj.uid == window.input.focus_uid; });
                    if (focused_it != snapshot->objects.end()) {
                        window.input.aim_yaw = static_cast<float>(
                            c3utils::norm_pi(static_cast<float>(focused_it->orientation[2]) - static_cast<float>(c3utils::pi)));
                        window.input.aim_pitch = static_cast<float>(focused_it->orientation[1]);
                        window.input.aim_pitch = std::clamp(window.input.aim_pitch, -1.45f, 1.45f);
                    }
                }
                submit_action_component("aileron_cmd", aileron_cmd);
                submit_action_component("elevator_cmd", elevator_cmd);
                submit_action_component("rudder_cmd", rudder_cmd);
            } else {
                submit_action_component_null("aileron_cmd");
                submit_action_component_null("elevator_cmd");
                submit_action_component_null("rudder_cmd");
            }

            std::vector<std::string> selectable_pylons;
            if (snapshot) {
                auto focused_it = std::find_if(
                    snapshot->objects.begin(),
                    snapshot->objects.end(),
                    [&window](const TelemetryObjectState& obj) { return obj.uid == window.input.focus_uid; });
                if (focused_it != snapshot->objects.end()) {
                    const json::JSON& reg = focused_it->debug_register;
                    if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("pylon_mounts", json::JSON::Class::Object)) {
                        const auto pylon_mounts = reg.at("pylon_mounts");
                        for (const auto& kv : pylon_mounts.ObjectRange()) {
                            selectable_pylons.push_back(kv.first);
                        }
                    }
                }
            }
            if (!selectable_pylons.empty()) {
                if (window.input.selected_pylon_name.empty()
                    || std::find(selectable_pylons.begin(), selectable_pylons.end(), window.input.selected_pylon_name) == selectable_pylons.end()) {
                    window.input.selected_pylon_name = selectable_pylons.front();
                }
                if (window.input.pylon_cycle_requested) {
                    auto it = std::find(selectable_pylons.begin(), selectable_pylons.end(), window.input.selected_pylon_name);
                    size_t idx = 0;
                    if (it != selectable_pylons.end()) {
                        idx = static_cast<size_t>(std::distance(selectable_pylons.begin(), it));
                        idx = (idx + 1) % selectable_pylons.size();
                    }
                    window.input.selected_pylon_name = selectable_pylons[idx];
                }
            } else {
                window.input.selected_pylon_name.clear();
            }
            window.input.pylon_cycle_requested = false;

            bool fire_emitted = false;
            if (window.input.fire_once_requested && snapshot) {
                auto focused_it = std::find_if(
                    snapshot->objects.begin(),
                    snapshot->objects.end(),
                    [&window](const TelemetryObjectState& obj) { return obj.uid == window.input.focus_uid; });
                if (focused_it != snapshot->objects.end()) {
                    const json::JSON& reg = focused_it->debug_register;
                    std::string weapon_spec;
                    if (!window.input.selected_pylon_name.empty()
                        && reg.JSONType() == json::JSON::Class::Object
                        && reg.hasKey("pylon_mounts", json::JSON::Class::Object)) {
                        const auto pylon_mounts = reg.at("pylon_mounts");
                        if (pylon_mounts.hasKey(window.input.selected_pylon_name, json::JSON::Class::String)) {
                            weapon_spec = pylon_mounts.at(window.input.selected_pylon_name).ToString();
                        }
                    }
                    std::string target_uid;
                    if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("enemies_lock", json::JSON::Class::Array)) {
                        const auto enemies_lock = reg.at("enemies_lock");
                        for (const auto& enm : enemies_lock.ArrayRange()) {
                            if (enm.JSONType() == json::JSON::Class::String) {
                                target_uid = enm.ToString();
                                if (!target_uid.empty()) {
                                    break;
                                }
                            }
                        }
                    }

                    if (!weapon_spec.empty() && !target_uid.empty()) {
                        json::JSON fire_obj = json::JSON::Make(json::JSON::Class::Object);
                        fire_obj["target_uid"] = json::String(target_uid);
                        fire_obj["weapon_spec"] = json::String(weapon_spec);
                        submit_action_component_json("fire", fire_obj);
                        fire_emitted = true;
                    }
                }
            }
            if (!fire_emitted) {
                submit_action_component_null("fire");
            }
            window.input.fire_once_requested = false;
        } else {
            if (!action_control_uid_.empty()) {
                auto submit_clear_for_uid = [this, kGameModeActionPenalty](const std::string& uid, const char* key) {
                    json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
                    kv[key] = json::JSON();
                    TelemetryCommand command;
                    command.kind = TelemetryCommandKind::Command;
                    command.target_uid = uid;
                    command.payload = json::String(
                        "setp " + uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
                    submit_command(command);
                };
                submit_clear_for_uid(action_control_uid_, "aileron_cmd");
                submit_clear_for_uid(action_control_uid_, "elevator_cmd");
                submit_clear_for_uid(action_control_uid_, "rudder_cmd");
                submit_clear_for_uid(action_control_uid_, "fire");
            }
            window.input.fire_once_requested = false;
            window.input.pylon_cycle_requested = false;
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
            snapshot.get(),
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
