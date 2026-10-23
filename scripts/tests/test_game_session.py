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

    def test_manual_pitch_validation_and_optional_compatibility(self):
        self.sim.reset(self.config)
        command=native.PilotCommand()
        self.assertFalse(command.manual_pitch)
        command.manual_pitch=True;command.pitch_input=float('nan')
        with self.assertRaises(ValueError):self.sim.submit(command)
        command.pitch_input=5
        self.sim.submit(command);self.sim.step()
        player=next(e for e in self.sim.frame().entities if e.uid=='player')
        self.assertEqual(player.animation_properties['controls/flight/elevator'],-1)

    def test_optional_roll_rate_validation_and_raw_aileron_priority(self):
        command=native.PilotCommand();self.assertIsNone(command.roll_rate)
        self.sim.reset(self.config);command.roll_rate=0.
        with self.assertRaises(ValueError):self.sim.submit(command)
        self.config.player_model='FG-A-10';self.config.library_aircraft=True
        self.config.fdm='auto';self.config.mission='training'
        self.config.missiles=self.config.bombs=0
        self.sim.reset(self.config);command.roll_rate=float('nan')
        with self.assertRaises(ValueError):self.sim.submit(command)
        command.roll_rate=-1.;command.manual_roll=True;command.roll_input=.2
        self.sim.submit(command);self.sim.step(50)
        p=next(e for e in self.sim.frame().entities if e.uid=='player')
        self.assertTrue(p.alive)
        self.assertAlmostEqual(p.animation_properties['controls/flight/aileron'],.2,places=6)
        self.assertGreater(p.orientation[0],.05)

    def test_imported_jsbsim_external_flight_controls_reach_the_fdm(self):
        self.config.player_model='FG-737-800';self.config.library_aircraft=True
        self.config.fdm='auto';self.config.mission='training'
        self.config.missiles=self.config.bombs=0;self.config.altitude=5000;self.config.speed=200
        pitches=[]
        for stick in [1,-1]:
            self.sim.reset(self.config)
            command=native.PilotCommand();command.manual_pitch=True;command.pitch_input=stick
            command.manual_roll=True;command.roll_input=0;self.sim.submit(command);self.sim.step(100)
            player=next(e for e in self.sim.frame().entities if e.uid=='player')
            self.assertTrue(player.alive);pitches.append(-player.orientation[1])
        self.assertGreater(pitches[0]-pitches[1],math.radians(5))

    def test_ordinary_f15_uses_imported_f15c_dynamics(self):
        self.config.fdm='auto';self.config.mission='training'
        self.config.missiles=self.config.bombs=0
        self.config.altitude=5000;self.config.speed=200
        trajectories=[]
        for model,library in [('F15',False),('FG-F15C',True)]:
            self.config.player_model=model;self.config.library_aircraft=library
            self.sim.reset(self.config);trajectory=[]
            for tick in range(300):
                command=native.PilotCommand();command.throttle=.7
                command.heading=.3 if tick<150 else -.2
                command.pitch=.1 if tick<100 else 0.
                self.sim.submit(command);self.sim.step()
                player=next(e for e in self.sim.frame().entities if e.uid=='player')
                self.assertTrue(player.alive)
                self.assertEqual(player.model,model)
                trajectory.append((player.position,player.velocity,player.orientation))
            trajectories.append(trajectory)
        self.assertEqual(trajectories[0],trajectories[1])
        # The ordinary selection still supports its armed air-to-air loadout.
        self.config.player_model='F15';self.config.library_aircraft=False
        self.config.missiles=6;self.sim.reset(self.config)
        self.assertEqual(self.sim.frame().missiles_left,6)

    def test_yasim_manual_bank_survives_centered_input_and_keeps_turning(self):
        self.config.library_aircraft=True;self.config.fdm='auto'
        self.config.mission='training';self.config.missiles=self.config.bombs=0
        self.config.altitude=5000;self.config.speed=200
        for model in ['FG-A-10','FG-SU-37']:
            for direction in [-1,1]:
                with self.subTest(model=model,direction=direction):
                    self.config.player_model=model;self.sim.reset(self.config)
                    # Same release path as the interactive clients: heading is
                    # refreshed from the current aircraft attitude each tick.
                    for tick in range(200):
                        p=next(e for e in self.sim.frame().entities if e.uid=='player')
                        c=native.PilotCommand();c.heading=p.orientation[2];c.throttle=.7
                        c.manual_roll=tick<25;c.roll_input=.2*direction
                        self.sim.submit(c);self.sim.step()
                        if tick==49:
                            banked=next(e for e in self.sim.frame().entities if e.uid=='player')
                    p=next(e for e in self.sim.frame().entities if e.uid=='player')
                    self.assertTrue(p.alive)
                    self.assertGreater(p.orientation[0]*direction,.15)
                    self.assertGreater(p.orientation[0]/banked.orientation[0],.7)
                    self.assertLess((p.orientation[2]-banked.orientation[2])*direction,-.01)

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
