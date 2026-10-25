"""Direct source-FDM numerical regression; no session, renderer or second physics."""
import math,unittest
import numpy as np
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native
from bvr_game.player_profiles import PlayerProfileStore


class JSBSimSubstepTests(unittest.TestCase):
    def test_integrator_reports_bounded_steps_and_preserves_constructor(self):
        for outer,maximum,count in [(.02,.005,4),(.021,.005,5),(.003,.005,1),(.1,.005,20),(.02,.02,1)]:
            fdm=native.JSBSimFDM(outer,'F16',maximum)
            self.assertEqual(fdm.inner_steps,count)
            self.assertAlmostEqual(fdm.inner_dt*count,outer,places=14)
            self.assertLessEqual(fdm.inner_dt,maximum+1e-15)
        self.assertAlmostEqual(native.JSBSimFDM(.02,'F16').inner_dt,.005)
        precise=.00333333333331
        self.assertAlmostEqual(native.JSBSimFDM(.02,'F16',precise).max_inner_dt,precise,places=16)
        for invalid in [0.,-.01,.03,float('nan'),float('inf')]:
            with self.assertRaises((ValueError,OverflowError)):native.JSBSimFDM(.02,'F16',invalid)

    def test_shared_substeps_equal_same_fdm_with_explicit_held_controls(self):
        outer=native.JSBSimFDM(.02,'F16');inner=native.JSBSimFDM(.005,'F16')
        for fdm in [outer,inner]:fdm.reset([-20000,0,3000],[500,0,0],[0,0,0])
        controls=native.FlightSurfaceControls();controls.throttle=.95
        for tick in range(150):
            controls.elevator=-.015*math.sin(tick*.02)
            outer.step_surfaces(controls)
            for _ in range(4):inner.step_surfaces(controls)
            a=outer.world_flight_measurements();b=inner.world_flight_measurements()
            for key in ['position','velocity','orientation','body_rates']:
                np.testing.assert_allclose(getattr(a,key),getattr(b,key),rtol=0,atol=1e-10,err_msg=key)

    def test_high_dynamic_pressure_pitch_is_stable_with_unchanged_player_profile(self):
        profiles=PlayerProfileStore();bounds=[]
        for maximum in [.02,.005]:
            fdm=native.JSBSimFDM(.02,'F16',maximum);fdm.reset([-20000,0,3000],[500,0,0],[0,0,0])
            controller=native.PlayerFlightController();controller.configure(profiles.native_profile(native,'F16'))
            intent=native.PlayerFlightIntent();intent.direction=[1,0,0];intent.throttle=.95;loads=[];rates=[]
            for _ in range(200):
                controls=controller.update(fdm.world_flight_measurements(),intent,.02);fdm.step_surfaces(controls)
                m=fdm.world_flight_measurements();loads.append(m.normal_g);rates.append(abs(m.body_rates[1]))
            bounds.append((min(loads),max(loads),max(rates)))
        self.assertGreater(bounds[0][1],10.,'The preserved20msfailure must actually reproduce')
        self.assertGreater(bounds[1][0],-.5)
        self.assertLess(bounds[1][1],4.)
        self.assertLess(bounds[1][2],.2)


if __name__=='__main__':unittest.main()
