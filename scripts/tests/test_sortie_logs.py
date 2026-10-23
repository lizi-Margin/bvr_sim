"""Core ACMI contents, deterministic logging, lifecycle, journals and F9 adapter."""
import json,math,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from bvr_game.app import FlightGame,serialize
from bvr_game.ground import apply_config

def acmi(path):
    time=0.;rows=[];removed=[];headers=[]
    for line in Path(path).read_text(encoding='utf8').splitlines():
        if line.startswith('#'):time=float(line[1:]);continue
        if line.startswith('-'):removed.append((time,line[1:]));continue
        if not line or line.startswith(('File','0,')):headers.append(line);continue
        id,*props=line.split(',');int(id,16)
        values=dict(p.split('=',1) for p in props if '=' in p)
        rows.append((time,id,values))
    return rows,removed,headers

def to_nwu(lon,lat,alt):
    a=6378137.;e2=6.6943799901413165e-3
    def ecef(lon,lat,h):
        lon,lat=math.radians(lon),math.radians(lat);r=a/math.sqrt(1-e2*math.sin(lat)**2)
        return [(r+h)*math.cos(lat)*math.cos(lon),(r+h)*math.cos(lat)*math.sin(lon),(r*(1-e2)+h)*math.sin(lat)]
    lo,la=math.radians(41.64821),math.radians(42.23831)
    x,y,z=[u-v for u,v in zip(ecef(lon,lat,alt),ecef(41.64821,42.23831,0))]
    return [-math.sin(la)*math.cos(lo)*x-math.sin(la)*math.sin(lo)*y+math.cos(la)*z,
            math.sin(lo)*x-math.cos(lo)*y,math.cos(la)*math.cos(lo)*x+math.cos(la)*math.sin(lo)*y+math.sin(la)*z]

class SortieLogs(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'空格 sortie logs'
        self.env=patch.dict(os.environ,{'BVR_SORTIE_LOG_ROOT':str(self.root)});self.env.start()
        self.game=FlightGame(output=Path(self.temp.name)/'client')
    def tearDown(self):
        self.game.close();self.env.stop();self.temp.cleanup()
    def test_preview_does_not_log_and_successive_sorties_do_not_overwrite(self):
        for id in ['F16','F22','FG-A-10','F22']:self.game.select_aircraft(id)
        self.assertFalse(self.root.exists())
        self.game.start();self.game.step(60);first=Path(self.game.log_paths()['current'])
        self.game.input(SimpleNamespace(held=[],pressed=[27],quit=False,x=960,y=540),.02)
        before={p.name:p.read_bytes() for p in first.iterdir()}
        self.game.start();self.game.step(20);second=Path(self.game.log_paths()['current']);self.game.close()
        self.assertNotEqual(first,second)
        self.assertEqual(before,{p.name:p.read_bytes() for p in first.iterdir()})
        self.assertEqual(json.loads((first/'sortie.json').read_text())['status'],'returned_to_hangar')
        rows,_,_=acmi(second/'battle.acmi');self.assertEqual(rows[0][0],0.)
        self.assertAlmostEqual(max(r[0] for r in rows),.4)
    def test_recording_does_not_change_full_frames_and_tape_replays(self):
        results=[];tape=None
        for enabled in [True,False]:
            self.game.logs_enabled=enabled;self.game.start();samples=[]
            for i in range(50):
                self.game.command(pitch=.1 if i<20 else -.05,heading=.1,throttle=.85)
                samples.append(serialize(self.game.step(5)))
            if enabled:
                directory=Path(self.game.log_paths()['current']);self.game.finish_sortie('test')
                tape=json.loads((directory/'input-tape.json').read_text())
            results.append(samples)
        self.assertEqual(*results)
        apply_config(__import__('bvr_game.app',fromlist=['native']).native,self.game.config,tape['config'])
        self.game.sim.reset(self.game.config)
        for row in tape['actions']:
            if row['kind']=='command':self.game.command(**row['value'])
            elif row['kind']=='step':self.game.sim.step(row['value']['ticks'])
        self.assertEqual(serialize(self.game.sim.frame()),tape['final_frame'])
    def test_real_missile_acmi_matches_core_samples_and_lifecycle(self):
        self.game.config.enemy_range=9000;self.game.config.enemy_attacks=True;self.game.start()
        directory=Path(self.game.log_paths()['current']);samples={}
        for _ in range(10):f=self.game.step();samples[round(f.sim_time,6)]=serialize(f)
        self.game.command(lock=True,fire=True,target_uid='bandit')
        for _ in range(1800):
            f=self.game.step();samples[round(f.sim_time,6)]=serialize(f)
            if f.result!='running':break
        self.game.finish_sortie('test')
        rows,removed,headers=acmi(directory/'battle.acmi');self.assertTrue(removed)
        self.assertTrue(any('ReferenceTime=2026' in r for r in headers))
        types={r[2]['Type'] for r in rows};self.assertIn('Air+FixedWing',types);self.assertIn('Weapon+Missile',types)
        checked=0
        for t,id,data in rows:
            if t not in samples or 'T' not in data:continue
            entity=next((e for e in samples[t]['entities'] if e['uid']==data['Pilot']),None)
            if not entity:continue
            lla=list(map(float,data['T'].split('|')[:3]))
            self.assertLess(math.dist(to_nwu(*lla),entity['position']),.13);checked+=1
        self.assertGreater(checked,100)
        self.assertAlmostEqual(max(t for t,_,_ in rows),max(samples),places=5)
        self.assertIn('SimCore::update_physics',(directory/'core.log').read_text(encoding='utf8'))
    def test_f9_calls_directory_api_without_advancing_or_pausing(self):
        event=SimpleNamespace(held=[],pressed=[120],quit=False,x=960,y=540)
        original=serialize(self.game.sim.frame())
        with patch('os.startfile',create=True) as opened:
            self.game.input(event,.02);opened.assert_called_once_with(str(self.root),'explore')
        self.assertEqual(original,serialize(self.game.sim.frame()))
    def test_bad_recording_path_is_explicit_and_session_recovers(self):
        target=Path(self.temp.name)/'not-a-directory';target.write_text('file')
        self.game.journal.root=target
        with self.assertRaisesRegex(RuntimeError,'not-a-directory'):self.game.start()
        self.game.journal.root=self.root;self.game.start();self.game.step(5)

if __name__=='__main__':unittest.main()
