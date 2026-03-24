#include "flight_controller_params.hxx"
#include "c3utils/c3utils.hxx"
#include "rubbish_can/check.hxx"
#include <cmath>

namespace bvr_sim {

FlightControllerParamsManager* FlightControllerParamsManager::instance_ = nullptr;

FlightControllerParamsManager::FlightControllerParamsManager() noexcept {
    params_map_["F16"] = FlightControllerParams::get_f16_params();
    params_map_["F15"] = FlightControllerParams::get_f15_params();
    params_map_["F15_original"] = FlightControllerParams::get_f16_params();
    params_map_["F18"] = FlightControllerParams::get_f18_params();
    params_map_["F18_original"] = FlightControllerParams::get_f16_params();
    params_map_["F4N"] = FlightControllerParams::get_f16_params();
    params_map_["F4N_original"] = FlightControllerParams::get_f16_params();
    params_map_["AJ37"] = FlightControllerParams::get_f16_params();
    params_map_["JA37"] = FlightControllerParams::get_f16_params();
    params_map_["F22"] = FlightControllerParams::get_f16_params();
    params_map_["F22_original"] = FlightControllerParams::get_f16_params();
}

FlightControllerParamsManager& FlightControllerParamsManager::getInstance() noexcept {
    if (instance_ == nullptr) {
        instance_ = new FlightControllerParamsManager();
    }
    return *instance_;
}

const FlightControllerParams& FlightControllerParamsManager::getParams(
    const std::string& aircraft_key) const noexcept {
    auto it = params_map_.find(aircraft_key);
    if (it == params_map_.end()) {
        check(false, "wrong aircraft key: " + aircraft_key);
    }
    return it->second;
}

}  // namespace bvr_sim
