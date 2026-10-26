"""Menu transactions use real typed core state and shared hit-test geometry."""
import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bvr_game.app import FlightGame,serialize
from bvr_game.client_settings import ClientSettings,DEFAULTS

class FrontendTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.g=FlightGame(output=self.root/'client',user_settings=self.root/'preferences.json');self.f=self.g.frontend
    def tearDown(self):self.g.close();self.temp.cleanup()
    def test_fps_reports_real_slow_frames_before_presentation_dt_is_capped(self):
        event=SimpleNamespace(held=[],pressed=[],x=960,y=540,quit=False)
        before=serialize(self.g.sim.frame())
        self.g.run_client_frame(event,2.)
        self.assertAlmostEqual(self.g.fps,.5)
        self.g.run_client_frame(event,1.)
        self.assertAlmostEqual(self.g.fps,2/3)
        self.assertEqual(serialize(self.g.sim.frame()),before)
    def click(self,id,width=1920,height=1080):
        self.g.width=width;self.g.height=height;self.f.layout()
        _,(x,y,w,h),_=next(r for r in self.f.regions if r[0]==id)
        self.g.run_client_frame(SimpleNamespace(held=[],pressed=[1],x=(x+w/2)*width/1920,y=(y+h/2)*height/1080,quit=False),.1)
    def test_scaled_click_navigation_does_not_advance_or_reset_complete_core_state(self):
        before=serialize(self.g.sim.frame())
        self.click('settings',1280,720);self.assertEqual(self.f.page,'settings')
        self.click('nav_flight',1280,720);self.click('cancel',1280,720)
        self.click('battle',1280,720);self.assertEqual(self.f.page,'prepare');self.click('back',1280,720)
        self.assertEqual(serialize(self.g.sim.frame()),before)
    def test_setting_apply_is_persistent_and_changes_input_without_core_gains(self):
        frame=serialize(self.g.sim.frame());profile=json.loads(json.dumps(self.g.player_profile))
        self.f.open_settings();self.f.draft['mouse_sensitivity']=1.5;self.f.action(('apply',))
        self.assertEqual(ClientSettings(self.root/'preferences.json').values['mouse_sensitivity'],1.5)
        self.assertEqual(self.g.player_input.profile['input']['sensitivity'],1.5*profile['input']['sensitivity'])
        self.assertEqual(self.g.player_profile,profile);self.assertEqual(serialize(self.g.sim.frame()),frame)
        self.g.start();self.assertEqual(self.g.player_input.profile['input']['sensitivity'],1.5*profile['input']['sensitivity'])
    def test_cancel_settings_and_preparation_are_true_drafts(self):
        before=serialize(self.g.config);frame=serialize(self.g.sim.frame())
        self.f.open_settings();self.f.draft['quality']='low';self.f.action(('cancel',))
        self.assertEqual(self.g.quality,'high');self.assertFalse((self.root/'preferences.json').exists())
        self.f.open_preparation();self.f.action(('option','mission','strike'));self.f.action(('cancel',))
        self.assertEqual(serialize(self.g.config),before);self.assertEqual(serialize(self.g.sim.frame()),frame)
    def test_imported_training_cannot_launch_an_unsupported_armed_mission(self):
        self.f.select('FG-A-10');self.f.open_preparation()
        self.assertEqual(self.f.missions(),['training']);self.assertEqual(self.f.preparation['loadout'],'unarmed')
        before=serialize(self.g.sim.frame());self.f.preparation['mission']='air';self.f.launch()
        self.assertEqual(self.g.mode,'hangar');self.assertEqual(serialize(self.g.sim.frame()),before)
    def test_invalid_seed_does_not_partially_commit_mission(self):
        before=serialize(self.g.config);self.f.open_preparation();self.f.preparation['mission']='strike';self.f.preparation['seed']=''
        self.f.launch();self.assertEqual(serialize(self.g.config),before);self.assertEqual(self.g.mode,'hangar')
    def test_dogfight_mission_selects_the_real_ir_loadout_and_starts(self):
        self.f.select('F16');self.f.open_preparation();self.f.action(('option','mission','dogfight_1v1'))
        self.assertEqual(self.f.preparation['loadout'],'dogfight')
        self.assertEqual(self.f.preparation['mounts'],{'1':'AIM-9M','9':'AIM-9M'})
        self.f.launch()
        self.assertEqual(self.g.mode,'flight');self.assertEqual(self.g.sim.frame().mission,'dogfight_1v1')
        self.assertEqual(self.g.weapon,'AIM-9M');self.assertEqual(self.g.sim.frame().missiles_left,2)
    def test_invalid_preferences_never_replace_saved_file(self):
        store=ClientSettings(self.root/'preferences.json');store.save(DEFAULTS);before=store.path.read_bytes()
        invalid={**DEFAULTS,'mouse_sensitivity':99.}
        with self.assertRaises(ValueError):store.save(invalid)
        self.assertEqual(store.path.read_bytes(),before)
    def test_settings_are_bound_to_available_controls_and_carousel_reaches_last_aircraft(self):
        self.f.action(('country','usa'));self.f.action(('scroll',10000))
        self.assertEqual(self.f.rows()[self.f.offset:][-1]['id'],self.f.rows()[-1]['id'])
        self.f.select(self.f.rows()[-1]['id']);self.assertEqual(self.g.current_aircraft()['id'],self.f.rows()[-1]['id'])
        self.f.open_settings();self.f.layout()
        self.assertTrue(all(0<=x<=1920 and 0<=y<=1080 and w>0 and h>0 for _,(x,y,w,h),_ in self.f.regions))
    def test_country_tabs_and_tree_navigation_do_not_mutate_core(self):
        frame=serialize(self.g.sim.frame());config=serialize(self.g.config)
        for country in ['germany','joint','fictional','usa']:
            self.click('country_'+country,1280,720)
            self.assertTrue(self.f.tree_open);self.assertEqual(self.f.country,country)
            self.f.action(('tree_scroll',500));self.f.layout()
            self.assertEqual(serialize(self.g.sim.frame()),frame);self.assertEqual(serialize(self.g.config),config)
        self.assertFalse(any(r[0].startswith('filter_') for r in self.f.regions))
    def test_family_expansion_reveals_both_f22_resources_and_selection_closes_tree(self):
        self.g.aircraft_search='F22';self.f.action(('country','usa'));self.f.layout()
        group=next(r for r in self.f.regions if r[0].startswith('family_'))
        self.f.action(group[2]);self.f.layout()
        ids={r[0] for r in self.f.regions}
        self.assertIn('tree_aircraft_F22',ids);self.assertIn('tree_aircraft_FG-F22',ids)
        self.click('tree_aircraft_F22');self.assertFalse(self.f.tree_open)
        self.assertEqual(self.g.current_aircraft()['id'],'F22')
    def test_every_aircraft_is_reachable_through_clipped_tree_input_regions(self):
        from bvr_game.aircraft_tree import countries,layout
        seen=set();before=serialize(self.g.sim.frame())
        for c in countries(self.g.aircraft_rows):
            self.f.action(('country',c['id']))
            tree=layout(self.f.rows())
            self.f.expanded_families.update(n['group'] for n in tree['nodes'] if n['kind']=='family')
            full=layout(self.f.rows(),self.f.expanded_families)
            for scroll in range(0,int(full['height'])+96,96):
                self.f.tree_scroll=scroll;self.f.layout()
                for id,(x,y,w,h),action in self.f.regions:
                    if id.startswith('tree_aircraft_'):
                        seen.add(action[1]);self.assertGreaterEqual(y,204);self.assertLessEqual(y+h,764)
                        self.assertGreaterEqual(x,145);self.assertLessEqual(x+w,1822)
        self.assertEqual(seen,{r['id'] for r in self.g.aircraft_rows})
        self.assertEqual(serialize(self.g.sim.frame()),before)

if __name__=='__main__':unittest.main()
