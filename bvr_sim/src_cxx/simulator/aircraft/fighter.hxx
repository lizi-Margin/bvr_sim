#pragma once

#include "base.hxx"
#include "fdm/ac_fdm.hxx"
#include "fdm/simple_fdm.hxx"
#include "fdm/jsbsim_fdm.hxx"
#include <string>
#include <memory>
#include <map>
#include <any>
#include "rl/action_space.hxx"
#include <optional>
#include "player_flight.hxx"

namespace bvr_sim {

class Missile;

class Fighter : public Aircraft {
private:
    double _t;
    std::unique_ptr<AircraftFDM> fdm;
    std::optional<ActionSpace> pilot_input_;
    std::optional<PlayerFlightIntent> player_intent_;
    PlayerFlightController player_controller_;

public:
    double min_shoot_interval;
    double last_shoot_time;

public:
    Fighter(
        const std::string& uid_,
        const std::string& model_,
        TeamColor color_,
        const std::array<double, 3>& position_,
        const std::array<double, 3>& velocity_,
        double dt_ = 0.1,
        const std::string& fdm_type = "simple"
    );

    ~Fighter() noexcept override = default;

    // 飞机状态是否可以开火
    bool can_shoot() const noexcept override;
    // 飞机能不能探测到敌人
    bool can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept override;

    // 标准的物理步进，从Register中读取控制动作
    // 控制动作key: delta_heading(double), delta_altitude(double), delta_speed(double)
    // 发射动作key: fire(map_ss with target_uid and weapon_name)
    void step() override;
    // Persistent human/in-process input; training behavior stays unchanged otherwise.
    void set_pilot_input(double heading, double climb, double throttle,
                         std::optional<double> aileron = std::nullopt,
                         std::optional<double> elevator = std::nullopt,
                         std::optional<double> roll_rate = std::nullopt);
    std::map<std::string,double> visual_properties() const { return fdm->visual_properties(); }
    void configure_player_flight(const PlayerFlightProfile& p){player_controller_.configure(p);}
    PlayerFlightProfile player_flight_profile() const{return player_controller_.profile();}
    std::optional<double> player_throttle() const {
        auto state=player_controller_.state();return state.active?std::optional<double>(state.controls.throttle):std::nullopt;
    }
    void set_player_flight(const PlayerFlightIntent& intent){
        validate_player_intent(intent);auto profile=player_controller_.profile();
        if(!player_intent_)player_controller_.configure(profile);
        player_intent_=intent;pilot_input_.reset();
    }
    PlayerFlightState player_flight_state() const {
        auto s=player_controller_.state();s.measured=fdm->flight_measurements();
        s.direction_error=player_math::angle(s.target_direction,s.measured.velocity);
        s.body_direction_error=player_math::angle(s.target_direction,player_math::axes(s.measured.orientation)[0]);
        return s;
    }

    double get_speed() const noexcept override;
    double get_heading() const noexcept override;
    double get_yaw() const noexcept override;
    double get_pitch() const noexcept override;
    double get_roll() const noexcept override;
    std::array<double, 3> get_rpy() const noexcept override;

    virtual std::string log() noexcept override { return Aircraft::log() + fdm->log();}

private:
    void initialize_fdm(const std::string& fdm_type);
};

}
