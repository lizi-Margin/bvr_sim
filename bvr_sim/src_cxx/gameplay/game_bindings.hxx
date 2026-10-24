#pragma once
#include "game_session.hxx"
#include "simulator/aircraft/player_flight.hxx"
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace bvr_sim {
inline void bind_game_api(pybind11::module_ &m) {
    namespace py = pybind11;
#define RW(T, field) .def_readwrite(#field, &T::field)
#define RO(T, field) .def_readonly(#field, &T::field)
    py::enum_<PlayerFlightMode>(m,"PlayerFlightMode")
        .value("Assisted",PlayerFlightMode::Assisted).value("RawManual",PlayerFlightMode::RawManual);
    py::class_<PlayerFlightIntent>(m,"PlayerFlightIntent").def(py::init<>())
        RW(PlayerFlightIntent,direction) RW(PlayerFlightIntent,throttle)
        RW(PlayerFlightIntent,pitch_input) RW(PlayerFlightIntent,roll_input) RW(PlayerFlightIntent,yaw_input)
        RW(PlayerFlightIntent,manual_pitch) RW(PlayerFlightIntent,manual_roll) RW(PlayerFlightIntent,manual_yaw)
        RW(PlayerFlightIntent,protection) RW(PlayerFlightIntent,mode)
        RW(PlayerFlightIntent,fire) RW(PlayerFlightIntent,drop_bomb) RW(PlayerFlightIntent,lock)
        RW(PlayerFlightIntent,target_uid) RW(PlayerFlightIntent,weapon);
    py::class_<FlightMeasurements>(m,"FlightMeasurements")
        RO(FlightMeasurements,position) RO(FlightMeasurements,velocity) RO(FlightMeasurements,orientation)
        RO(FlightMeasurements,body_rates) RO(FlightMeasurements,alpha) RO(FlightMeasurements,beta)
        RO(FlightMeasurements,normal_g) RO(FlightMeasurements,speed) RO(FlightMeasurements,density)
        RO(FlightMeasurements,gravity_up) RO(FlightMeasurements,reference_frame);
    py::class_<FlightSurfaceControls>(m,"FlightSurfaceControls")
        .def(py::init<>()) RW(FlightSurfaceControls,aileron) RW(FlightSurfaceControls,elevator)
        RW(FlightSurfaceControls,rudder) RW(FlightSurfaceControls,throttle);
    py::class_<PlayerFlightProfile>(m,"PlayerFlightProfile").def(py::init<>())
        RW(PlayerFlightProfile,id) RW(PlayerFlightProfile,version) RW(PlayerFlightProfile,source_hash)
        RW(PlayerFlightProfile,heading_gain) RW(PlayerFlightProfile,bank_gain) RW(PlayerFlightProfile,roll_rate_gain)
        RW(PlayerFlightProfile,pitch_gain) RW(PlayerFlightProfile,pitch_rate_gain)
        RW(PlayerFlightProfile,yaw_damping) RW(PlayerFlightProfile,sideslip_gain)
        RW(PlayerFlightProfile,trim_gain) RW(PlayerFlightProfile,trim_limit)
        RW(PlayerFlightProfile,max_bank) RW(PlayerFlightProfile,max_roll_rate)
        RW(PlayerFlightProfile,max_pitch_rate) RW(PlayerFlightProfile,max_turn_rate)
        RW(PlayerFlightProfile,max_alpha) RW(PlayerFlightProfile,min_alpha)
        RW(PlayerFlightProfile,max_g) RW(PlayerFlightProfile,min_g) RW(PlayerFlightProfile,protection_gain)
        RW(PlayerFlightProfile,reference_speed) RW(PlayerFlightProfile,min_speed)
        RW(PlayerFlightProfile,schedule_min) RW(PlayerFlightProfile,schedule_max)
        RW(PlayerFlightProfile,surface_rate) RW(PlayerFlightProfile,release_seconds)
        RW(PlayerFlightProfile,target_response) RW(PlayerFlightProfile,bank_response)
        RW(PlayerFlightProfile,energy_horizon) RW(PlayerFlightProfile,recovery_speed_ratio) RW(PlayerFlightProfile,recovery_pitch)
        RW(PlayerFlightProfile,reference_density)
        .def("validate",&PlayerFlightProfile::validate);
    py::class_<PlayerFlightState>(m,"PlayerFlightState")
        RO(PlayerFlightState,configured) RO(PlayerFlightState,active) RO(PlayerFlightState,protecting)
        RO(PlayerFlightState,saturated) RO(PlayerFlightState,measured) RO(PlayerFlightState,controls)
        RO(PlayerFlightState,energy_limited) RO(PlayerFlightState,limited_direction)
        RO(PlayerFlightState,target_direction) RO(PlayerFlightState,direction_error) RO(PlayerFlightState,body_direction_error)
        RO(PlayerFlightState,target_bank) RO(PlayerFlightState,roll_error)
        RO(PlayerFlightState,desired_roll_rate) RO(PlayerFlightState,desired_pitch_rate)
        RO(PlayerFlightState,pitch_manual_weight) RO(PlayerFlightState,roll_manual_weight)
        RO(PlayerFlightState,pitch_trim)
        RO(PlayerFlightState,profile_id) RO(PlayerFlightState,profile_hash) RO(PlayerFlightState,mode);
    py::class_<PlayerFlightController>(m,"PlayerFlightController").def(py::init<>())
        .def("configure",&PlayerFlightController::configure)
        .def("update",&PlayerFlightController::update)
        .def("state",&PlayerFlightController::state)
        .def("profile",&PlayerFlightController::profile);
    py::class_<VehicleRoute>(m, "VehicleRoute")
        .def(py::init<>()) RW(VehicleRoute, points) RW(VehicleRoute, speed) RW(VehicleRoute, loop);
    py::class_<GroundUnitSpec>(m, "GroundUnitSpec")
        .def(py::init<>()) RW(GroundUnitSpec, uid) RW(GroundUnitSpec, model) RW(GroundUnitSpec, kind)
            RW(GroundUnitSpec, team) RW(GroundUnitSpec, position) RW(GroundUnitSpec, route)
                RW(GroundUnitSpec, missiles) RW(GroundUnitSpec, mission_target);
    py::class_<GroundState>(m, "GroundState") RO(GroundState, uid) RO(GroundState, model)
        RO(GroundState, kind) RO(GroundState, motion) RO(GroundState, blocked_reason)
            RO(GroundState, contact_surface) RO(GroundState, position) RO(GroundState, velocity)
                RO(GroundState, orientation) RO(GroundState, health) RO(GroundState, speed)
                    RO(GroundState, waypoint) RO(GroundState, route) RO(GroundState, alive)
                        RO(GroundState, parking) RO(GroundState, missiles_left)
                            RO(GroundState, sensor_contacts);
    py::class_<GameConfig>(m, "GameConfig")
        .def(py::init<>()) RW(GameConfig, player_model) RW(GameConfig, enemy_model) RW(GameConfig, mission)
            RW(GameConfig, fdm) RW(GameConfig, library_aircraft) RW(GameConfig, seed) RW(GameConfig, dt)
                RW(GameConfig, enemy_range) RW(GameConfig, altitude) RW(GameConfig, speed)
                    RW(GameConfig, enemy_attacks) RW(GameConfig, enemy_evasion) RW(GameConfig, player_north)
                        RW(GameConfig, player_west) RW(GameConfig, ground_north) RW(GameConfig, ground_west)
                            RW(GameConfig, missiles) RW(GameConfig, bombs) RW(GameConfig, ground_units)
                                RW(GameConfig, intercept_waves) RW(GameConfig, intercept_interval) RW(GameConfig, intercept_timeout);
    py::class_<PilotCommand>(m, "PilotCommand")
        .def(py::init<>()) RW(PilotCommand, uid) RW(PilotCommand, heading) RW(PilotCommand, pitch)
            RW(PilotCommand, throttle) RW(PilotCommand, roll_input) RW(PilotCommand, manual_roll)
                RW(PilotCommand, roll_rate)
                RW(PilotCommand, pitch_input) RW(PilotCommand, manual_pitch)
                RW(PilotCommand, fire) RW(PilotCommand, drop_bomb) RW(PilotCommand, lock)
                    RW(PilotCommand, target_uid) RW(PilotCommand, weapon);
    py::class_<GameContact>(m, "GameContact") RO(GameContact, uid) RO(GameContact, sensor)
        RO(GameContact, position) RO(GameContact, velocity) RO(GameContact, locked);
    py::class_<GameWarning>(m, "GameWarning") RO(GameWarning, uid) RO(GameWarning, bearing)
        RO(GameWarning, range) RO(GameWarning, localized) RO(GameWarning, missile);
    py::class_<GameEntity>(m, "GameEntity") RO(GameEntity, uid) RO(GameEntity, model) RO(GameEntity, kind)
        RO(GameEntity, team) RO(GameEntity, alive) RO(GameEntity, position) RO(GameEntity, velocity)
            RO(GameEntity, orientation) RO(GameEntity, health) RO(GameEntity, mach) RO(GameEntity, pylons)
                RO(GameEntity, throttle) RO(GameEntity, weapon_age) RO(GameEntity, motor_burning)
                    RO(GameEntity, animation_properties);
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
                RO(GameFrame, warnings) RO(GameFrame, ground_units) RO(GameFrame, events)
                    RO(GameFrame, missiles_left) RO(GameFrame, bombs_left) RO(GameFrame, air_kills)
                        RO(GameFrame, ground_kills) RO(GameFrame, radar_warning)
                            RO(GameFrame, missile_warning) RO(GameFrame, bomb_impact)
                                    RO(GameFrame, mission_wave) RO(GameFrame, mission_total) RO(GameFrame, mission_kills_required) RO(GameFrame, next_wave_time)
                                    RO(GameFrame, radar_mode) RO(GameFrame, rwr_mode)
                                    RO(GameFrame, enemy_behavior) RO(GameFrame, radar_range)
                                        RO(GameFrame, envelope) RO(GameFrame, missiles);
    py::class_<ContactSurface>(m, "ContactSurface")
        .def(py::init<>()) RW(ContactSurface, id) RW(ContactSurface, material) RW(ContactSurface, vertices)
            RW(ContactSurface, indices) RW(ContactSurface, drivable)
        .def("height", &ContactSurface::height)
        .def("prepare", &ContactSurface::prepare);
    py::class_<CollisionBox>(m, "CollisionBox")
        .def(py::init<>()) RW(CollisionBox, id) RW(CollisionBox, center) RW(CollisionBox, half_size)
            RW(CollisionBox, yaw);
    py::class_<WaterRegion>(m, "WaterRegion").def(py::init<>()) RW(WaterRegion, id) RW(WaterRegion, polygon);
    py::class_<GroundContact>(m, "GroundContact") RO(GroundContact, height) RO(GroundContact, pitch)
        RO(GroundContact, roll) RO(GroundContact, grade) RO(GroundContact, water) RO(GroundContact, supported)
            RO(GroundContact, surface_id);
    py::class_<TerrainTile>(m, "TerrainTile")
        .def(py::init<>()) RW(TerrainTile, origin_north) RW(TerrainTile, origin_west) RW(TerrainTile, spacing)
            RW(TerrainTile, columns) RW(TerrainTile, rows) RW(TerrainTile, heights)
        .def("height", &TerrainTile::height)
        .def("contains", &TerrainTile::contains);
    py::class_<GameTerrain>(m, "GameTerrain")
        .def(py::init<>()) RW(GameTerrain, origin_north) RW(GameTerrain, origin_west) RW(GameTerrain, spacing)
            RW(GameTerrain, columns) RW(GameTerrain, rows) RW(GameTerrain, heights)
                RW(GameTerrain, detail_tiles) RO(GameTerrain, maximum_height)
                    RW(GameTerrain, contact_surfaces) RW(GameTerrain, obstacles)
                        RW(GameTerrain, water_regions)
        .def("height", &GameTerrain::height)
        .def("collision_height", &GameTerrain::collision_height)
        .def("contact", &GameTerrain::contact, py::arg("north"), py::arg("west"), py::arg("yaw") = 0,
             py::arg("reference_height") = INFINITY, py::arg("max_step") = .6)
        .def("prepare_surfaces", &GameTerrain::prepare_surfaces)
        .def("line_of_sight", &GameTerrain::line_of_sight);
    py::class_<GameSession>(m, "GameSession")
        .def(py::init<const std::string &>(), py::arg("log_path") = "bvr_game.log")
        .def("reset", &GameSession::reset)
        .def("submit", &GameSession::submit)
        .def("submit_player",&GameSession::submit_player)
        .def("configure_player_flight",&GameSession::configure_player_flight)
        .def("player_flight_profile",&GameSession::player_flight_profile)
        .def("player_flight_state",&GameSession::player_flight_state)
        .def("step", &GameSession::step, py::arg("ticks") = 1, py::call_guard<py::gil_scoped_release>())
        .def("step_exact", &GameSession::step_exact, py::arg("ticks") = 1,
             py::call_guard<py::gil_scoped_release>())
        .def("set_paused", &GameSession::set_paused)
        .def("frame", &GameSession::frame)
        .def("terrain", &GameSession::terrain)
        .def("set_terrain", &GameSession::set_terrain)
        .def("spawn_ground", &GameSession::spawn_ground)
        .def("set_ground_route", &GameSession::set_ground_route)
        .def("park_ground", &GameSession::park_ground)
        .def("begin_recording", &GameSession::begin_recording)
        .def("end_recording", &GameSession::end_recording)
        .def("flush_recording", &GameSession::flush_recording)
        .def("close", &GameSession::close)
        .def(
            "__enter__", [](GameSession &self) -> GameSession & { return self; },
            py::return_value_policy::reference)
        .def("__exit__", [](GameSession &self, py::object, py::object, py::object) { self.close(); });
#undef RW
#undef RO
}
} // namespace bvr_sim
