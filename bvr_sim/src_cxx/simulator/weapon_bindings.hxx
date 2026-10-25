#pragma once
#include "core_aircraft.hxx"
#include "core.hxx"
#include "ground/ground_factory.hxx"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace bvr_sim {
inline void require_sync_core(const SimCore& core) {
    if(core.is_running())throw std::logic_error("Typed world access requires synchronous core stepping");
}
inline std::shared_ptr<const Terrain> core_surface(const SimCore& core) {
    auto surface=core.environment();return surface?surface:std::make_shared<Terrain>();
}
inline void bind_weapon_api(pybind11::module_& m) {
    namespace py=pybind11;
#define RO(T,f) .def_readonly(#f,&T::f)
#define RW(T,f) .def_readwrite(#f,&T::f)
    py::class_<WeaponDefinition>(m,"WeaponDefinition") RO(WeaponDefinition,id) RO(WeaponDefinition,name)
        RO(WeaponDefinition,category) RO(WeaponDefinition,seeker) RO(WeaponDefinition,description);
    py::class_<StationDefinition>(m,"StationDefinition") RO(StationDefinition,id) RO(StationDefinition,name)
        RO(StationDefinition,mirror) RO(StationDefinition,diagram) RO(StationDefinition,weapons);
    py::class_<AircraftStations>(m,"AircraftStations") RO(AircraftStations,aircraft) RO(AircraftStations,source)
        RO(AircraftStations,limitations) RO(AircraftStations,stations) RO(AircraftStations,presets);
    py::class_<WeaponLaunchCheck>(m,"WeaponLaunchCheck") RO(WeaponLaunchCheck,allowed) RO(WeaponLaunchCheck,reason)
        RO(WeaponLaunchCheck,station) RO(WeaponLaunchCheck,range) RO(WeaponLaunchCheck,angle);
    py::class_<AircraftSpawnSpec>(m,"AircraftSpawnSpec").def(py::init<>()) RW(AircraftSpawnSpec,uid)
        RW(AircraftSpawnSpec,model) RW(AircraftSpawnSpec,team) RW(AircraftSpawnSpec,fdm)
        RW(AircraftSpawnSpec,position) RW(AircraftSpawnSpec,velocity) RW(AircraftSpawnSpec,loadout) RW(AircraftSpawnSpec,radar);
    py::class_<CoreObjectState>(m,"CoreObjectState") RO(CoreObjectState,uid) RO(CoreObjectState,kind)
        RO(CoreObjectState,model) RO(CoreObjectState,owner) RO(CoreObjectState,target)
        RO(CoreObjectState,position) RO(CoreObjectState,velocity) RO(CoreObjectState,orientation)
        RO(CoreObjectState,pylons) RO(CoreObjectState,alive) RO(CoreObjectState,done)
        RO(CoreObjectState,success) RO(CoreObjectState,health) RO(CoreObjectState,seeker_active);
    m.def("weapon_catalog",&selectable_weapons);
    m.def("aircraft_stations",&aircraft_stations);
    m.def("validate_loadout",&validate_loadout);
    m.def("loadout_preset",&loadout_preset);
#undef RO
#undef RW
}
}
