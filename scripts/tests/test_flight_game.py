"""Input mapping and full menu/combat loop using real simulation, no GPU needed."""
import tempfile,unittest
from types import SimpleNamespace
from bvr_game.app import FlightGame
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
if __name__=='__main__':unittest.main()
