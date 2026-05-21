#include "game_mode.hxx"
#include "game_renderer.hxx"
#include "c3utils/c3utils.hxx"

#include <algorithm>
#include <array>
#include <chrono>
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

void GameMode::run_loop() noexcept {
    auto renderer = create_dx11_renderer();
    if (!renderer) {
        std::lock_guard<std::mutex> lock(state_mutex_);
        last_error_ = "Failed to create DX11 renderer";
        running_ = false;
        return;
    }

    renderer->set_command_submitter(command_submitter_);

    std::string error;
    if (!renderer->initialize(error)) {
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

        const auto now = std::chrono::steady_clock::now();
        const float dt_seconds = std::clamp(
            std::chrono::duration_cast<std::chrono::duration<float>>(now - previous_time).count(),
            0.001f, 0.05f);
        previous_time = now;

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            RendererCameraState cam;
            cam.input_mode = state_.input_mode;
            cam.camera_mode = state_.camera_mode;
            cam.target_uid = state_.target_uid;
            cam.focus_index = state_.focus_index;
            cam.distance = state_.distance;
            cam.yaw = state_.yaw;
            cam.pitch = state_.pitch;
            cam.fov_y = state_.fov_y;
            cam.roll_locked = state_.roll_locked;
            cam.mouse_aim_enabled = state_.mouse_aim_enabled;
            if (state_.target.has_value()) {
                cam.has_target = true;
                cam.target[0] = (*state_.target)[0];
                cam.target[1] = (*state_.target)[1];
                cam.target[2] = (*state_.target)[2];
            }
            renderer->apply_camera_state(cam);
        }

        if (!renderer->process_messages()) {
            break;
        }

        auto snapshot = snapshot_provider_ ? snapshot_provider_() : std::shared_ptr<const WorldSnapshot>();

        renderer->update_input(snapshot.get(), dt_seconds);

        RendererFrameInput frame_input;
        frame_input.snapshot = snapshot.get();
        frame_input.sim_time = snapshot ? snapshot->sim_time : 0.0;
        frame_input.object_count = snapshot ? static_cast<long>(snapshot->objects.size()) : 0L;

        RendererFrameStats frame_stats;
        if (!renderer->render_frame(frame_input, frame_stats)) {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_error_ = "Render frame failed";
            break;
        }

        {
            std::lock_guard<std::mutex> lock(state_mutex_);
            last_sim_time_ = frame_input.sim_time;
            last_object_count_ = frame_input.object_count;
            last_command_count_ = frame_stats.command_count;
            last_draw_calls_ = frame_stats.draw_calls;
            last_vertex_count_ = frame_stats.vertex_count;
            shadows_enabled_ = renderer->get_shadows_enabled();
            material_system_enabled_ = renderer->get_material_system_enabled();

            const RendererCameraState cam = renderer->get_camera_state();
            state_.input_mode = cam.input_mode;
            state_.camera_mode = cam.camera_mode;
            state_.target_uid = cam.target_uid;
            state_.focus_index = cam.focus_index;
            state_.distance = cam.distance;
            state_.yaw = cam.yaw;
            state_.pitch = cam.pitch;
            state_.fov_y = cam.fov_y;
            state_.roll_locked = cam.roll_locked;
            state_.mouse_aim_enabled = cam.mouse_aim_enabled;
            if (cam.has_target) {
                state_.target = std::array<double, 3>{cam.target[0], cam.target[1], cam.target[2]};
            } else {
                state_.target.reset();
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }

    renderer->destroy();
    running_ = false;
}

#endif

} // namespace bvr_sim
