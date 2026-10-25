"""Typed weapons acceptance, including a world with no GameSession or renderer."""
import tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as n

class CoreWeaponsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.core=n.SimCore(.02,str(Path(self.temp.name)/'core.log'),'',False)
        self.core.reset_world(123)
    def tearDown(self):
        self.core.close();self.core=None;self.temp.cleanup()
    def spawn(self,uid='own',model='F16',team='blue',position=(0,0,3000),velocity=(250,0,0),mounts=None,radar=True):
        s=n.AircraftSpawnSpec();s.uid=uid;s.model=model;s.team=team;s.position=position;s.velocity=velocity
        s.loadout={'1':'AIM-9M','2':'AIM-120C7'} if mounts is None else mounts
        s.radar=radar
        self.core.spawn_aircraft(s)
    def state(self,uid):return next(o for o in self.core.objects() if o.uid==uid)
    def pair(self):
        self.spawn();self.spawn('target',team='red',position=(3500,0,3000),velocity=(-250,0,0),mounts={})
        self.core.step(10)
    def test_catalog_and_developer_presets_validate(self):
        ids={w.id for w in n.weapon_catalog()}
        self.assertIn('AIM-9M',ids);self.assertIn('AIM-120C7',ids)
        for model in ['F22','F16','F15','F18','F4N']:
            self.assertEqual(dict(n.loadout_preset(model,'clean')),{})
            self.assertEqual(dict(n.loadout_preset(model,'unarmed')),{})
            for id,mounts in n.aircraft_stations(model).presets.items():
                self.assertEqual(n.validate_loadout(model,mounts),[],(model,id))
        f22=n.loadout_preset('F22','intercept')
        self.assertEqual(list(f22.values()).count('AIM-120C7'),6)
        self.assertEqual(list(f22.values()).count('AIM-9M'),2)
        self.assertTrue(n.validate_loadout('F22',{'SIDE-L':'AIM-120C7'}))
        self.assertTrue(n.validate_loadout('FG-F22',{'SIDE-L':'AIM-9M'}))
    def test_invalid_spawn_is_atomic(self):
        self.spawn();before=[(o.uid,o.position,o.pylons) for o in self.core.objects()]
        for mounts in [{'UNKNOWN':'AIM-9M'},{'1':'Mk-82'},{'1':'MissingWeapon'}]:
            with self.assertRaises(ValueError):self.spawn('invalid',mounts=mounts)
            self.assertEqual([(o.uid,o.position,o.pylons) for o in self.core.objects()],before)
        invalid=n.AircraftSpawnSpec();invalid.uid='bad-backend';invalid.fdm='yasim'
        with self.assertRaises(ValueError):self.core.spawn_aircraft(invalid)
    def test_rejected_launch_preserves_both_stores_and_world(self):
        self.pair();before=dict(self.state('own').pylons);size=len(self.core.objects())
        for weapon,target,station in [('Unknown','target','1'),('AIM-120C7','target','1'),('AIM-9M','missing','1'),('AIM-9M','own','1')]:
            self.assertFalse(self.core.launch_weapon('own',weapon,target,station))
            self.assertEqual(dict(self.state('own').pylons),before);self.assertEqual(len(self.core.objects()),size)
    def test_each_weapon_flies_hits_once_and_reset_is_reproducible(self):
        for weapon,station in [('AIM-9M','1'),('AIM-120C7','2'),('AIM-120C5','2')]:
            results=[]
            for repeat in range(2):
                self.core.reset_world(123)
                self.spawn(mounts={'1':'AIM-9M','2':weapon if station=='2' else 'AIM-120C7'})
                self.spawn('target',team='red',position=(3500,0,3000),velocity=(-250,0,0),mounts={});self.core.step(10)
                self.assertTrue(self.core.check_launch('own',weapon,'target',station).allowed)
                self.assertTrue(self.core.launch_weapon('own',weapon,'target',station))
                self.assertEqual(self.state('own').pylons[station],'')
                self.assertFalse(self.core.launch_weapon('own',weapon,'target',station))
                missile=next(o for o in self.core.objects() if o.kind=='missile')
                initial=tuple(missile.position)
                trace=[]
                for tick in range(1500):
                    self.core.step()
                    m=self.state(missile.uid)
                    if tick%25==0:trace.append((tuple(m.position),tuple(m.velocity),m.alive,m.done,m.success))
                    if m.done:break
                self.assertNotEqual(tuple(m.position),initial)
                self.assertTrue(m.success,(weapon,tick,tuple(m.position)))
                self.assertFalse(self.state('target').alive)
                health=self.state('target').health;self.core.step(50)
                self.assertEqual(self.state('target').health,health)
                results.append(trace)
            self.assertEqual(results[0],results[1],weapon)
    def test_ir_off_axis_and_out_of_range_reject_without_radar(self):
        self.spawn(radar=False);self.spawn('offaxis',team='red',position=(2500,2000,3000),mounts={})
        self.spawn('far',team='red',position=(20000,0,3000),mounts={})
        self.assertFalse(self.core.check_launch('own','AIM-9M','offaxis').allowed)
        self.assertFalse(self.core.check_launch('own','AIM-9M','far').allowed)
        self.assertEqual(self.state('own').pylons['1'],'AIM-9M')
    def test_one_mixed_sortie_fires_both_types_after_cooldown_without_reset(self):
        self.spawn(mounts={'1':'AIM-9M','2':'AIM-120C7','3':'Mk-82'})
        for uid,north in [('near',3500),('far',7000)]:
            self.spawn(uid,team='red',position=(north,0,3000),velocity=(-250,0,0),mounts={})
        self.core.step(10)
        self.assertTrue(self.core.launch_weapon('own','AIM-9M','near','1'))
        self.assertFalse(self.core.launch_weapon('own','AIM-120C7','far','2'))
        self.assertEqual(self.state('own').pylons['2'],'AIM-120C7')
        self.core.step(260)
        self.assertTrue(self.core.launch_weapon('own','AIM-120C7','far','2'))
        self.core.step(1500)
        missiles=[o for o in self.core.objects() if o.kind=='missile']
        self.assertEqual({o.model for o in missiles},{'AIM-9M','AIM-120C7'})
        self.assertTrue(all(o.done and o.success for o in missiles))
        self.assertFalse(self.state('near').alive);self.assertFalse(self.state('far').alive)
        self.assertEqual(self.state('own').pylons,{'1':'','2':'','3':'Mk-82'})
    def test_ir_launches_with_no_aircraft_radar_and_radar_weapon_does_not(self):
        self.spawn(radar=False);self.spawn('target',team='red',position=(3500,0,3000),velocity=(-250,0,0),mounts={})
        self.core.step(10)
        self.assertFalse(self.core.check_launch('own','AIM-120C7','target').allowed)
        self.assertTrue(self.core.check_launch('own','AIM-9M','target').allowed)
        self.assertTrue(self.core.launch_weapon('own','AIM-9M','target'))
        self.assertFalse(self.core.launch_weapon('own','AIM-120C7','target'))
        self.assertEqual(self.state('own').pylons['2'],'AIM-120C7')
    def test_bomb_factory_release_prediction_collision_damage_and_reset(self):
        traces=[]
        for repeat in range(2):
            self.core.reset_world(123)
            terrain=n.GameTerrain();terrain.origin_north=-1000;terrain.origin_west=-1000
            terrain.spacing=10000;terrain.heights=[0,0,0,120]
            self.core.set_environment(terrain)
            self.spawn(position=(0,0,1000),mounts={'1':'AIM-9M','3':'Mk-82'})
            prediction=self.core.predict_bomb_impact('own');self.assertIsNotNone(prediction)
            for uid,team,offset in [('depot','red',0),('friendly','blue',0),('distant','red',150)]:
                target=n.GroundUnitSpec();target.uid=uid;target.kind='static';target.team=team
                target.position=[prediction[0]+offset,prediction[1],prediction[2]];self.core.spawn_ground(target)
            before=dict(self.state('own').pylons)
            self.assertFalse(self.core.release_weapon('own','Mk-82','1'))
            self.assertFalse(self.core.release_weapon('own','Unknown','3'))
            self.assertEqual(dict(self.state('own').pylons),before)
            self.assertTrue(self.core.release_weapon('own','Mk-82','3'))
            self.assertFalse(self.core.release_weapon('own','Mk-82','3'))
            bomb=next(o for o in self.core.objects() if o.kind=='bomb');trace=[]
            for tick in range(6000):
                self.core.step();state=self.state(bomb.uid)
                if tick%50==0:trace.append((tuple(state.position),tuple(state.velocity)))
                if state.done:break
            self.assertTrue(state.done);self.assertFalse(state.alive)
            self.assertLess(sum((a-b)**2 for a,b in zip(state.position,prediction))**.5,1e-5)
            self.assertFalse(self.state('depot').alive)
            self.assertTrue(self.state('friendly').alive);self.assertTrue(self.state('distant').alive)
            health=self.state('depot').health;impact=tuple(state.position);self.core.step(50)
            self.assertEqual(self.state('depot').health,health);self.assertEqual(tuple(self.state(bomb.uid).position),impact)
            self.assertEqual(self.state('own').pylons['1'],'AIM-9M');traces.append(trace)
        self.assertEqual(traces[0],traces[1])

class SessionWeaponsTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.sim=n.GameSession(str(Path(self.temp.name)/'session.log'))
    def tearDown(self):self.sim.close();self.temp.cleanup()
    def config(self):
        c=n.GameConfig();c.player_model='F16';c.fdm='simple';c.enemy_attacks=False;c.enemy_range=3500
        c.use_station_loadout=True;c.loadout={'1':'AIM-9M','2':'AIM-120C7','3':'Mk-82'};return c
    def test_mixed_loadout_selection_real_firing_and_snapshot_counts(self):
        c=self.config()
        for weapon,station in [('AIM-9M','1'),('AIM-120C7','2'),('AIM-120C5','2')]:
            c.loadout={'1':'AIM-9M','2':weapon if station=='2' else 'AIM-120C7','3':'Mk-82'}
            self.sim.reset(c);self.sim.step(10)
            cmd=n.PilotCommand();cmd.weapon=weapon;cmd.station=station;cmd.target_uid='bandit';cmd.lock=True
            self.sim.submit(cmd);self.sim.step()
            f=self.sim.frame();self.assertEqual(f.selected_weapon,weapon);self.assertTrue(f.launch_ready,f.launch_reason)
            cmd.fire=True;self.sim.submit(cmd);self.sim.step()
            f=self.sim.frame();self.assertEqual(f.missiles_left,1);self.assertEqual(f.bombs_left,1)
            self.assertIn(weapon,[e.model for e in f.entities if e.kind=='missile'])
            self.assertTrue(any(e.kind=='missile_launched' and e.weapon==weapon for e in f.events))
            self.sim.step(1500);self.assertEqual(self.sim.frame().air_kills,1)
    def test_invalid_loadout_reset_preserves_live_world(self):
        c=self.config();self.sim.reset(c);self.sim.step(5);before=self.sim.frame()
        c.loadout={'1':'Mk-82'}
        with self.assertRaises(ValueError):self.sim.reset(c)
        after=self.sim.frame();self.assertEqual(after.tick,before.tick)
        self.assertEqual([(o.uid,o.position,o.pylons) for o in before.entities],[(o.uid,o.position,o.pylons) for o in after.entities])
    def test_exact_bomb_station_release_uses_core_factory(self):
        c=self.config();c.loadout={'1':'AIM-9M','3':'Mk-82','7':'Mk-82'};self.sim.reset(c)
        cmd=n.PilotCommand();cmd.drop_bomb=True;cmd.station='1';self.sim.submit(cmd);self.sim.step()
        self.assertEqual(self.sim.frame().bombs_left,2)
        cmd.station='7';self.sim.submit(cmd);self.sim.step();f=self.sim.frame()
        p=next(e for e in f.entities if e.uid=='player')
        self.assertEqual(p.pylons['3'],'Mk-82');self.assertEqual(p.pylons['7'],'')
        self.assertEqual(f.bombs_left,1);self.assertTrue(any(e.kind=='bomb' for e in f.entities))

if __name__=='__main__':unittest.main()
