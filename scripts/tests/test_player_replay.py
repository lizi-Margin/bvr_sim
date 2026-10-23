"""Actual client journal replay, profile restoration and safe reload boundaries."""
import copy,json,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from bvr_game.app import FlightGame,serialize,native
from bvr_game.player_profiles import PlayerProfileStore
from bvr_game.playtest import replay

class PlayerReplayTests(unittest.TestCase):
    def test_client_intent_pause_exact_step_and_reload_replay_whole_frame(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'BVR_SORTIE_LOG_ROOT':str(Path(temp)/'sorties')}):
            g=FlightGame(output=Path(temp)/'client')
            try:
                g.config.mission='training';g.start(start_position=[-20000,0,8500],initial_speed=300)
                for j in range(30):
                    g.input(SimpleNamespace(held=[83] if j<10 else [],pressed=[],x=1200,y=480,quit=False),.02);g.step(5)
                g.input(SimpleNamespace(held=[],pressed=[80],x=960,y=540,quit=False),.02)
                tick=g.sim.frame().tick;g.step(10);self.assertEqual(g.sim.frame().tick,tick)
                g.step_exact(3);self.assertEqual(g.sim.frame().tick,tick+3)
                g.reload_player_flight()
                g.input(SimpleNamespace(held=[],pressed=[80],x=960,y=540,quit=False),.02);g.step(20)
                directory=Path(g.log_paths()['current']);g.finish_sortie('test')
            finally:g.close()
            report=replay(directory/'input-tape.json',Path(temp)/'replay')
            self.assertEqual(report['status'],'passed')
            self.assertTrue(report['full_final_frame_equal'])

    def test_invalid_profile_save_is_atomic_and_recorded_profile_hash_checked(self):
        with tempfile.TemporaryDirectory() as temp:
            source=PlayerProfileStore();path=Path(temp)/'profiles.json';path.write_bytes(source.path.read_bytes())
            store=PlayerProfileStore(path);before=path.read_bytes()
            with self.assertRaises(ValueError):store.save_override('F22','control.energy_horizon',-1)
            self.assertEqual(path.read_bytes(),before)
            resolved=store.save_override('F22','input.sensitivity',1.1)
            self.assertEqual(resolved['input']['sensitivity'],1.1)
            self.assertEqual(PlayerProfileStore(path).resolve('F22'),resolved)
            broken=copy.deepcopy(resolved);broken['control']['max_g']=99
            with self.assertRaisesRegex(ValueError,'hash mismatch'):store.native_resolved(native,broken)

    def test_active_reload_rejected_without_advancing_ticks(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'BVR_SORTIE_LOG_ROOT':str(Path(temp)/'sorties')}):
            g=FlightGame(output=Path(temp)/'client')
            try:
                g.config.mission='training';g.start();g.submit_player(direction=[1,0,.01]);g.step(5)
                before=serialize(g.sim.frame())
                with self.assertRaises(ValueError):g.reload_player_flight()
                self.assertEqual(serialize(g.sim.frame()),before)
                g.sim.set_paused(True);tick=g.sim.frame().tick;g.reload_player_flight();self.assertEqual(g.sim.frame().tick,tick)
                g.player_profiles_frozen=True
                with self.assertRaisesRegex(ValueError,'frozen'):g.reload_player_flight()
            finally:g.close()

if __name__=='__main__':unittest.main()
