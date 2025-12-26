#pragma once

#include "base.hxx"

namespace bvr_sim {

class Missile;
class Aircraft;

class AA : public GroundUnit {
protected:
    int num_missiles;
    int num_left_missiles;
    double _t;
    std::vector<std::shared_ptr<Missile>> launched_missiles;

public:
    AA(
        const std::string& uid,
        const std::string& model,
        TeamColor color,
        const std::array<double, 3>& position,
        double dt = 0.1,
        int num_missiles = 6
    ) noexcept;

    ~AA() noexcept override = default;

    virtual bool can_shoot() const noexcept;

    virtual bool can_shoot_enm(const std::shared_ptr<SimulatedObject>& enemy) const noexcept;

    virtual void shoot(
        const std::shared_ptr<Missile>& missile,
        const std::shared_ptr<Aircraft>& target = nullptr
    ) noexcept;

    void step() override;

    std::array<double, 3> get_launch_velocity(const std::shared_ptr<Aircraft>& target) const noexcept;

    std::string log() noexcept override;

    int get_num_missiles() const noexcept { return num_missiles; }
    int get_num_left_missiles() const noexcept { return num_left_missiles; }
    double get_t() const noexcept { return _t; }
    const std::vector<std::shared_ptr<Missile>>& get_launched_missiles() const noexcept { return launched_missiles; }
};

}