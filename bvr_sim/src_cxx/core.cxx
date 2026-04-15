#include "core.hxx"
#include "cmd_handler.hxx"
#include "rubbish_can/check.hxx"
#include "so_pool.hxx"
#include "bsl_pool.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "rubbish_can/SL.hxx"
#include "global_config.hxx"
#include "telemetry/telemetry_types.hxx"
#include <fstream>
#include <unordered_set>
#include "trace.hxx"

namespace bvr_sim {

SimCore::SimCore(double dt, const std::string& log_file_path, const std::string& acmi_file_path)
    : running_(false),
      paused_(false),
      should_exit_(false),
      acmi_file_path_(acmi_file_path),
      telemetry_bridge_(std::make_shared<TelemetryBridge>()),
      visualization_server_(std::make_shared<EmbeddedWebServer>())
{
    cfg::dt = dt;
    cfg::sim_time = 0.0;

    // init trace
    register_trace();

    // init log
    SL::init_instance(log_file_path, false);

    // truncate acmi file
    truncate_acmi_file();

    telemetry_bridge_->set_command_handler([this](const TelemetryCommand& command) {
        handle_telemetry_command(command);
    });

    visualization_server_->set_snapshot_provider([this]() {
        return get_telemetry_snapshot();
    });
    visualization_server_->set_diagnostics_provider([this]() {
        return get_visualization_status();
    });
    visualization_server_->set_command_submitter([this](const TelemetryCommand& command) {
        start_telemetry_bridge();
        telemetry_bridge_->submit_command(command);
    });
}

SimCore::~SimCore() {
    stop();
}

void SimCore::start() {
    if (running_) {
        return;
    }

    cfg::sim_time = 0.0;
    truncate_acmi_file();
    start_telemetry_bridge();

    running_ = true;
    should_exit_ = false;
    sim_thread_ = std::thread(&SimCore::run_loop, this);
}

void SimCore::stop() {
    if (!running_) {
        stop_visualization_server();
        stop_telemetry_bridge();
        return;
    }

    should_exit_ = true;
    paused_ = false;
    pause_cv_.notify_all();

    if (sim_thread_.joinable()) {
        sim_thread_.join();
    }

    running_ = false;
    stop_visualization_server();
    stop_telemetry_bridge();
    cfg::sim_time = 0.0;
    if (acmi_file_.is_open()) {
        acmi_file_.flush();
        acmi_file_.close();
    }
}

void SimCore::pause() {
    paused_ = true;
}

void SimCore::resume() {
    paused_ = false;
    pause_cv_.notify_all();
}

void SimCore::step(int steps) {
    if (steps <= 0) {
        return;
    }
    for (int i = 0; i < steps; i++){
        update_physics();
        cfg::sim_time += cfg::dt;
        log();
    }
    BaselinePool::instance().step();
    refresh_telemetry_snapshot();
}

json::JSON SimCore::handle(const std::string& cmd) {
    return CmdHandler::instance().handle(cmd);
}

void SimCore::set_acmi_file_path(const std::string& path) {
    acmi_file_path_ = path;
    if (!running_) {
        truncate_acmi_file();
    }
}

void SimCore::run_loop() {
    // auto frame_duration = std::chrono::duration<double>(dt_);
    auto frame_duration = std::chrono::duration<double>(0.001);

    while (!should_exit_) {
        auto frame_start = std::chrono::high_resolution_clock::now();

        {
            std::unique_lock lock(pause_mutex_);
            pause_cv_.wait(lock, [this] { return !paused_ || should_exit_; });
        }

        if (should_exit_) {
            break;
        }

        step(1);

        auto frame_end = std::chrono::high_resolution_clock::now();
        auto frame_time = frame_end - frame_start;

        if (frame_time < frame_duration) {
            std::this_thread::sleep_for(frame_duration - frame_time);
        }
    }
}

void SimCore::log() {
    auto objects = SOPool::instance().get_all();
    std::string log;
    log.reserve(100);
    log += "#" + std::to_string(cfg::sim_time) + "\n";
    for (auto& obj : objects) {
        if (obj) {
            log += obj->log() + "\n";
        }
    }

    if (acmi_file_.is_open()) {
        acmi_file_ << log;
    } else {
        if (!acmi_file_path_.empty()) {
            SL::get().printf("[SimCore] Failed to log (append) acmi file: %s\n", acmi_file_path_.c_str());
        }
    }
}
void SimCore::update_physics() {
    SL::get().print("===SimCore::update_physics===");
    // colorful::print("===SimCore::update_physics===");
    std::unordered_set<std::string> ticked_uids;
    
    for (auto& obj : SOPool::instance().get_all()) {
        check(obj, "wtf obj from so pool is nullptr");
        SL::get().printf("[SimCore::update_physics] start tick obj->uid: %s, obj->type: %s\n", obj->uid.c_str(), SOT_to_string(obj->Type).c_str());
        // obj->debug_print()
        obj->tick();
        SL::get().printf("[SimCore::update_physics] end tick obj->uid: %s, obj->type: %s\n", obj->uid.c_str(), SOT_to_string(obj->Type).c_str());
        if (obj->trashed()) {
            SL::get().printf("[SimCore::update_physics] trash out obj->uid: %s, obj->type: %s\n", obj->uid.c_str(), SOT_to_string(obj->Type).c_str());
            SOPool::instance().trash_out(obj->uid);
        }
        ticked_uids.insert(obj->uid);
    }

    for (auto& obj : SOPool::instance().get_all()) {
        check(obj, "wtf obj from so pool is nullptr");
        if (ticked_uids.find(obj->uid) == ticked_uids.end()) {
            obj->tick();
            format_check(!obj->trashed(),"obj->uid: %s, obj->type: %s is trashed, which is just created", obj->uid.c_str(), SOT_to_string(obj->Type).c_str());
        }
    }
    SL::get().print("---SimCore::update_physics---");
}

void SimCore::truncate_acmi_file() {
    if (acmi_file_.is_open()) {
        acmi_file_.close();
    }
    if (!acmi_file_path_.empty())
    {
        acmi_file_.open(acmi_file_path_, std::ios_base::out);
        if (acmi_file_.is_open()) {
            acmi_file_ << "FileType=text/acmi/tacview\n";
            acmi_file_ << "FileVersion=2.1\n";
            acmi_file_ << "0,ReferenceTime=2025-12-06T00:00:00Z\n";
        } else {
            SL::get().printf("[SimCore] Failed to truncate (write) acmi file: %s\n", acmi_file_path_.c_str());
        }
    }
}

double SimCore::get_sim_time() const noexcept { return cfg::sim_time; }
double SimCore::get_dt() const noexcept { return cfg::dt; }
bool SimCore::is_telemetry_running() const noexcept {
    return telemetry_bridge_ && telemetry_bridge_->is_running();
}

json::JSON SimCore::get_telemetry_snapshot() const {
    if (!telemetry_bridge_) {
        return json::JSON::Make(json::JSON::Class::Object);
    }

    auto snapshot = telemetry_bridge_->get_latest_snapshot();
    if (!snapshot) {
        return json::JSON::Make(json::JSON::Class::Object);
    }
    return world_snapshot_to_json(*snapshot);
}

json::JSON SimCore::get_telemetry_status() const {
    json::JSON status = json::JSON::Make(json::JSON::Class::Object);
    status["telemetry_running"] = json::Boolean(is_telemetry_running());
    status["sim_running"] = json::Boolean(is_running());
    status["sim_paused"] = json::Boolean(is_paused());
    status["sim_time"] = json::Float(get_sim_time());
    status["dt"] = json::Float(get_dt());
    return status;
}

void SimCore::start_telemetry_bridge() {
    if (!telemetry_bridge_) {
        telemetry_bridge_ = std::make_shared<TelemetryBridge>();
    }
    telemetry_bridge_->start();
}

void SimCore::stop_telemetry_bridge() {
    if (telemetry_bridge_) {
        telemetry_bridge_->stop();
    }
}

void SimCore::refresh_telemetry_snapshot() {
    if (telemetry_bridge_) {
        telemetry_bridge_->refresh_once();
    }
}

void SimCore::set_visualization_static_root(const std::string& static_root) {
    if (!visualization_server_) {
        visualization_server_ = std::make_shared<EmbeddedWebServer>();
    }
    visualization_server_->set_static_root(static_root);
}

bool SimCore::is_visualization_server_running() const noexcept {
    return visualization_server_ && visualization_server_->is_running();
}

void SimCore::start_visualization_server(int port) {
    if (!visualization_server_) {
        visualization_server_ = std::make_shared<EmbeddedWebServer>();
    }
    start_telemetry_bridge();
    visualization_server_->start(port);
}

void SimCore::stop_visualization_server() {
    if (visualization_server_) {
        visualization_server_->stop();
    }
}

json::JSON SimCore::get_visualization_status() const {
    json::JSON status = json::JSON::Make(json::JSON::Class::Object);
    status["server_running"] = json::Boolean(is_visualization_server_running());
    status["telemetry_running"] = json::Boolean(is_telemetry_running());
    status["port"] = json::Integral(visualization_server_ ? visualization_server_->get_port() : 0L);
    status["base_url"] = json::String(visualization_server_ ? visualization_server_->get_base_url() : "");
    status["frontend_url"] = json::String(visualization_server_ ? visualization_server_->get_frontend_url() : "");
    status["static_root"] = json::String(visualization_server_ ? visualization_server_->get_static_root() : "");
    status["frontend_available"] = json::Boolean(visualization_server_ && visualization_server_->is_static_frontend_available());
    status["client_count"] = json::Integral(visualization_server_ ? static_cast<long>(visualization_server_->get_client_count()) : 0L);
    status["telemetry"] = telemetry_bridge_ ? telemetry_bridge_->get_diagnostics() : json::JSON::Make(json::JSON::Class::Object);
    return status;
}

void SimCore::handle_telemetry_command(const TelemetryCommand& command) {
    if (command.kind == TelemetryCommandKind::Pause) {
        pause();
        return;
    }
    if (command.kind == TelemetryCommandKind::Resume) {
        resume();
        return;
    }
    if (command.kind == TelemetryCommandKind::Step) {
        int step_count = 1;
        if (command.payload.JSONType() == json::JSON::Class::Integral) {
            step_count = static_cast<int>(command.payload.ToInt());
        } else if (command.payload.JSONType() == json::JSON::Class::Object
            && command.payload.hasKey("steps", json::JSON::Class::Integral)) {
            step_count = static_cast<int>(command.payload.at("steps").ToInt());
        }
        format_check(step_count > 0, "Telemetry step command requires positive steps");
        step(step_count);
        return;
    }
}

}
