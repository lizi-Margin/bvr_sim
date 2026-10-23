"""Integration tests of the real C++ simulation, with no window or telemetry."""
import math
import unittest
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native


class GameSessionTests(unittest.TestCase):
    def setUp(self):
        self.sim = native.GameSession("game_session_test.log")
        self.config = native.GameConfig()
        self.config.player_model = "F16"
        self.config.enemy_attacks = False

    def tearDown(self):
        self.sim.close()

    def test_tick_boundary_pause_and_immutable_frame(self):
        self.sim.reset(self.config)
        initial = self.sim.frame()
        command = native.PilotCommand()
        command.heading = 0.7
        self.sim.submit(command)
        self.assertEqual(self.sim.frame().applied_command_tick, 0)
        self.sim.set_paused(True)
        self.sim.step(10)
        self.assertEqual(self.sim.frame().tick, 0)
        self.sim.step_exact(10)
        frame = self.sim.frame()
        self.assertEqual(frame.tick, 10)
        self.assertEqual(frame.applied_command_tick, 1)
        self.assertAlmostEqual(frame.sim_time, 10 * self.config.dt)
        self.assertEqual(initial.tick, 0)
        self.assertNotEqual(initial.entities[0].position, frame.entities[0].position)

    def test_unobserved_target_cannot_lock_or_fire(self):
        self.config.enemy_range = 200000
        self.sim.reset(self.config)
        self.sim.step(5)
        command = native.PilotCommand()
        command.lock = command.fire = True
        command.target_uid = "bandit"
        self.sim.submit(command)
        self.sim.step()
        frame = self.sim.frame()
        self.assertEqual(frame.contacts, [])
        self.assertEqual(frame.selected_target, "")
        self.assertEqual(frame.missiles_left, 4)
        self.assertIn("lock_rejected", [e.kind for e in frame.events])

    def test_real_radar_missile_and_mission_result(self):
        self.config.enemy_range = 3500
        self.sim.reset(self.config)
        self.sim.step(10)
        self.assertIn("bandit", [c.uid for c in self.sim.frame().contacts])
        command = native.PilotCommand()
        command.lock = command.fire = True
        command.target_uid = "bandit"
        self.sim.submit(command)
        self.sim.step()
        self.assertEqual(self.sim.frame().missiles_left, 3)
        self.sim.step(1500)
        frame = self.sim.frame()
        print("AIR_COMBAT", frame.result, frame.tick, [(e.kind, e.message) for e in frame.events])
        self.assertEqual(frame.result, "succeeded")
        self.assertEqual(frame.air_kills, 1)
        self.assertIn("missile_hit", [e.kind for e in frame.events])
        self.sim.reset(self.config)
        self.assertEqual(self.sim.frame().tick, 0)
        self.assertEqual(self.sim.frame().missiles_left, 4)

    def test_ballistic_bomb_terrain_damage_and_result(self):
        self.config.mission = "strike"
        self.sim.reset(self.config)
        pilot = native.PilotCommand()
        self.sim.submit(pilot)
        released = False
        for _ in range(1500):
            frame = self.sim.frame()
            if not released and frame.bomb_impact and abs(frame.bomb_impact[0] - 6000) < 20:
                command = native.PilotCommand()
                command.drop_bomb = True
                self.sim.submit(command)
                released = True
            self.sim.step(2)
            if self.sim.frame().result != "running":
                break
        frame = self.sim.frame()
        print("GROUND_STRIKE", released, frame.result, frame.tick, [(e.kind, e.position) for e in frame.events])
        self.assertTrue(released, "Pilot must reach a release solution through actual flight")
        self.assertEqual(frame.bombs_left, 1)
        self.assertEqual(frame.result, "succeeded")
        self.assertEqual(frame.ground_kills, 1)
        self.assertIn("bomb_impact", [e.kind for e in frame.events])

    def test_terrain_mesh_height_and_occlusion(self):
        terrain = native.GameTerrain()
        terrain.origin_north = terrain.origin_west = 0
        terrain.spacing = 100
        terrain.heights = [0, 100, 0, 100]
        self.assertAlmostEqual(terrain.height(50, 50), 50)
        self.assertFalse(terrain.line_of_sight([0, 50, 10], [100, 50, 10]))
        self.assertTrue(terrain.line_of_sight([0, 50, 200], [100, 50, 200]))
        terrain.heights=[0,0,0,100]
        self.assertEqual(terrain.height(25,25),0)
        self.assertEqual(terrain.height(75,75),50)

    def test_reading_frames_does_not_change_flight(self):
        trajectories = []
        for extra_reads in [False, True]:
            self.sim.reset(self.config)
            pilot = native.PilotCommand()
            pilot.heading = 0.5
            pilot.pitch = 0.1
            self.sim.submit(pilot)
            for _ in range(100):
                self.sim.step()
                if extra_reads:
                    self.sim.frame()
            player = next(e for e in self.sim.frame().entities if e.uid == "player")
            trajectories.append((player.position, player.velocity, player.orientation))
        for a, b in zip(trajectories[0], trajectories[1]):
            for x, y in zip(a, b):
                self.assertAlmostEqual(x, y, places=10)

    def test_seed_map_position_and_validation(self):
        self.config.ground_north=6100
        self.config.player_west=200
        self.sim.reset(self.config)
        first={e.uid:e.position for e in self.sim.frame().entities}
        self.assertEqual(first['depot'],[6100,0,0])
        self.assertEqual(first['player'][1],200)
        self.sim.reset(self.config)
        self.assertEqual(first,{e.uid:e.position for e in self.sim.frame().entities})
        self.config.seed+=1;self.sim.reset(self.config)
        self.assertNotEqual(first['bandit'],next(e.position for e in self.sim.frame().entities if e.uid=='bandit'))
        self.config.speed=float('nan')
        with self.assertRaises(ValueError):self.sim.reset(self.config)

    def test_enemy_weapons_and_player_failure(self):
        self.config.enemy_attacks=True;self.config.enemy_range=7000
        self.sim.reset(self.config)
        warning=False
        for _ in range(300):
            self.sim.step(10);f=self.sim.frame();warning=warning or f.missile_warning
            if f.result!='running':break
        self.assertIn('bandit',[e.actor for e in f.events if e.kind=='missile_launched'])
        self.assertTrue(warning)
        self.assertEqual(f.result,'failed')


if __name__ == "__main__":
    unittest.main()
