#pragma once

#include "fdm.hxx"
#include "c3utils/c3utils.hxx"
#include "rl/action_space.hxx"
#include "simulator/aircraft/player_flight_types.hxx"
#include <array>
#include <map>
#include <string>
#include <any>

namespace bvr_sim {

class AircraftFDM : public FDM_API {
protected:
    bool terminate;

public:
    explicit AircraftFDM(double dt = 0.1) noexcept;

    virtual void step(const ActionSpace& action) = 0;
    // Presentation reads actual controls/outputs; it cannot mutate dynamics.
    virtual std::map<std::string,double> visual_properties() const { return {}; }
    virtual FlightMeasurements flight_measurements() const {
        FlightMeasurements m;m.position=get_position();m.velocity=get_velocity();m.orientation=get_rpy();m.speed=get_speed();return m;
    }
    virtual void step_surfaces(const FlightSurfaceControls& controls) {
        validate_surface_controls(controls);
        json::JSON action=json::Object();
        action["delta_heading"]=json::Float(0);action["delta_altitude"]=json::Float(0);action["delta_speed"]=json::Float(0);
        action["aileron_cmd"]=json::Float(controls.aileron);action["elevator_cmd"]=json::Float(controls.elevator);
        action["rudder_cmd"]=json::Float(controls.rudder);action["throttle_cmd"]=json::Float(controls.throttle);
        step(ActionSpace(std::move(action)));
    }

    bool is_terminated() const noexcept { return terminate; };

};

}
