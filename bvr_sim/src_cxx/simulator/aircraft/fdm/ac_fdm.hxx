#pragma once

#include "fdm.hxx"
#include "c3utils/c3utils.hxx"
#include "rl/action_space.hxx"
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

    bool is_terminated() const noexcept { return terminate; };

};

}
