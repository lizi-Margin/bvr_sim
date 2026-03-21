#include "radar.hxx"
#include "../aircraft/base.hxx"
#include "../../c3utils/funcs.hxx"
#include "rubbish_can/colorful.hxx"
#include "rubbish_can/check.hxx"
#include "rubbish_can/SL.hxx"
#include <cmath>
#include <algorithm>
#include <sstream>

namespace bvr_sim {

using namespace c3utils;

const std::map<std::string, Radar::RadarSpecs> Radar::RADAR_SPECS = {
        // double max_range;
        // double RadarHorizontalBeamwidth;
        // double RadarVerticalBeamwidth;
        // double scan_zone_size_hori;
        // double scan_zone_size_vert;
        // double gimbal_limit;
        // double frequency_ghz;
    {"F16", {
        110000.0,
        deg2rad(5.0),
        deg2rad(5.0),
        deg2rad(20.0),
        deg2rad(20.0),
        deg2rad(85.0),
        9.86
    }}
};

ScanZone::ScanZone(Radar* radar_, double scan_zone_size_hori_, double scan_zone_size_vert_) noexcept
    : radar(radar_),
      now_scan_zone_rpy{0.0, 0.0, 0.0},
      scan_zone_size_hori(scan_zone_size_hori_),
      scan_zone_size_vert(scan_zone_size_vert_),
      now_beam_angle_hori(0.0),
      now_beam_angle_vert(0.0),
      beam_step_right(true)
{
    reset_beam();
}

void ScanZone::reset_beam() noexcept {
    now_beam_angle_hori = radar->RadarHorizontalBeamwidth / 2.0 - scan_zone_size_hori / 2.0;
    now_beam_angle_vert = -radar->RadarVerticalBeamwidth / 2.0 + scan_zone_size_vert / 2.0;
    beam_step_right = true;
}

Radar::Radar(
    const std::shared_ptr<Aircraft>& parent_,
    bool enable_noise_,
    double noise_std_position_,
    double noise_std_velocity_
) noexcept
    : SensorBase(parent_),
      RadarDirectionVec(1.0, 0.0, 0.0),
      scan_zone(this),
      enable_noise(enable_noise_),
      noise_std_position(noise_std_position_),
      noise_std_velocity(noise_std_velocity_),
      radar_mode("scan")
{
    auto it = RADAR_SPECS.find(parent_->aircraft_model);
    const RadarSpecs& specs = (it != RADAR_SPECS.end()) ? it->second : RADAR_SPECS.at("F16");

    radar_range = specs.max_range;
    RadarHorizontalBeamwidth = specs.RadarHorizontalBeamwidth;
    RadarVerticalBeamwidth = specs.RadarVerticalBeamwidth;
    RadarElevation = 0.0;
    RadarAzimuth = 0.0;
    gimbal_limit = specs.gimbal_limit;
    frequency_ghz = specs.frequency_ghz;

    scan_zone = ScanZone(this, specs.scan_zone_size_hori, specs.scan_zone_size_vert);

    RadarRollEgo = 0.0;
    RadarElevationEgo = 0.0;
    RadarAzimuthEgo = 0.0;
}

Vector3 Radar::_get_parent_nose_vec() const noexcept {
    return Vector3(parent->velocity).normalize();
}

Vector3 Radar::_get_rel_pos_vec(const std::shared_ptr<SimulatedObject>& simulatedobj) const noexcept {
    return Vector3(
        simulatedobj->position[0] - parent->position[0],
        simulatedobj->position[1] - parent->position[1],
        simulatedobj->position[2] - parent->position[2]
    );
}

std::array<double, 2> Radar::_get_el_az(const Vector3& direction_vec, const Vector3& nose_vec) const noexcept {
    auto gba = nose_vec.get_rotate_angle_fix();
    Vector3 dir_copy = direction_vec;
    dir_copy.rev_rotate_xyz_fix(gba[0], gba[1], gba[2]);
    auto angles = dir_copy.get_rotate_angle_fix();
    return {angles[1], angles[2]};
}

void Radar::_step_radar_scan_zone_direction() noexcept {
    scan_zone.now_scan_zone_rpy[0] = 0.0;
    scan_zone.now_scan_zone_rpy[1] = -parent->get_pitch();
    scan_zone.now_scan_zone_rpy[2] = 0.0;

    if (parent->sa_datalink != nullptr) {
        double el, az;
        if (_get_best_target(el, az) != nullptr){
            scan_zone.now_scan_zone_rpy[1] = el;
            scan_zone.now_scan_zone_rpy[2] = az;
        } else {
            // default, set above
        }
    } else {
        SL::get().print("[Radar] Warning: no sa_datalink");
    }
}

void Radar::_step_scan_zone_inside_bar() noexcept {
    bool STEP_VERT = false;
    bool RESET = false;

    double next_hori;
    if (scan_zone.beam_step_right) {
        next_hori = scan_zone.now_beam_angle_hori + RadarHorizontalBeamwidth;
    } else {
        next_hori = scan_zone.now_beam_angle_hori - RadarHorizontalBeamwidth;
    }

    if (next_hori > scan_zone.scan_zone_size_hori / 2.0 || next_hori < -scan_zone.scan_zone_size_hori / 2.0) {
        double next_vert = scan_zone.now_beam_angle_vert - RadarVerticalBeamwidth;
        if (next_vert < -scan_zone.scan_zone_size_vert / 2.0) {
            RESET = true;
        } else {
            STEP_VERT = true;
        }
    }

    if (RESET) {
        scan_zone.reset_beam();
        track_targets.clear();
    } else if (STEP_VERT) {
        scan_zone.beam_step_right = !scan_zone.beam_step_right;
        scan_zone.now_beam_angle_vert = scan_zone.now_beam_angle_vert - RadarVerticalBeamwidth;
    } else {
        scan_zone.now_beam_angle_hori = next_hori;
    }
}

void Radar::_sync_radar_antenna() noexcept {
    Vector3 parent_nose = Vector3(parent->velocity).normalize();
    auto gba = parent_nose.get_rotate_angle_fix();

    Vector3 direction_vec(1.0, 0.0, 0.0);

    double zr = scan_zone.now_scan_zone_rpy[0];
    double zp = scan_zone.now_scan_zone_rpy[1];
    double zy = scan_zone.now_scan_zone_rpy[2];

    direction_vec.rotate_zyx_self(
        0.0 + zr,
        scan_zone.now_beam_angle_vert + zp,
        scan_zone.now_beam_angle_hori + zy
    );

    direction_vec.rotate_xyz_fix(gba[0], gba[1], gba[2]);
    RadarDirectionVec = direction_vec;

    auto el_az = _get_el_az(direction_vec, parent_nose);
    double el = norm(el_az[0], -gimbal_limit, gimbal_limit);
    double az = norm(el_az[1], -gimbal_limit, gimbal_limit);
    RadarElevation = el;
    RadarAzimuth = az;
}

bool Radar::_target_in_beam(const std::shared_ptr<SimulatedObject>& enemy) const noexcept {
    if (!enemy->is_alive) {
        return false;
    }

    std::array<double, 3> rel_pos = {
        enemy->position[0] - parent->position[0],
        enemy->position[1] - parent->position[1],
        enemy->position[2] - parent->position[2]
    };
    double distance = linalg_norm(rel_pos);

    if (distance > radar_range) {
        return false;
    }

    Vector3 parent_nose = Vector3(parent->velocity).normalize();
    Vector3 rel_pos_vec(rel_pos[0] / distance, rel_pos[1] / distance, rel_pos[2] / distance);

    auto el_az = _get_el_az(rel_pos_vec, parent_nose);
    double rel_el = el_az[0];
    double rel_az = el_az[1];

    double el_lower_bound = RadarElevation - RadarVerticalBeamwidth / 2.0;
    double el_higher_bound = RadarElevation + RadarVerticalBeamwidth / 2.0;
    if (!(el_lower_bound < rel_el && rel_el < el_higher_bound)) {
        return false;
    }

    double az_lower_bound = RadarAzimuth - RadarHorizontalBeamwidth / 2.0;
    double az_higher_bound = RadarAzimuth + RadarHorizontalBeamwidth / 2.0;
    if (!(az_lower_bound < rel_az && rel_az < az_higher_bound)) {
        return false;
    }

    return true;
}

void Radar::_stt(const std::shared_ptr<SimulatedObject>& enemy) noexcept {
    if (!enemy->is_alive) {
        return;
    }

    std::array<double, 3> rel_pos = {
        enemy->position[0] - parent->position[0],
        enemy->position[1] - parent->position[1],
        enemy->position[2] - parent->position[2]
    };
    double distance = linalg_norm(rel_pos);

    Vector3 parent_nose = Vector3(parent->velocity).normalize();
    Vector3 rel_pos_vec(rel_pos[0] / distance, rel_pos[1] / distance, rel_pos[2] / distance);
    RadarDirectionVec = rel_pos_vec;

    auto el_az = _get_el_az(rel_pos_vec, parent_nose);
    double rel_el = norm(el_az[0], -gimbal_limit, gimbal_limit);
    double rel_az = norm(el_az[1], -gimbal_limit, gimbal_limit);
    RadarElevation = rel_el;
    RadarAzimuth = rel_az;
}

void Radar::_sync_radar_antenna_ego() noexcept {
    Vector3 radar_direction = RadarDirectionVec;
    double p_roll = parent->get_roll();
    double p_pitch = parent->get_pitch();
    double p_yaw = parent->get_heading();
    radar_direction.rev_rotate_zyx_self(p_roll, p_pitch, p_yaw);
    auto angles = radar_direction.get_rotate_angle_fix();
    double r_pitch = angles[1];
    double r_yaw = angles[2];
    double r_roll = -p_roll;
    RadarRollEgo = r_roll;
    RadarElevationEgo = r_pitch;
    RadarAzimuthEgo = r_yaw;
}

std::shared_ptr<SimulatedObject> Radar::_get_target_to_track() const noexcept {
    if (track_targets.size() > 0) {
        return track_targets.begin()->second;
    } else {
        return nullptr;
    }
}

void Radar::update() {
    data_dict.clear();
    parent->enemies_lock.clear();

    double best_target_el, best_target_az;
    auto mem_target = _get_target_to_track();
    auto best_target = _get_best_target(best_target_el, best_target_az);

    /////////////////////// Simple logic ///////////////////////////////
    if (best_target != nullptr) {
        _stt(best_target);
    } else {
        _step_radar_scan_zone_direction();
        _step_scan_zone_inside_bar();
        _sync_radar_antenna();
    }

    /////////////////////// Realistic logic ///////////////////////////////
    // if (mem_target != nullptr) {
    //     if (best_target != nullptr) {
    //         if (best_target->uid != mem_target->uid) {
    //             radar_mode = "scan";
    //         } else {
    //             radar_mode = "stt";
    //         }
    //     } else {
    //         radar_mode = "stt";
    //     }
    // } else {
    //     radar_mode = "scan";
    // }

    // if (radar_mode == "stt") {
    //     check(mem_target != nullptr, "mem_target is nullptr");
    //     _stt(mem_target);
    // } else if (radar_mode == "scan") {
    //     _step_radar_scan_zone_direction();
    //     _step_scan_zone_inside_bar();
    //     _sync_radar_antenna();
    // } else {
    //     check(false, "radar_mode not stt or scan");
    // }

    if (RENDER_RADAR_BEAM) {
        _sync_radar_antenna_ego();
    }

    track_targets.clear();
    for (auto& enemy : parent->enemies) {
        if (!enemy->is_alive) {
            continue;
        }
        if (enemy->Type != SOT::Aircraft) {
            continue;
        }
        if (!_target_in_beam(enemy)) {
            track_targets.erase(enemy->uid);
            continue;
        }

        track_targets[enemy->uid] = enemy;

        auto detection = std::make_shared<DataObj>(
            enemy,
            enable_noise ? noise_std_position : 0.0,
            enable_noise ? noise_std_velocity : 0.0
        );

        data_dict[enemy->uid] = detection;
        auto ac_enemy = std::dynamic_pointer_cast<Aircraft>(enemy);
        if (ac_enemy) {
            parent->enemies_lock.push_back(ac_enemy);
        } else {
            colorful::printHONG("Radar: enemy dynamic cast failed");
            std::abort();
        }
    }

    if (parent->enemies_lock.size() > 0) {
        std::sort(parent->enemies_lock.begin(), parent->enemies_lock.end(),
            [this](const std::shared_ptr<SimulatedObject>& a, const std::shared_ptr<SimulatedObject>& b) {
                double dist_a = linalg_norm(std::array<double, 3>{
                    a->position[0] - parent->position[0],
                    a->position[1] - parent->position[1],
                    a->position[2] - parent->position[2]
                });
                double dist_b = linalg_norm(std::array<double, 3>{
                    b->position[0] - parent->position[0],
                    b->position[1] - parent->position[1],
                    b->position[2] - parent->position[2]
                });
                return dist_a < dist_b;
            });
    }
}

std::string Radar::log_suffix() const noexcept {
    std::ostringstream msg;
    if (RENDER_RADAR_BEAM) {
        msg << ",RadarMode=1,RadarRange=" << radar_range
            << ",RadarHorizontalBeamwidth=" << rad2deg(RadarHorizontalBeamwidth)
            << ",RadarVerticalBeamwidth=" << rad2deg(RadarVerticalBeamwidth);
        msg << ",RadarRoll=" << rad2deg(RadarRollEgo)
            << ",RadarElevation=" << -rad2deg(RadarElevationEgo)
            << ",RadarAzimuth=" << -rad2deg(RadarAzimuthEgo);

        if (radar_mode == "stt") {
            auto lock_target = _get_target_to_track();
            double lock_range;
            if (lock_target != nullptr) {
                lock_range = linalg_norm(std::array<double, 3>{
                    lock_target->position[0] - parent->position[0],
                    lock_target->position[1] - parent->position[1],
                    lock_target->position[2] - parent->position[2]
                });
            } else {
                lock_range = radar_range;
            }
            msg << ",LockedTargetMode=1,LockedTargetAzimuth=" << -rad2deg(RadarAzimuthEgo)
                << ",LockedTargetElevation=" << -rad2deg(RadarElevationEgo)
                << ",LockedTargetRange=" << lock_range;
        } else if (radar_mode == "scan") {
            msg << ",LockedTargetMode=0";
        }
        msg << "\n";
    }
    return msg.str();
}



std::shared_ptr<SimulatedObject> Radar::_get_best_target(double& out_el, double& out_az) const noexcept {
    if (parent->sa_datalink == nullptr) return nullptr;

    auto& dl_data_dict = parent->sa_datalink->get_data();
    std::vector<std::shared_ptr<DataObj>> dl_dataobj_list;
    for (const auto& pair : dl_data_dict) {
        dl_dataobj_list.push_back(pair.second);
    }

    std::sort(dl_dataobj_list.begin(), dl_dataobj_list.end(),
        [this](const std::shared_ptr<DataObj>& a, const std::shared_ptr<DataObj>& b) {
            double dist_a = linalg_norm_vec(Vector3(
                a->position[0] - parent->position[0],
                a->position[1] - parent->position[1],
                a->position[2] - parent->position[2]
            ));
            double dist_b = linalg_norm_vec(Vector3(
                b->position[0] - parent->position[0],
                b->position[1] - parent->position[1],
                b->position[2] - parent->position[2]
            ));
            return dist_a < dist_b;
        });

    for (const auto& dataobj : dl_dataobj_list) {
        auto el_az = _get_el_az(_get_rel_pos_vec(dataobj), _get_parent_nose_vec());
        double el = el_az[0];
        double az = el_az[1];
        if (std::abs(el) < gimbal_limit && std::abs(az) < gimbal_limit) {
            out_el = el;
            out_az = az;
            check(dataobj->source, "source is nullptr");
            return dataobj->source;
        }
        /// simple ///
        else {
            return nullptr;
        }
        //////////////
    }

    return nullptr;
}

}
