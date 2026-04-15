#pragma once

#include "base.hxx"
#include "simulator/param_store.hxx"
#include "simulator/missile/fdm/generic_missile_fdm.hxx"
#include <array>
#include <optional>
#include <deque>

namespace bvr_sim {

class MModelA : public Missile {
public:
    MModelA(
        const std::string& uid,
        const std::string& missile_model,
        TeamColor color,
        const std::shared_ptr<SimulatedObject>& parent,
        const std::shared_ptr<SimulatedObject>& friend_obj,
        const std::shared_ptr<SimulatedObject>& target,
        double dt
    ) noexcept;

    void step() noexcept override;
    bool can_track_target() noexcept override;
    std::array<double, 3> get_rpy() const noexcept override;

    const ParamStore& get_params() const noexcept { return params_; }

public:
    // ===== Seeker state =====
    double radar_pitch, radar_yaw;
    bool guide_cmd_valid;

    // ===== Signal loss handling =====
    double losstime;
    bool loss;
    std::array<double, 3> _before_loss_real_last_known_target_pos;

    // ===== Guidance commands (outputs from update_guidance) =====
    std::optional<double> L_beta;
    std::optional<double> L_eps;
    std::optional<double> _dbeta_filtered;

private:
    // params_ MUST be declared before fdm_ — initializer list order matters
    ParamStore         params_;   // owned by MModelA
    GenericMissileFDM  fdm_;      // holds const ref to params_

    // ===== Mission state =====
    bool              _search_started;
    double            _distance_pre;
    std::deque<bool>  _distance_increment;
    int               _left_t;

    bool _can_track_from(const std::shared_ptr<SimulatedObject>& friend_) const noexcept;
    void _loss_update_target_info() noexcept;
    double K_func(double range_to_target) const noexcept;
    double calculate_min_distance(
        const std::array<double, 3>& missile_pos,
        const std::array<double, 3>& missile_vel,
        const std::array<double, 3>& aircraft_pos,
        const std::array<double, 3>& aircraft_vel,
        double delta_t
    ) const noexcept;
    std::pair<double, double> update_guidance() noexcept;

    static ParamStore _make_params(const std::string& missile_model) noexcept;
};

} // namespace bvr_sim
