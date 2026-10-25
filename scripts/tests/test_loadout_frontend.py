"""Hit-test transactions and actual player weapon switching, backed by the core."""
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bvr_game.app import FlightGame,serialize

class LoadoutFrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.g=FlightGame(output=root/'client',user_settings=root/'preferences.json');self.g.logs_enabled=False
        self.g.select_aircraft('F16');self.f=self.g.frontend
    def tearDown(self):self.g.close();self.temp.cleanup()
    def event(self,pressed=(),x=960,y=540):
        return self.g.input(SimpleNamespace(pressed=list(pressed),held=[],x=x,y=y,quit=False,wheel=0),.02)
    def test_hangar_uses_defined_stations_before_entering_preparation(self):
        self.g.close()
        root=Path(self.temp.name)
        self.g=FlightGame(output=root/'initial-client',user_settings=root/'initial-preferences.json')
        self.assertTrue(self.g.config.use_station_loadout)
        player=next(e for e in self.g.sim.frame().entities if e.uid=='player')
        self.assertEqual(dict(player.pylons),dict(self.g.config.loadout))
        self.assertIn('MAIN-1',player.pylons);self.assertNotIn('M0',player.pylons)
        self.assertNotIn('Mk-82',player.pylons.values())
    def click(self,id):
        self.f.layout();_,(x,y,w,h),_=next(r for r in self.f.regions if r[0]==id)
        self.event([1],x+w/2,y+h/2)
    def test_station_click_compatibility_mirror_and_cancel_are_drafts(self):
        before=serialize(self.g.sim.frame());config=serialize(self.g.config)
        self.click('battle');self.click('station_1');self.f.layout()
        self.assertNotIn('mount_Mk-82',{r[0] for r in self.f.regions})
        self.click('mount_AIM-9M');self.click('mirror')
        self.assertEqual(self.f.preparation['mounts']['1'],'AIM-9M')
        self.assertEqual(self.f.preparation['mounts']['9'],'AIM-9M')
        self.click('station_3');self.click('mount_Mk-82')
        self.assertEqual(self.f.preparation['mounts']['3'],'Mk-82')
        self.click('back')
        self.assertEqual(serialize(self.g.config),config);self.assertEqual(serialize(self.g.sim.frame()),before)
    def test_launch_commits_mounts_and_v_cycles_actual_remaining_weapon_types(self):
        self.g.config.mission='air';self.g.config.enemy_attacks=False;self.g.config.enemy_range=3500
        self.click('battle');self.click('station_1');self.click('mount_AIM-9M')
        self.click('station_2');self.click('mount_AIM-120C7')
        self.click('launch');self.assertEqual(self.g.mode,'flight')
        self.assertTrue(self.g.config.use_station_loadout)
        player=next(e for e in self.g.sim.frame().entities if e.uid=='player')
        self.assertEqual(player.pylons['1'],'AIM-9M');self.assertEqual(player.pylons['2'],'AIM-120C7')
        self.g.step(10);seen=set()
        for _ in range(4):self.event([86]);seen.add(self.g.weapon)
        self.assertEqual(seen,set(self.g.sim.frame().weapon_counts))
        self.assertIn('AIM-9M',seen);self.assertIn('AIM-120C7',seen)
        for weapon in ['AIM-9M','AIM-120C7']:
            # Each real shot uses the same key path as a user; reset starts a fresh target.
            self.g.start(record=False);self.g.step(10)
            for _ in range(5):
                if self.g.weapon==weapon:break
                self.event([86])
            self.assertEqual(self.g.weapon,weapon)
            self.event([82]);self.g.step();before=self.g.sim.frame().missiles_left
            self.event([32]);self.g.step()
            f=self.g.sim.frame();self.assertEqual(f.missiles_left,before-1)
            self.assertTrue(any(e.kind=='missile_launched' and e.weapon==weapon for e in f.events))

if __name__=='__main__':unittest.main()
