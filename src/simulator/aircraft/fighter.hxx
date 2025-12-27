#pragma once

#include "base.hxx"
#include "fdm/base.hxx"
#include "fdm/simple_fdm.hxx"
#include "fdm/jsbsim_fdm.hxx"
#include <string>
#include <memory>
#include <map>
#include <any>

namespace bvr_sim {

class Missile;

class Fighter : public Aircraft {
private:
    double _t;
    std::unique_ptr<BaseFDM> fdm;

public:
    double min_shoot_interval;
    double last_shoot_time;

public:
    Fighter(
        const std::string& uid_,
        TeamColor color_,
        const std::array<double, 3>& position_,
        const std::array<double, 3>& velocity_,
        double dt_ = 0.1,
        const std::string& fdm_type = "simple"
    ) noexcept;

    ~Fighter() noexcept override = default;

    // 飞机状态是否可以开火
    bool can_shoot() const noexcept override;
    // 飞机能不能探测到敌人
    bool can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept override;

    // 标准的物理步进，从Register中读取控制动作
    // 控制动作key: delta_heading(double), delta_altitude(double), delta_speed(double)
    // 发射动作key: fire(map_ss with target_uid and weapon_name)
    void step() override;

    double get_speed() const noexcept override;
    double get_heading() const noexcept override;
    double get_pitch() const noexcept override;
    double get_roll() const noexcept override;
    std::array<double, 3> get_rpy() const noexcept;

private:
    void initialize_fdm(const std::string& fdm_type) noexcept;
};

}
