#pragma once

#include "base.hxx"
#include "../data_obj.hxx"
#include <string>
#include <map>
#include <memory>

namespace bvr_sim {

class RadarWarningSystem : public SensorBase {
private:
    double noise_std_position;
    double noise_std_velocity;

public:
    RadarWarningSystem(
        const std::shared_ptr<Aircraft>& parent,
        double noise_std_position = 200.0
    ) noexcept;

    ~RadarWarningSystem() noexcept override = default;

    void update() override;

    std::string log_suffix() const noexcept override { return ""; }
};

class MissileWarningSystem : public SensorBase {
private:
    double noise_std_position;

public:
    MissileWarningSystem(
        const std::shared_ptr<Aircraft>& parent,
        double noise_std_position = 200.0
    ) noexcept;

    ~MissileWarningSystem() noexcept override = default;

    void update() override;

    std::string log_suffix() const noexcept override { return ""; }
};

}