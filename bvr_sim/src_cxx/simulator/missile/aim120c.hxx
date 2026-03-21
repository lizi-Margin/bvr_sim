#pragma once

#include "base.hxx"
#include "missile_aerodynamics.hxx"
#include <deque>
#include <optional>

namespace bvr_sim {

class Aircraft;
class GroundUnit;

struct MissileParameter {
    double thrust;
    double t_max;
    double t_thrust;
    double Length;
    double Diameter;
    double m0;
    double dm;
    double K;
    double nyz_max;
};

constexpr MissileParameter default_missile_parameter = {
    16325.0,
    300.0,
    8.0,
    3.65,
    0.178,
    161.48,
    6.41,
    3.0,
    10.0
};

double signed_angle(const std::array<double, 3>& from_direction, const std::array<double, 3>& to_direction) noexcept;

class AIM120C : public Missile {
public:
    double speed;
    std::array<double, 3> posture;

    bool guide_cmd_valid;
    double radar_pitch;
    double radar_yaw;
    double losstime;
    bool loss;

    // AIM120C* radar;

    std::optional<double> L_beta;
    std::optional<double> L_eps;

    MissileAerodynamics aero;

private:
    double _search_fov;
    double _search_range;
    double _search_start_range;
    bool _search_started;
    double _track_gimbal_limit;

    double _g;
    double _t_max;
    double _t_thrust;
    double _thrust;
    double _Length;
    double _Diameter;
    double _m0;
    double _dm;
    double _K;
    double _nyz_max;
    double _Rc;
    double _mach_min;
    double _v_min;

    double _t;
    double _m;
    double _dtheta;
    double _dphi;
    double _distance_pre;
    std::deque<bool> _distance_increment;
    int _left_t;
    std::optional<double> _dbeta_filtered;

    std::array<double, 3> _before_loss_real_last_known_target_pos;

public:
    AIM120C(
        const std::string& uid,
        TeamColor color,
        const std::shared_ptr<SimulatedObject>& parent,
        const std::shared_ptr<SimulatedObject>& friend_obj,
        const std::shared_ptr<SimulatedObject>& target,
        double dt = 0.1,
        std::optional<double> t_thrust_override = std::nullopt
    ) noexcept;

    virtual ~AIM120C() noexcept = default;

    void step() noexcept override;

    bool can_track_target() noexcept override;

    double K_func(double Rxyz) const noexcept;

    double calculate_min_distance(
        const std::array<double, 3>& missile_pos,
        const std::array<double, 3>& missile_vel,
        const std::array<double, 3>& aircraft_pos,
        const std::array<double, 3>& aircraft_vel,
        double delta_t = 0.016
    ) const noexcept;

private:
    bool _can_track_from(const std::shared_ptr<SimulatedObject>& friend_) const noexcept;

    void _loss_update_target_info() noexcept;

    std::pair<std::array<double, 2>, double> _guidance() noexcept;

    void _state_trans_eula(const std::array<double, 2>& action) noexcept;

    void _state_trans(const std::array<double, 2>& action) noexcept;

};

}
