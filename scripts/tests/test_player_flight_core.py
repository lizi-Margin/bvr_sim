"""Player assistance directly on source FDMs, without GameSession/rendering."""
import math,unittest
from pathlib import Path
from bvr_game.app import native
from bvr_game.player_profiles import PlayerProfileStore

ROOT=Path(__file__).resolve().parents[2]


class PlayerFlightCoreTests(unittest.TestCase):
    def test_roll_takeover_and_release_use_actual_source_dynamics(self):
        profiles=PlayerProfileStore()
        for model in ['F22','F16','FG-A-10']:
            for sign in [-1,1]:
                with self.subTest(model=model,sign=sign):
                    fdm=(native.YASimFDM(.02,str(ROOT/f'bvr_sim/resources/aircraft/{model}/fdm.xml'))
                         if model.startswith('FG-') else native.JSBSimFDM(.02,model))
                    fdm.reset([0,0,5000],[180 if model.startswith('FG-') else 250,0,0])
                    controller=native.PlayerFlightController();profile=profiles.native_profile(native,model);controller.configure(profile)
                    intent=native.PlayerFlightIntent();intent.direction=[1,0,0];intent.throttle=.85
                    maximum_rate=0.;owned_bank=None
                    for tick in range(750):
                        intent.manual_roll=50<=tick<100;intent.roll_input=sign if intent.manual_roll else 0.
                        controls=controller.update(fdm.world_flight_measurements(),intent,.02)
                        fdm.step_surfaces(controls);state=controller.state()
                        self.assertLessEqual(abs(state.desired_roll_rate),profile.max_roll_rate+1e-10)
                        maximum_rate=max(maximum_rate,abs(fdm.world_flight_measurements().body_rates[0]))
                        if tick==99:owned_bank=fdm.world_flight_measurements().orientation[0]
                    self.assertFalse(fdm.terminated)
                    self.assertGreater(sign*owned_bank,.1)
                    self.assertEqual(controller.state().roll_manual_weight,0)
                    self.assertLess(abs(fdm.world_flight_measurements().body_rates[0]),.1)
                    self.assertLess(maximum_rate,profile.max_roll_rate*1.5)
    def test_raw_manual_preserves_direct_aileron_even_above_assisted_rate(self):
        profiles=PlayerProfileStore();profile=profiles.native_profile(native,'FG-SU-37')
        controller=native.PlayerFlightController();controller.configure(profile)
        fdm=native.YASimFDM(.02,str(ROOT/'bvr_sim/resources/aircraft/FG-SU-37/fdm.xml'))
        fdm.reset([0,0,5000],[200,0,0])
        for _ in range(100):
            fdm.step(aileron=1,elevator=0,rudder=0,throttle=.85)
            if fdm.world_flight_measurements().body_rates[0]>profile.max_roll_rate*1.5:break
        measurements=fdm.world_flight_measurements()
        self.assertGreater(measurements.body_rates[0],profile.max_roll_rate)
        intent=native.PlayerFlightIntent();intent.direction=[1,0,0];intent.manual_roll=True;intent.roll_input=1
        assisted=controller.update(measurements,intent,.02)
        self.assertLess(assisted.aileron,0,'Assisted input should brake an excessive positive roll rate')
        intent.mode=native.PlayerFlightMode.RawManual
        raw=controller.update(measurements,intent,.02)
        self.assertEqual(raw.aileron,1,'Raw manual must still expose direct surfaces')


if __name__=='__main__':unittest.main()
