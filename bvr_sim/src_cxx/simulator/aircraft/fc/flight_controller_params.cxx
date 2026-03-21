#include "flight_controller_params.hxx"
#include "c3utils/c3utils.hxx"
#include "rubbish_can/check.hxx"
#include <cmath>

namespace bvr_sim {

FlightControllerParamsManager* FlightControllerParamsManager::instance_ = nullptr;

FlightControllerParamsManager::FlightControllerParamsManager() noexcept {
    FlightControllerParams f16_params = FlightControllerParams::get_f16_params();
  
    params_map_["F16"] = f16_params;
    params_map_["F15"] = f16_params;
    params_map_["F18"] = f16_params;
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
