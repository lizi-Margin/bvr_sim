#pragma once

#include "base.hxx"
#include "missile_params.hxx"
#include <array>
#include <optional>
#include <deque>
#include <memory>

namespace bvr_sim {

/// Generic parametric missile model (Model A).
/// Inherits from Missile, uses MissileParams for all configuration.
class MModelA : public Missile {
public:
    // ===== CTOR =====
    MModelA(
        const std::string& uid,
        TeamColor color,
        const std::shared_ptr<SimulatedObject>& parent,
        const std::shared_ptr<SimulatedObject>& friend_obj,
        const std::shared_ptr<SimulatedObject>& target,
        double dt,
        const std::string& missile_model
    ) noexcept;

    // ===== Virtual overrides =====
    void step() noexcept override;

    // ===== Public accessors =====
    const MissileParams& get_params() const noexcept { return params_; }

public:
    // ===== Motion state =====
    double speed;
    std::array<double, 3> posture;  // pitch, yaw, roll

    // ===== Seeker state =====
    double radar_pitch, radar_yaw;
    bool guide_cmd_valid;

    // ===== Signal loss handling =====
    double losstime;
    bool loss;
    std::array<double, 3> _before_loss_real_last_known_target_pos;

    // ===== Guidance commands =====
    std::optional<double> L_beta;  // lateral guidance command
    std::optional<double> L_eps;   // longitudinal guidance command
    std::optional<double> _dbeta_filtered;

private:
    // ===== Parameters =====
    MissileParams params_;

    // ===== Propulsion state =====
    double _t;      // thrust elapsed time
    double _m;      // current mass

    // ===== Control surfaces =====
    double _dtheta; // longitudinal rudder angle rate
    double _dphi;   // lateral rudder angle rate

    // ===== Distance tracking =====
    bool _search_started;
    double _distance_pre;
    std::deque<bool> _distance_increment;
    int _left_t;

    // ===== Filter =====
    // TimeScalarFilter ny_filter{0.1};  // TODO: add if needed

    // ===== Private methods (to be implemented in .cxx) =====
    std::pair<double, double> update_guidance() noexcept;
    void _state_trans(const std::array<double, 2>& action) noexcept;
    void update_aerodynamics() noexcept;
    void update_kinematics() noexcept;
};

} // namespace bvr_sim
