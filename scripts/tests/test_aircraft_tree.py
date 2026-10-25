"""Catalog completeness, honest historical metadata, and tree reachability."""
import unittest
from bvr_game.aircraft import aircraft_catalog
from bvr_game.aircraft_tree import document,history,countries,ordered,layout,ROLES

class AircraftTreeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.rows=aircraft_catalog(include_library=True)['aircraft']
    def test_every_registered_aircraft_has_one_sourced_classification(self):
        self.assertEqual({r['id'] for r in self.rows},{r['id'] for r in document()['aircraft']})
        allowed={r['id'] for r in document()['countries']}
        for row in self.rows:
            h=history(row);self.assertIn(h['country'],allowed);self.assertIn(h['role'],dict(ROLES))
            self.assertTrue(h['references'],row['id'])
            self.assertTrue(h['decade'] is None and h['status']=='fictional' or isinstance(h['decade'],int) and h['decade']%10==0)
    def test_country_partition_and_expanded_tree_reach_every_resource_once(self):
        seen=[]
        for country in countries(self.rows):
            rows=ordered(self.rows,country['id']);seen.extend(r['id'] for r in rows)
            base=layout(rows);expanded={n['group'] for n in base['nodes'] if n['kind']=='family'}
            full=layout(rows,expanded)
            actual=[n['row']['id'] for n in full['nodes'] if n['kind']=='aircraft']
            self.assertCountEqual(actual,[r['id'] for r in rows]);self.assertEqual(len(actual),len(set(actual)))
            decades=[b['decade'] for b in full['bands'] if b['decade'] is not None]
            self.assertEqual(decades,sorted(decades))
            for node in full['nodes']:self.assertEqual(ROLES[node['lane']][0],history(node['row'])['role'])
        self.assertCountEqual(seen,[r['id'] for r in self.rows])
    def test_non_flying_and_fictional_aircraft_are_not_assigned_fake_first_flights(self):
        for id in ['FG-j7w','FG-Messerschmitt-P1101','FG-Messerschmitt-Libelle','FG-PZL-230F','FG-FMA-IA36-Condor']:
            self.assertEqual(history(id)['status'],'paper');self.assertEqual(history(id)['date_basis'],'design_or_exhibition')
        for id in ['FG-Carreidas','FG-RainbowRacer71']:
            self.assertIsNone(history(id)['decade']);self.assertEqual(history(id)['country'],'fictional')
    def test_design_origin_is_distinct_from_operator_and_joint_projects(self):
        self.assertEqual(history('FG-F18-CAF')['country'],'usa')
        self.assertEqual(history('FG-AN-225')['country'],'ussr')
        for id in ['FG-Concorde','FG-eurofighter','FG-Alphajet','FG-T7-RedHawk']:
            self.assertEqual(history(id)['country'],'joint')

if __name__=='__main__':unittest.main()
