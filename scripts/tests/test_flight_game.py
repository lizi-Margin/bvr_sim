"""Input mapping and full menu/combat loop using real simulation, no GPU needed."""
import tempfile,unittest
from types import SimpleNamespace
from bvr_game.app import FlightGame
from bvr_game.presentation import mouse_pitch,curve
import math
class FlightGameTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.game=FlightGame(output=self.temp.name)
        self.game.config.enemy_attacks=False;self.game.config.enemy_range=3500
    def tearDown(self):self.game.close();self.temp.cleanup()
    def key(self,key):
        return self.game.input(SimpleNamespace(held=[key],pressed=[key],x=960,y=540,quit=False),1/60)
    def test_hangar_fly_lock_fire_result_fly_again(self):
        self.assertEqual(self.game.mode,'hangar');self.key(50);self.assertEqual(self.game.config.player_model,'F16')
        self.key(13);self.assertEqual(self.game.mode,'flight');self.game.step(10)
        self.key(82);self.game.step();self.assertEqual(self.game.sim.frame().selected_target,'bandit')
        self.key(32);self.game.step();self.assertEqual(self.game.sim.frame().missiles_left,3)
        self.game.step(1500);self.assertEqual(self.game.mode,'result');self.assertEqual(self.game.sim.frame().result,'succeeded')
        self.key(13);self.assertEqual(self.game.mode,'flight');self.assertEqual(self.game.sim.frame().tick,0)
        self.key(27);self.assertEqual(self.game.mode,'hangar')
    def test_mouse_aim_controls_real_aircraft(self):
        self.key(13);before=self.game.player().orientation
        event=SimpleNamespace(held=[],pressed=[],x=700,y=400,quit=False)
        for _ in range(150):self.game.input(event,.02);self.game.step()
        after=self.game.player().orientation
        self.assertGreater(abs(after[2]-before[2]),.05)
        self.assertGreater(self.game.sim.frame().applied_command_tick,0)
    def test_pitch_reaches_full_aim_range_and_keyboard_moves_real_aircraft(self):
        self.assertAlmostEqual(mouse_pitch(230,1080),math.pi/4)
        self.assertAlmostEqual(mouse_pitch(780,1080),-math.pi/4)
        self.assertEqual(mouse_pitch(540,1080),0)
        self.assertAlmostEqual(mouse_pitch(460,2160),math.pi/4)
        for key,sign in [(87,-1),(83,1)]:
            self.game.start();before=self.game.player().orientation[1]
            event=SimpleNamespace(held=[key],pressed=[],x=960,y=540,quit=False)
            for _ in range(75):self.game.input(event,.02);self.game.step()
            p=self.game.player()
            self.assertTrue(p.alive)
            # Core NWU pitch is negative nose-up; vertical velocity is positive up.
            self.assertGreater(-sign*(p.orientation[1]-before),math.radians(3))
            self.assertGreater(sign*p.velocity[2],5)
            # Assisted manual pitch owns the axis, while actual deflection is
            # still constrained by the configured alpha/G protection.
            state=self.game.sim.player_flight_state()
            self.assertEqual(state.pitch_manual_weight,1)
            self.assertLessEqual(abs(p.animation_properties['controls/flight/elevator']),1)
            self.assertLess(abs(p.orientation[0]),math.radians(5),'Pure pitch unexpectedly rolled the aircraft')
        # Releasing the key restores angle assist, rather than latching the elevator.
        self.game.input(SimpleNamespace(held=[],pressed=[],x=960,y=540,quit=False),.02);self.game.step()
        self.assertLess(abs(self.game.player().animation_properties['controls/flight/elevator']),1)

    def test_imported_hangar_search_select_fly_and_return_to_combat_aircraft(self):
        self.assertGreaterEqual(len(self.game.aircraft_rows),152)
        def event(keys=(),x=960,y=540):
            return self.game.input(SimpleNamespace(held=[],pressed=list(keys),x=x,y=y,wheel=0,quit=False),.02)
        event([191]);event([55]);event([51]);event([55]);event([13])
        rows=self.game.filtered_aircraft();self.assertTrue(any(r['id']=='FG-737-800' for r in rows))
        self.game.select_aircraft('FG-737-800');self.assertTrue(self.game.config.library_aircraft)
        self.assertEqual(self.game.config.mission,'training');self.assertEqual(self.game.config.missiles,0)
        event([13]);self.game.step(20);self.assertEqual(self.game.mode,'flight');self.assertTrue(self.game.player().alive)
        event([27]);self.game.select_aircraft('F22');self.assertFalse(self.game.config.library_aircraft)
        self.game.config.mission='air';self.game.start();self.game.step(10)
        self.assertEqual(self.game.player().model,'F22');self.assertGreater(self.game.sim.frame().missiles_left,0)

    def test_yasim_keyboard_release_with_mouse_still_off_center(self):
        # The earlier exact-center regression missed the normal parked cursor:
        # its tiny heading offset used to reengage near-zero bank-angle assist.
        for model in ['FG-A-10','FG-SU-37','FG-Hunter','FG-YF-23']:
            for direction in [-1,1]:
                with self.subTest(model=model,direction=direction):
                    self.game.select_aircraft(model);self.game.start()
                    mouse_x=960+77*direction
                    for tick in range(60):
                        event=SimpleNamespace(held=[68 if direction>0 else 65],pressed=[],x=mouse_x,y=540,quit=False)
                        self.game.input(event,.02);self.game.step()
                        if self.game.player().orientation[0]*direction>.4:break
                    banked=self.game.player()
                    self.assertGreater(banked.orientation[0]*direction,.4)
                    for _ in range(300):
                        event=SimpleNamespace(held=[],pressed=[],x=mouse_x,y=540,quit=False)
                        self.game.input(event,.02);self.game.step()
                    final=self.game.player()
                    self.assertTrue(final.alive)
                    # New pointing assistance tracks the small off-centre
                    # direction; it no longer latches the old bank-rate input.
                    state=self.game.sim.player_flight_state()
                    self.assertEqual(state.roll_manual_weight,0)
                    self.assertGreater(final.orientation[0]*direction,.1)
                    self.assertLess(abs(final.orientation[0]-state.target_bank),.15)
                    self.assertLess(math.remainder(final.orientation[2]-banked.orientation[2],2*math.pi)*direction,-.02)

    def test_yasim_mouse_can_establish_bank_and_countersteer(self):
        self.game.select_aircraft('FG-A-10');self.game.start()
        def move(x,ticks):
            event=SimpleNamespace(held=[],pressed=[],x=x,y=540,quit=False)
            for _ in range(ticks):self.game.input(event,.02);self.game.step()
        move(1500,150)
        banked=self.game.player()
        self.assertTrue(banked.alive)
        self.assertGreater(banked.orientation[0],math.radians(25))
        move(960,250)
        centered=self.game.player()
        self.assertTrue(centered.alive)
        self.assertLess(abs(centered.orientation[0]),math.radians(5))
        self.assertLess(centered.orientation[2]-banked.orientation[2],-.02)
        move(420,100)
        self.assertLess(self.game.player().orientation[0],centered.orientation[0]-.2)

    def test_free_look_keeps_intent_but_pitch_keys_still_own_axis(self):
        self.game.config.mission='training';self.game.start()
        original=list(self.game.player_input.direction)
        for _ in range(50):
            self.game.input(SimpleNamespace(held=[67,83],pressed=[],x=1500,y=200,quit=False),.02)
            self.game.step()
        self.assertEqual(self.game.player_input.direction,original)
        self.assertEqual(self.game.sim.player_flight_state().pitch_manual_weight,1)
        self.assertLess(self.game.player().orientation[1],-.05)
        rate=self.game.sim.player_flight_state().measured.body_rates[1]
        for _ in range(50):
            self.game.input(SimpleNamespace(held=[87,83],pressed=[],x=960,y=540,quit=False),.02)
            self.game.step()
        self.assertEqual(self.game.sim.player_flight_state().pitch_manual_weight,1)
        self.assertLess(abs(self.game.sim.player_flight_state().measured.body_rates[1]),abs(rate)*.5+.01)
if __name__=='__main__':unittest.main()
