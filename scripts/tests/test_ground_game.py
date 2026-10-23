"""Typed game adaptation, validation and deterministic reset over real core ground objects."""
import tempfile,unittest
from pathlib import Path
from bvr_game.app import native,serialize
from bvr_game.aircraft import aircraft_catalog

class GroundGameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.session=native.GameSession(str(Path(self.temp.name)/'sim.log'))
        self.terrain=native.GameTerrain();self.terrain.origin_north=-1000;self.terrain.origin_west=-1000;self.terrain.spacing=2000
        self.session.set_terrain(self.terrain);self.config=native.GameConfig();self.config.mission='training';self.config.enemy_attacks=False
        self.session.reset(self.config)
    def tearDown(self):self.session.close();self.temp.cleanup()
    def vehicle(self):
        s=native.GroundUnitSpec();s.uid='truck';s.position=[0,0,0]
        route=native.VehicleRoute();route.points=[[0,0],[60,0],[60,60]];route.speed=5;s.route=route
        return s
    def ground(self):return next(s for s in self.session.frame().ground_units if s.uid=='truck')
    def test_pause_exact_step_and_braking_are_core_state(self):
        self.session.spawn_ground(self.vehicle());self.session.step(200);self.assertGreater(self.ground().position[0],10)
        self.session.set_paused(True);self.session.park_ground('truck',True);before=self.ground().position
        self.session.step(100);self.assertEqual(before,self.ground().position)
        self.session.step_exact(100);self.assertLess(self.ground().speed,.01)
        stopped=self.ground().position;self.session.step_exact(20);self.assertEqual(stopped,self.ground().position)
        self.session.park_ground('truck',False);self.session.step_exact(100);self.assertGreater(self.ground().position[0],stopped[0]+1)
    def test_declared_spawn_and_commands_reproduce_full_frame_after_reset(self):
        self.config.ground_units=[self.vehicle()]
        def run():
            self.session.reset(self.config);self.session.step(150);self.session.park_ground('truck',True);self.session.step(100)
            self.session.park_ground('truck',False);self.session.step(200);return serialize(self.session.frame())
        self.assertEqual(run(),run())
    def test_warning_noise_replays_every_intermediate_frame_after_reset(self):
        self.config.mission='air';self.config.enemy_attacks=True;self.config.enemy_range=50000;self.config.seed=7
        def run():
            self.session.reset(self.config);frames=[]
            for _ in range(20):
                command=native.PilotCommand();command.throttle=.85;self.session.submit(command);self.session.step(5)
                frames.append(serialize(self.session.frame()))
            self.assertTrue(any(f['warnings'] for f in frames))
            return frames
        self.assertEqual(run(),run())
    def test_invalid_spawn_route_and_unknown_control_fail_explicitly(self):
        self.session.spawn_ground(self.vehicle())
        with self.assertRaises(ValueError):self.session.spawn_ground(self.vehicle())
        with self.assertRaises(ValueError):self.session.park_ground('missing',True)
        route=native.VehicleRoute();route.points=[[float('nan'),0]]
        with self.assertRaises(ValueError):self.session.set_ground_route('truck',route)
    def test_aircraft_capabilities_reject_f4_amraam_and_f15_bombs(self):
        self.config.player_model='F4N';self.config.missiles=1;self.config.bombs=0
        with self.assertRaises(ValueError):self.session.reset(self.config)
        self.config.player_model='F15';self.config.missiles=4;self.config.bombs=1
        with self.assertRaises(ValueError):self.session.reset(self.config)
        rows=aircraft_catalog()['aircraft'];self.assertEqual([r['id'] for r in rows],['F22','F16','F15','F18','F4N'])
        self.assertNotIn('AIM-120C7',next(r for r in rows if r['id']=='F4N')['supported_weapons'])
    def test_contact_surface_validation_and_overhead_reference(self):
        surface=native.ContactSurface();surface.id='bridge';surface.vertices=[[-20,-5,10],[20,-5,10],[-20,5,10],[20,5,10]];surface.indices=[0,1,2,1,3,2]
        self.terrain.contact_surfaces=[surface];self.terrain.prepare_surfaces()
        self.assertEqual(self.terrain.height(0,0),0);self.assertEqual(self.terrain.contact(0,0).height,10)
        self.assertEqual(self.terrain.contact(0,0,0,0).height,0)
        surface.indices=[0,1,99]
        with self.assertRaises(ValueError):surface.prepare()

if __name__=='__main__':unittest.main()
