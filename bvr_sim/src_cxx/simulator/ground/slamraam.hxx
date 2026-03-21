#pragma once

#include "aa.hxx"

namespace bvr_sim {

class SLAMRAAM : public AA {
private:
    double search_range;
    double height_gate;
    double velocity_gate;
    double last_shoot_time;
    double min_shoot_interval;

public:
    SLAMRAAM(
        const std::string& uid,
        TeamColor color,
        const std::array<double, 3>& position,
        double dt = 0.1,
        int num_missiles = 6
    ) noexcept;

    ~SLAMRAAM() noexcept override = default;

    bool can_shoot() const noexcept override;

    bool can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept override;

    void shoot(
        const std::shared_ptr<Missile>& missile,
        const std::shared_ptr<Aircraft>& target = nullptr
    ) noexcept override;

    void step() override;

    double get_search_range() const noexcept { return search_range; }
    double get_height_gate() const noexcept { return height_gate; }
    double get_velocity_gate() const noexcept { return velocity_gate; }
    double get_last_shoot_time() const noexcept { return last_shoot_time; }
    double get_min_shoot_interval() const noexcept { return min_shoot_interval; }
};

}