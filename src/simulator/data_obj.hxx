#pragma once

#include "simulator.hxx"
#include <string>
#include <array>
#include <memory>

namespace bvr_sim {

class DataObj : public SimulatedObject {
public:
    const std::shared_ptr<SimulatedObject> source;

protected:
    std::string name_suffix;
    double noise_std_position;
    double noise_std_velocity;

    std::array<double, 3> true_position;
    std::array<double, 3> true_velocity;

public:
    DataObj(
        const std::shared_ptr<SimulatedObject>& source_obj,
        double noise_std_position = 0.0,
        double noise_std_velocity = 0.0
    ) noexcept;

    ~DataObj() noexcept override = default;

    void step() override;

    std::string log() noexcept override;

    std::array<double, 3> get_position_error() const noexcept;
    std::array<double, 3> get_velocity_error() const noexcept;
    double get_position_error_magnitude() const noexcept;
    double get_velocity_error_magnitude() const noexcept;

protected:
    std::array<double, 3> add_position_error(
        const std::array<double, 3>& true_position,
        double std_dev
    ) const noexcept;

    std::array<double, 3> add_velocity_error(
        const std::array<double, 3>& true_velocity,
        double std_dev
    ) const noexcept;
};

}
