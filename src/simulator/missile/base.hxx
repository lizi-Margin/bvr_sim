#pragma once

#include "../simulator.hxx"
#include <string>
#include <array>
#include <memory>

namespace bvr_sim {

class Aircraft;

class Missile : public SimulatedObject {
public:    
    std::string missile_model;
    bool is_done;
    bool is_success;

    bool radar_on;
    bool ir_on;

    std::shared_ptr<SimulatedObject> parent;
    std::shared_ptr<SimulatedObject> friend_obj;
    std::shared_ptr<SimulatedObject> target;


protected:
    std::array<double, 3> last_known_target_pos;
    std::array<double, 3> last_known_target_vel;

    std::string last_known_target_pos_vis_id;
    std::string log_done_reason;

public:
    Missile(
        const std::string& uid_,
        const std::string& missile_model_,
        TeamColor color_,
        const std::shared_ptr<SimulatedObject>& parent_,
        const std::shared_ptr<SimulatedObject>& friend_obj_,
        const std::shared_ptr<SimulatedObject>& target_,
        double dt_ = 0.1
    ) noexcept;

    virtual ~Missile() noexcept = default;

    virtual void step() override = 0;

    virtual bool can_track_target() noexcept { return true; };

    virtual void update_target_info() noexcept;

    std::string log()noexcept override;

    const std::array<double, 3>& get_last_known_target_pos() const noexcept { return last_known_target_pos; }
    const std::array<double, 3>& get_last_known_target_vel() const noexcept { return last_known_target_vel; }
    const std::string& get_log_done_reason() const noexcept { return log_done_reason; }


protected:
    void setup_last_known_target_info() noexcept;
};

}
