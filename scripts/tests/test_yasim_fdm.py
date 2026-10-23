"""Observable standalone YASim regressions. Build native module before running."""
import math
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'bvr_sim/build/Release'))
import bvr_sim_cpp as native


class YASimDynamics(unittest.TestCase):
    def make(self, dt=.02):
        fdm = native.YASimFDM(dt, str(ROOT / 'bvr_sim/resources/aircraft/FG-SU-37/fdm.xml'))
        fdm.reset([0., 0., 5000.], [200., 0., 0.])
        return fdm

    def run_for(self, fdm, seconds=2., throttle=.7):
        for _ in range(round(seconds / self.dt)):
            fdm.advance(0., 0., throttle)
        return tuple(fdm.position + fdm.velocity + fdm.rpy)

    def test_time_units_and_nwu_axes(self):
        fdm = self.make(.1)
        fdm.step(throttle=.7)
        self.assertGreater(fdm.position[0], 19.)
        self.assertLess(fdm.position[0], 21.)
        self.assertLess(abs(fdm.position[1]), .01)
        fdm.reset([0., 0., 5000.], [0., 200., 0.], [0., 0., math.pi / 2])
        fdm.step(throttle=.7)
        self.assertGreater(fdm.position[1], 19.)
        self.assertLess(abs(fdm.position[0]), .01)

    def test_reset_determinism_and_instance_isolation(self):
        self.dt = .02
        first, unrelated = self.make(), self.make()
        expected = self.run_for(first)
        self.run_for(unrelated, throttle=.1)
        first.reset([0., 0., 5000.], [200., 0., 0.])
        self.assertEqual(expected, self.run_for(first))
        self.assertFalse(first.terminated)

    def test_throttle_changes_measured_motion(self):
        self.dt = .02
        idle, full = self.make(), self.make()
        self.run_for(idle, 5., .05)
        self.run_for(full, 5., 1.)
        self.assertGreater(full.position[0] - idle.position[0], 5.)
        self.assertGreater(math.dist(full.velocity, [0., 0., 0.]), math.dist(idle.velocity, [0., 0., 0.]))

    def test_dt_subdivision_and_ground_termination_reset(self):
        a, b = self.make(.02), self.make(.01)
        self.dt = .02
        state_a = self.run_for(a)
        self.dt = .01
        state_b = self.run_for(b)
        self.assertLess(math.dist(state_a[:3], state_b[:3]), .2)
        a.reset([0., 0., .1], [200., 0., -100.])
        for _ in range(10):
            a.step()
        self.assertTrue(a.terminated)
        a.reset([0., 0., 5000.], [200., 0., 0.])
        a.step()
        self.assertFalse(a.terminated)
        self.assertTrue(all(math.isfinite(x) for x in a.position))

    def test_hybrid_prop_jet_airborne_ground_callback(self):
        fdm = native.YASimFDM(.02, str(ROOT / 'bvr_sim/resources/aircraft/FG-Lockheed-P-2-Neptune/fdm.xml'))
        fdm.reset([0., 0., 3657.6], [92.6, 0., 0.])
        for _ in range(50):
            fdm.advance(0., 0., .7)
        self.assertFalse(fdm.terminated)
        self.assertTrue(all(math.isfinite(x) for x in fdm.position + fdm.velocity))
        self.assertGreater(fdm.position[0], 70.)
        self.assertGreater(fdm.position[2], 3600.)

    def test_surface_input_changes_actual_attitude(self):
        left, right = self.make(), self.make()
        for _ in range(50):
            left.step(aileron=-.3, elevator=0., rudder=0., throttle=.7)
            right.step(aileron=.3, elevator=0., rudder=0., throttle=.7)
        self.assertFalse(left.terminated or right.terminated)
        self.assertGreater(abs(left.rpy[0] - right.rpy[0]), .05)

    def test_neutral_heading_does_not_command_wings_level(self):
        # A centered mouse/released A/D is not a request to erase the bank.
        # Check actual turning motion, not just the control property value.
        for model in ['FG-SU-37', 'FG-A-10', 'FG-Hunter']:
            for bank in [-.4, .4]:
                with self.subTest(model=model, bank=bank):
                    fdm = native.YASimFDM(.02, str(ROOT / f'bvr_sim/resources/aircraft/{model}/fdm.xml'))
                    fdm.reset([0., 0., 5000.], [200., 0., 0.], [bank, 0., 0.])
                    for _ in range(200):
                        fdm.advance(0., 0., .7)
                    self.assertFalse(fdm.terminated)
                    self.assertGreater(fdm.rpy[0] * math.copysign(1, bank), .25)
                    self.assertLess(fdm.rpy[2] * math.copysign(1, bank), -.03)
                    self.assertGreater(abs(fdm.position[1]), 5.)

    def test_heading_assist_still_banks_and_turns_both_directions(self):
        for heading in [-.6, .6]:
            with self.subTest(heading=heading):
                fdm = self.make()
                for _ in range(200):
                    fdm.advance(heading, 0., .7)
                self.assertFalse(fdm.terminated)
                self.assertGreater(fdm.rpy[2] * math.copysign(1, heading), .05)
                self.assertLess(fdm.rpy[0] * math.copysign(1, heading), -.25)

    def test_rate_mode_overrides_heading_assist_without_erasing_bank(self):
        for bank in [-.5,.5]:
            with self.subTest(bank=bank):
                fdm=self.make();fdm.reset([0.,0.,5000.],[200.,0.,0.],[bank,0.,0.])
                for _ in range(500):
                    # A small contradictory heading target must not engage
                    # angle feedback while rate mode explicitly owns roll.
                    fdm.advance(.003,0.,.7,roll_rate=0.)
                self.assertFalse(fdm.terminated)
                self.assertGreater(fdm.rpy[0]*math.copysign(1,bank),.4)
                self.assertLess(fdm.rpy[2]*math.copysign(1,bank),-.1)

    def test_engine_neutral_surfaces_do_not_force_wings_level(self):
        fdm=self.make();fdm.reset([0.,0.,5000.],[200.,0.,0.],[.5,0.,0.])
        for _ in range(500):fdm.step(aileron=0.,elevator=0.,rudder=0.,throttle=.7)
        self.assertFalse(fdm.terminated)
        self.assertGreater(fdm.rpy[0],.4)
        self.assertLess(fdm.rpy[2],-.1)

    def test_source_auxiliary_control_branches_are_not_stick_aliases(self):
        for model,aux in [('FG-YF-23','/autopilot/FCS/controls/flight/speedbrake-aileron-norm'),
                          ('FG-Buccaneer','/controls/flight/aileron-autostab')]:
            with self.subTest(model=model):
                fdm=native.YASimFDM(.02,str(ROOT/f'bvr_sim/resources/aircraft/{model}/fdm.xml'))
                fdm.reset([0.,0.,5000.],[200.,0.,0.])
                fdm.set_property(aux,.07)
                for _ in range(50):fdm.step(aileron=.2,throttle=.7)
                self.assertFalse(fdm.terminated)
                self.assertGreater(fdm.rpy[0],.02)
                self.assertAlmostEqual(fdm.property(aux),.07)


if __name__ == '__main__':
    unittest.main()
