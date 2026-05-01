#include "ac_fdm.hxx"
#include <cmath>

namespace bvr_sim {

using namespace c3utils;

AircraftFDM::AircraftFDM(double dt) noexcept
    : FDM_API(dt),
      terminate(false) {}
}
