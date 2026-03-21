#pragma once

#include "base.hxx"
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

class SimpleFDM : public BaseFDM {
private:
    // F-16 specific performance parameters (from original F16 class)
    double max_speed;
    double min_speed;
    double max_turn_rate;
    double max_climb_rate;
    double max_acceleration;
    double max_g;
    double DELTA_PITCH_MAX;

    // Altitude limits
    double min_altitude;
    double max_altitude;

public:
    explicit SimpleFDM(double dt = 0.1) noexcept;

    ~SimpleFDM() noexcept override = default;

    void reset(const std::map<std::string, std::any>& initial_state) override;

    void step(const std::map<std::string, double>& action) override;

    void set_aircraft_parameters(const std::map<std::string, double>& params) noexcept;
};

}