#include "unit_factory.hxx"
#include "aircraft/fighter.hxx"
#include "ground/slamraam.hxx"
#include "ground/ground_static_target.hxx"
#include "so_pool.hxx"
#include "pylon_manager.hxx"
#include "rubbish_can/json_getter.hxx"
#include "global_config.hxx"
#include "sense/rws.hxx"
#include "sense/radar.hxx"
// #include "sense/simple_radar.hxx"
#include "sense/awacs.hxx"
#include "bsl_pool.hxx"
#include "rubbish_can/SL.hxx"
#include "rubbish_can/colorful.hxx"
#include "rubbish_can/rubbish_can.hxx"
#include "baseline_opponents/mad.hxx"
#include "baseline_opponents/tactical.hxx"
#include <iostream>

namespace bvr_sim {

const std::map<std::string, UnitFactory::UnitType> UnitFactory::UNIT_MAP = {
    {"F16", UnitType::Fighter},
    {"F15", UnitType::Fighter},
    {"F18", UnitType::Fighter},
    {"SLAMRAAM", UnitType::SLAMRAM},
    {"GroundStaticTarget", UnitType::GroundStaticTarget},
    {"Ground", UnitType::GroundStaticTarget},
};

UnitFactory::UnitType UnitFactory::parse_unit_type(const std::string& unit_spec) noexcept {
    if (unit_spec.empty()) {
        return UnitType::Unknown;
    }

    auto it = UNIT_MAP.find(unit_spec);
    if (it == UNIT_MAP.end()) {
        return UnitType::Unknown;
    }
    return it->second;
}

std::shared_ptr<SimulatedObject> UnitFactory::create_unit(
    const std::string& uid,
    json::JSON spec_json
) noexcept {
    std::string unit_spec;
    if (!get_string_from_json("unit_spec", spec_json, unit_spec)) {
        std::cout << "Failed to get unit_spec from JSON" << std::endl;
        return nullptr;
    }

    std::string color_str;
    TeamColor color;
    if (!get_string_from_json("color", spec_json, color_str)) {
        std::cout << "Failed to get color from JSON" << std::endl;
        return nullptr;
    }
    if (color_str == "Blue" || color_str == "blue") {
        color = TeamColor::Blue;
    } else if (color_str == "Red" || color_str == "red") {
        color = TeamColor::Red;
    } else {
        std::cout << "Invalid color: " << color_str << std::endl;
        SL::get().print("[UnitFactory] Error:  Invalid color: " + color_str);
        return nullptr;
    }



    UnitType type = parse_unit_type(unit_spec);

    try {
        std::array<double, 3> position = {0.0, 0.0, 5000.0};
        std::array<double, 3> velocity = {0.0, 1.0, 250};

        if (!get_array3_from_json("position", spec_json, position)) {
            std::cout << "Failed to get position from JSON" << std::endl;
            SL::get().print("[UnitFactory] Warning: Failed to get position from JSON");
        }


        if (!get_array3_from_json("velocity", spec_json, velocity)) {
            std::cout << "Failed to get velocity from JSON" << std::endl;
            SL::get().print("[UnitFactory] Warning: Failed to get velocity from JSON");
        }

        // if (!get_double_from_json("dt", spec_json, dt)) {
        //     std::cout << "Failed to get dt from JSON" << std::endl;
        // }

        std::shared_ptr<SimulatedObject> unit = nullptr;

        switch (type) {
            case UnitType::Fighter: {
                SL::get().print("[UnitFactory] start create fighter");
                std::string fdm_type = "simple"; // or jsbsim
                if (spec_json.hasKey("fdm_type")) {
                    fdm_type = spec_json["fdm_type"].ToString();
                }
                SL::get().print("[UnitFactory] fdm_type: " + fdm_type);

                SL::get().print("[UnitFactory] start create fighter shared ptr with uid: " + uid);
                auto fighter = std::make_shared<Fighter>(
                    uid,
                    color,
                    position,
                    velocity,
                    cfg::dt,
                    fdm_type
                );
                if (!fighter) {
                    colorful::printHONG("Failed to create fighter with uid: " + uid + " ptr is nullptr");
                    check(false, "Failed to create fighter with uid: " + uid + " ptr is nullptr");
                    return nullptr;
                }

                std::string radar_type = "radar";
                get_string_from_json("radar_type", spec_json, radar_type);
                
                if (radar_type == "radar") {
                    fighter->add_sensor("radar", std::make_shared<Radar>(fighter));
                }
                // else if (radar_type == "simple_radar") {
                //     fighter->add_sensor("radar", std::make_shared<SimpleRadar>(fighter));
                // }
                else {
                    check(false, "Invalid radar_type: " + radar_type);
                }
                SL::get().print("[UnitFactory] add sensor " + radar_type + " to fighter with uid: " + uid);
                
                SL::get().print("[UnitFactory] add sensor rws to fighter with uid: " + uid);
                fighter->add_sensor("rws", std::make_shared<RadarWarningSystem>(fighter));
                SL::get().print("[UnitFactory] add sensor mws to fighter with uid: " + uid);
                fighter->add_sensor("mws", std::make_shared<MissileWarningSystem>(fighter));
                SL::get().print("[UnitFactory] add sensor sa_datalink to fighter with uid: " + uid);
                fighter->add_sensor("sa_datalink", std::make_shared<SADatalink>(fighter));

                SL::get().print("[UnitFactory] start add pyload to fighter pylon manager with uid: " + uid);
                std::map<std::string, std::string> pylon_mounts;
                if (get_map_ss_from_json("pylon_mounts", spec_json, pylon_mounts)) {
                    auto req_pyload = print_map_s(pylon_mounts);
                    SL::get().print("[UnitFactory] req_pyload: " + req_pyload);
                    for (auto& [pylon_name, weapon_spec] : pylon_mounts) {
                        std::string weapon_name = weapon_spec;
                        SL::get().print("[UnitFactory] add weapon " + weapon_name + " to pylon " + pylon_name);
                        fighter->pylon_manager.add_weapon(pylon_name, weapon_name);
                    }
                } else {
                    SL::get().print("[UnitFactory] Failed to get pylon mounts from JSON");
                    colorful::printHUANG("Failed to get pylon mounts from JSON");
                }
                SL::get().print("[UnitFactory] finish add pyload to fighter pylon manager with uid: " + uid);

                SL::get().print("[UnitFactory] freeze pylon manager with uid: " + uid);
                fighter->pylon_manager.freeze();

                SL::get().print("[UnitFactory] add fighter to baseline pool with uid: " + uid);

                std::string opponent_type = "";
                if (spec_json.hasKey("opponent_type")) {
                    opponent_type = spec_json["opponent_type"].ToString();
                }
                // Add appropriate baseline opponent based on type
                if (opponent_type == "tactical") {
                    BaselinePool::instance().add(fighter, std::make_shared<TacticalOpponent3D>());
                    SL::get().print("[UnitFactory] add fighter, tactical to baseline pool with uid: " + uid + " success");
                } else if (opponent_type == "mad") {
                    BaselinePool::instance().add(fighter, std::make_shared<MadOpponent3D>());
                    SL::get().print("[UnitFactory] add fighter, mad to baseline pool with uid: " + uid + " success");
                } else {
                    // do nothing
                    SL::get().print("[UnitFactory] no opponent with uid: " + uid);
                }
                
                unit = fighter;
                break;
            }

            case UnitType::SLAMRAM: {
                int num_missiles = 6;
                unit = std::make_shared<SLAMRAAM>(
                    uid,
                    color,
                    position,
                    cfg::dt,
                    num_missiles
                );
                break;
            }

            case UnitType::GroundStaticTarget: {
                unit = std::make_shared<GroundStaticTarget>(
                    uid,
                    color,
                    position,
                    cfg::dt
                );
                break;
            }

            case UnitType::Unknown:
            default:
                std::cerr << "Warning: Unknown unit type '" << unit_spec << "'" << std::endl;
                return nullptr;
        }

        if (unit) {
            SOPool::instance().add(unit);
        }

        return unit;

    } catch (const std::exception& e) {
        std::cerr << "Error creating unit " << uid << ": " << e.what() << std::endl;
        return nullptr;
    } catch (...) {
        std::cerr << "Unknown error creating unit " << uid << std::endl;
        return nullptr;
    }
}

}
