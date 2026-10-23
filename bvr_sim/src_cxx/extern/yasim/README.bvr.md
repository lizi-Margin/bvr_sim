# Standalone YASim integration

Upstream: FlightGear `src/FDM/YASim`, revision
`807e406dd3bceca816942490a999970e157dbcfa`.
The original file headers and GPL license are retained in `COPYING`.
`UPSTREAM.json` pins the source. This directory is source, not a binary SDK.

`bvr_yasim` builds the actual aerodynamic solver, engines and rigid-body
integrator. It excludes `FGGround.cpp`, `yasim-test.cpp` and `proptest.cpp`.
The simulator host is `simulator/aircraft/fdm/yasim_fdm.cxx`.

Host compatibility patches relative to upstream:

- Use the existing JSBSim-bundled SimGear property/XML implementation, avoiding
  two incompatible definitions of `SGPropertyNode` in one process. Adapt the
  single property alias call to that version's API.
- Replace process termination in XML/control parsing with exceptions so a bad
  aircraft cannot terminate its host process.
- Initialize rigid-body mass/cache state, jet thrust and thruster fuel state.
  Initialize propeller-engine output vectors and engine control state. These
  eliminate reads before the first integration pass; aerodynamic equations are
  unchanged.
- Remove an unused FlightGear FDM header include from `Gear.cpp`.
- Release owned wing-section records and local solver control
  settings when resetting/destroying an aircraft.

The small `yasim_support/` host surface supplies scoped, thread-local property
access and logging/constants. `BVHMaterial.hxx` and `tiedpropertylist.hxx` come
from SimGear revision `abe3e7c96e08fe1a28941af923e450f566620ab6`; their original
headers and `COPYING.SimGear` are retained there. The complete FlightGear and
SimGear applications are not linked or launched.

Public state uses north/west/up, metres, seconds and radians. The YASim state
uses an ECEF frame anchored at the equator, with a static sea-level tangent
plane. The host returns an identity transform for this ground body. Terrain
collision above sea level remains the core caller's responsibility.

Each instance owns its property tree and creates a fresh parser/model on reset.
The host explicitly sets the upstream integrator interval for each substep
(at most 0.005 seconds); `Airplane::iterate(dt)` alone does not set that interval.
Airborne resets use source cruise controls and running hybrid piston engines.

FlightGear Nasal, electrical/hydraulic systems and autopilot scripts are not
executed. A generic host assist and documented input-name aliases produce
surface commands. Source XML still supplies all simulated forces and masses.
This integration does not certify aircraft flight envelopes or source FCS fidelity.
Set `BVR_YASIM_SOLVER_VERBOSE=1` only for local solver diagnostics.
