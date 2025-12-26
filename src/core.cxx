#include "core.hxx"
#include "cmd_handler.hxx"
#include "so_pool.hxx"
#include "bsl_pool.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "rubbish_can/SL.hxx"
#include "global_config.hxx"
#include <fstream>
#include <unordered_set>
#include "trace.hxx"

namespace bvr_sim {

SimCore::SimCore(double dt)
    : running_(false),
      paused_(false),
      should_exit_(false),
      acmi_file_path_("./replay.acmi") 
{
    cfg::dt = dt;
    cfg::sim_time = 0.0;

    // init trace
    register_trace();

    // init log
    SL::get("bvr_sim.log", false);

    // truncate acmi file
    truncate_acmi_file();
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

    running_ = true;
    should_exit_ = false;
    sim_thread_ = std::thread(&SimCore::run_loop, this);
}

void SimCore::stop() {
    if (!running_) {
        return;
    }

    should_exit_ = true;
    paused_ = false;
    pause_cv_.notify_all();

    if (sim_thread_.joinable()) {
        sim_thread_.join();
    }

    running_ = false;
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
    }
    BaselinePool::instance().step();
    log();
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
            check(!obj->trashed(), "obj->uid: %s, obj->type: %s is trashed, which is just created", obj->uid.c_str(), SOT_to_string(obj->Type).c_str());
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

}
