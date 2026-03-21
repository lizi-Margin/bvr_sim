#include "base.hxx"
#include "../aircraft/base.hxx"
#include <sstream>
#include <iomanip>

namespace bvr_sim {

Missile::Missile(
    const std::string& uid_,
    const std::string& missile_model_,
    TeamColor color_,
    const std::shared_ptr<SimulatedObject>& parent_,
    const std::shared_ptr<SimulatedObject>& friend_obj_,
    const std::shared_ptr<SimulatedObject>& target_,
    double dt_
) noexcept
    : SimulatedObject(uid_, color_, parent_->position, parent_->velocity, dt_, SOT::Missile),
      missile_model(missile_model_),
      is_done(false),
      is_success(false),
      radar_on(false),
      ir_on(false),
      parent(parent_),
      friend_obj(friend_obj_),
      target(target_),
      last_known_target_pos{0.0, 0.0, 0.0},
      last_known_target_vel{0.0, 0.0, 0.0},
      last_known_target_pos_vis_id(uid + get_new_uuid()),
      log_done_reason("") {

    setup_last_known_target_info();

    last_known_target_pos_vis_id = uid + "0" + get_new_uuid() + "010";
}

void Missile::setup_last_known_target_info() noexcept {
    if (target != nullptr) {
        last_known_target_pos = target->position;
        last_known_target_vel = target->velocity;
    } else {
        last_known_target_pos = {0.0, 0.0, 0.0};
        last_known_target_vel = {0.0, 0.0, 0.0};
    }
}

void Missile::update_target_info() noexcept {
    if (can_track_target()) {
        last_known_target_pos = target->position;
        last_known_target_vel = target->velocity;
    }
}

std::string Missile::log() noexcept {
    std::stringstream ss;
    ss << std::fixed << std::setprecision(6);
    auto [lon, lat, alt] = NWU2LLA(position[0], position[1], position[2]);
    if (is_alive) {
        
        auto [roll_deg, pitch_deg, yaw_deg] = velocity_to_euler(velocity, true);

        std::string color_str = (color == TeamColor::Red) ? "Red" : "Blue";

        ss << uid << ",T=" << lon << "|" << lat << "|" << alt << "|"
        << roll_deg << "|" << -pitch_deg << "|" << -yaw_deg << ","
        << "Name=" << missile_model << ","
        << "Color=" << color_str << ","
        << "Type=Weapon + Missile\n";

        auto [block_lon, block_lat, block_alt] = NWU2LLA(last_known_target_pos[0], last_known_target_pos[1], last_known_target_pos[2]);
        ss << last_known_target_pos_vis_id << ",T=" << block_lon << "|" << block_lat << "|" << block_alt << ","
        << "Name=missile_target, Type=Navaid + Static, Radius=5, Color=" << color_str << ","
        << "Visible=" << 1 << "\n";
            
    } else if (!render_explosion) {
        if (is_success) {
            // ss << "0,Event=Destroyed|" << uid << "|" << '\n';
            ss << "-" + uid + "\n";
            auto explosion_id = uid + "0" + get_new_uuid();
            auto explosion_type = "Small";
            ss << explosion_id << ",T=" << lon << "|" << lat << "|" << alt << ","
            << "Type=Explosion + " << explosion_type << "\n";
        }
        ss << "-" + last_known_target_pos_vis_id + "\n";
        ss << "0,Event=Message|" << uid + get_new_uuid() << "|is_done=" << is_done << "-is_alive=" << is_alive << "-is_success=" << is_success << "-target_uid=" << target->uid << "-done_reason=" << log_done_reason << "\n";

        render_explosion = true;
    }
    return ss.str();
}

}
