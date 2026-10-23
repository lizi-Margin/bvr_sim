#pragma once
#include "game_session.hxx"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace bvr_sim {
inline void bind_game_api(pybind11::module_ &m) {
    namespace py = pybind11;
#define RW(T, field) .def_readwrite(#field, &T::field)
#define RO(T, field) .def_readonly(#field, &T::field)
    py::class_<GameConfig>(m, "GameConfig")
        .def(py::init<>()) RW(GameConfig, player_model) RW(GameConfig, enemy_model) RW(GameConfig, mission)
            RW(GameConfig, fdm) RW(GameConfig, seed) RW(GameConfig, dt) RW(GameConfig, enemy_range)
                RW(GameConfig, altitude) RW(GameConfig, speed) RW(GameConfig, enemy_attacks)
                    RW(GameConfig, enemy_evasion) RW(GameConfig, player_north) RW(GameConfig, player_west)
                        RW(GameConfig, ground_north) RW(GameConfig, ground_west) RW(GameConfig, missiles)
                            RW(GameConfig, bombs);
    py::class_<PilotCommand>(m, "PilotCommand")
        .def(py::init<>()) RW(PilotCommand, uid) RW(PilotCommand, heading) RW(PilotCommand, pitch)
            RW(PilotCommand, throttle) RW(PilotCommand, roll_input) RW(PilotCommand, manual_roll)
                RW(PilotCommand, fire) RW(PilotCommand, drop_bomb) RW(PilotCommand, lock)
                    RW(PilotCommand, target_uid) RW(PilotCommand, weapon);
    py::class_<GameContact>(m, "GameContact") RO(GameContact, uid) RO(GameContact, sensor)
        RO(GameContact, position) RO(GameContact, velocity) RO(GameContact, locked);
    py::class_<GameEntity>(m, "GameEntity") RO(GameEntity, uid) RO(GameEntity, model) RO(GameEntity, kind)
        RO(GameEntity, team) RO(GameEntity, alive) RO(GameEntity, position) RO(GameEntity, velocity)
            RO(GameEntity, orientation) RO(GameEntity, health) RO(GameEntity, mach) RO(GameEntity, pylons)
                RO(GameEntity, throttle) RO(GameEntity, weapon_age) RO(GameEntity, motor_burning);
    py::class_<LaunchEnvelope>(m, "LaunchEnvelope") RO(LaunchEnvelope, target_uid) RO(LaunchEnvelope, range)
        RO(LaunchEnvelope, closing_speed) RO(LaunchEnvelope, bearing) RO(LaunchEnvelope, rmax)
            RO(LaunchEnvelope, rtr) RO(LaunchEnvelope, eta) RO(LaunchEnvelope, in_range);
    py::class_<MissileFlight>(m, "MissileFlight") RO(MissileFlight, uid) RO(MissileFlight, owner)
        RO(MissileFlight, target) RO(MissileFlight, age) RO(MissileFlight, range)
            RO(MissileFlight, closing_speed) RO(MissileFlight, eta) RO(MissileFlight, seeker_active)
                RO(MissileFlight, motor_burning);
    py::class_<CombatEvent>(m, "CombatEvent") RO(CombatEvent, tick) RO(CombatEvent, kind)
        RO(CombatEvent, actor) RO(CombatEvent, target) RO(CombatEvent, weapon) RO(CombatEvent, message)
            RO(CombatEvent, position);
    py::class_<GameFrame>(m, "GameFrame") RO(GameFrame, tick) RO(GameFrame, applied_command_tick)
        RO(GameFrame, sim_time) RO(GameFrame, paused) RO(GameFrame, mission) RO(GameFrame, result)
            RO(GameFrame, selected_target) RO(GameFrame, entities) RO(GameFrame, contacts)
                RO(GameFrame, events) RO(GameFrame, missiles_left) RO(GameFrame, bombs_left)
                    RO(GameFrame, air_kills) RO(GameFrame, ground_kills) RO(GameFrame, radar_warning)
                        RO(GameFrame, missile_warning) RO(GameFrame, bomb_impact) RO(GameFrame, radar_mode)
                            RO(GameFrame, rwr_mode) RO(GameFrame, enemy_behavior) RO(GameFrame, radar_range)
                                RO(GameFrame, envelope) RO(GameFrame, missiles);
    py::class_<TerrainTile>(m, "TerrainTile")
        .def(py::init<>()) RW(TerrainTile, origin_north) RW(TerrainTile, origin_west) RW(TerrainTile, spacing)
            RW(TerrainTile, columns) RW(TerrainTile, rows) RW(TerrainTile, heights)
        .def("height", &TerrainTile::height)
        .def("contains", &TerrainTile::contains);
    py::class_<GameTerrain>(m, "GameTerrain")
        .def(py::init<>()) RW(GameTerrain, origin_north) RW(GameTerrain, origin_west) RW(GameTerrain, spacing)
            RW(GameTerrain, columns) RW(GameTerrain, rows) RW(GameTerrain, heights)
                RW(GameTerrain, detail_tiles) RO(GameTerrain, maximum_height)
        .def("height", &GameTerrain::height)
        .def("line_of_sight", &GameTerrain::line_of_sight);
    py::class_<GameSession>(m, "GameSession")
        .def(py::init<const std::string &>(), py::arg("log_path") = "bvr_game.log")
        .def("reset", &GameSession::reset)
        .def("submit", &GameSession::submit)
        .def("step", &GameSession::step, py::arg("ticks") = 1, py::call_guard<py::gil_scoped_release>())
        .def("step_exact", &GameSession::step_exact, py::arg("ticks") = 1,
             py::call_guard<py::gil_scoped_release>())
        .def("set_paused", &GameSession::set_paused)
        .def("frame", &GameSession::frame)
        .def("terrain", &GameSession::terrain)
        .def("set_terrain", &GameSession::set_terrain)
        .def("close", &GameSession::close)
        .def(
            "__enter__", [](GameSession &self) -> GameSession & { return self; },
            py::return_value_policy::reference)
        .def("__exit__", [](GameSession &self, py::object, py::object, py::object) { self.close(); });
#undef RW
#undef RO
}
} // namespace bvr_sim
