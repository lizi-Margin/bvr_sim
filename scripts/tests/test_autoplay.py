"""Regression coverage for the ammunition failure found during actual Agent play."""
from dataclasses import replace
import unittest
from bvr_game.playtest import LocalObservation, LocalCombatPilot


def contact_observation():
    return LocalObservation(0, 45.,
        {'position':[0,0,8500], 'velocity':[300,0,0], 'orientation':[0,0,0], 'agl':8500},
        ({'uid':'raider', 'position':[30000,0,8500], 'velocity':[-300,0,0]},),
        (), 'raider', 6, False, False, 'quiet', {'result':'running'},
        {'AIM-120C7':4, 'AIM-9M':2})


class AutoplayPolicyTests(unittest.TestCase):
    def test_short_range_inventory_does_not_trigger_empty_radar_weapon(self):
        pilot=LocalCombatPilot()
        obs=replace(contact_observation(), missiles=2, weapon_counts={'AIM-9M':2})
        self.assertFalse(pilot.command(obs).get('fire',False))

    def test_waits_for_first_shot_before_spending_another_round(self):
        pilot=LocalCombatPilot(shot_interval=55)
        obs=contact_observation()
        self.assertTrue(pilot.command(obs)['fire'])
        # The shot timer starts only when the core actually consumes a missile.
        obs=replace(obs,time=45.5,missiles=5,weapon_counts={'AIM-120C7':3,'AIM-9M':2})
        self.assertFalse(pilot.command(obs).get('fire',False))
        self.assertFalse(pilot.command(replace(obs,time=86)).get('fire',False))
        self.assertTrue(pilot.command(replace(obs,time=101))['fire'])

    def test_incoming_missile_prevents_launch(self):
        obs=replace(contact_observation(),missile_warning=True,
                    warnings=({'missile':True,'bearing':.2},))
        pilot=LocalCombatPilot()
        self.assertFalse(pilot.command(obs).get('fire',False))
        self.assertEqual(pilot.phase,'defend')


if __name__=='__main__':unittest.main()
