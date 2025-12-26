#pragma once

#include "rubbish_can/json.hpp"
#include <thread>
#include <atomic>
#include <fstream>
#include <mutex>
#include <condition_variable>

namespace bvr_sim {

class SimCore {
public:
    SimCore(double dt = 0.4);
    ~SimCore();

    SimCore(const SimCore&) = delete;
    SimCore& operator=(const SimCore&) = delete;

    void start();
    void stop();
    void pause();
    void resume();

    void step(int steps = 1);

    json::JSON handle(const std::string& cmd);
    void set_acmi_file_path(const std::string& path);

    bool is_running() const noexcept { return running_; }
    bool is_paused() const noexcept { return paused_; }

    double get_sim_time() const noexcept;
    double get_dt() const noexcept;

private:
    void run_loop();
    void update_physics();
    void log();
    
    std::atomic<bool> running_;
    std::atomic<bool> paused_;
    std::atomic<bool> should_exit_;

    std::thread sim_thread_;
    std::mutex pause_mutex_;
    std::condition_variable pause_cv_;

private:
    void truncate_acmi_file();
    std::string acmi_file_path_;
    std::ofstream acmi_file_;

};

}
