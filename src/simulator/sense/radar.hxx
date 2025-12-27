#pragma once

#include "base.hxx"
#include "../aircraft/base.hxx"
#include "../simulator.hxx"
// #include "../data_obj.hxx"
#include "../../c3utils/funcs.hxx"
#include <string>
#include <map>
#include <memory>
#include <array>

namespace bvr_sim {

class Radar;

class ScanZone {
public:
    Radar* radar;
    std::array<double, 3> now_scan_zone_rpy;
    double scan_zone_size_hori;
    double scan_zone_size_vert;
    double now_beam_angle_hori;
    double now_beam_angle_vert;
    bool beam_step_right;

    ScanZone(Radar* radar_, double scan_zone_size_hori_ = c3utils::deg2rad(30.0), double scan_zone_size_vert_ = c3utils::deg2rad(20.0)) noexcept;

    void reset_beam() noexcept;
};

class Radar : public SensorBase {
public:
    struct RadarSpecs {
        double max_range;
        double RadarHorizontalBeamwidth;
        double RadarVerticalBeamwidth;
        double scan_zone_size_hori;
        double scan_zone_size_vert;
        double gimbal_limit;
        double frequency_ghz;
    };

    static const std::map<std::string, RadarSpecs> RADAR_SPECS;
    static constexpr bool RENDER_RADAR_BEAM = true;

public:
    double radar_range;
    double RadarHorizontalBeamwidth;
    double RadarVerticalBeamwidth;
    double RadarElevation;
    double RadarAzimuth;
    c3utils::Vector3 RadarDirectionVec;
    double gimbal_limit;
    double frequency_ghz;
    ScanZone scan_zone;

    double RadarRollEgo;
    double RadarElevationEgo;
    double RadarAzimuthEgo;

    bool enable_noise;
    double noise_std_position;
    double noise_std_velocity;

    std::map<std::string, std::shared_ptr<SimulatedObject>> track_targets;

    std::string radar_mode;

    Radar(
        const std::shared_ptr<Aircraft>& parent_,
        bool enable_noise_ = false,
        double noise_std_position_ = 50.0,
        double noise_std_velocity_ = 5.0
    ) noexcept;

    ~Radar() noexcept override = default;

    void update() override;

    std::string log_suffix() const noexcept override;

    virtual void clean_up() noexcept override {
        SensorBase::clean_up();
        track_targets.clear();
    }

private:
    c3utils::Vector3 _get_parent_nose_vec() const noexcept;

    c3utils::Vector3 _get_rel_pos_vec(const std::shared_ptr<SimulatedObject>& simulatedobj) const noexcept;

    std::array<double, 2> _get_el_az(const c3utils::Vector3& direction_vec, const c3utils::Vector3& nose_vec) const noexcept;

    void _step_radar_scan_zone_direction() noexcept;

    void _step_scan_zone_inside_bar() noexcept;

    void _sync_radar_antenna() noexcept;

    bool _target_in_beam(const std::shared_ptr<SimulatedObject>& enemy) const noexcept;

    void _stt(const std::shared_ptr<SimulatedObject>& enemy) noexcept;

    void _sync_radar_antenna_ego() noexcept;

    std::shared_ptr<SimulatedObject> _get_target_to_track() const noexcept;

    std::shared_ptr<SimulatedObject> _get_best_target(double& out_el, double& out_az) const noexcept;
};

}
