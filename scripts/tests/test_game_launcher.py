"""Supervisor cancellation must work while its worker cannot process UI/signals."""
import json,subprocess,sys,tempfile,time,unittest
from pathlib import Path
from unittest.mock import patch
from bvr_game.launcher import GameWorker

class LauncherTests(unittest.TestCase):
    def test_all_graphical_batch_entries_share_the_cancellable_loader(self):
        game=Path(__file__).resolve().parents[2]/'game'
        frontend=(game/'Launch-Frontend.cmd').read_text(encoding='utf-8').lower()
        self.assertIn('python -x utf8 -m bvr_game.launcher play --runtime game/runtime-ui.json %*',frontend)
        for name in ('Launch-Game.cmd','Launch-Regional-Horizon.cmd','Launch-Map-Candidate.cmd'):
            with self.subTest(script=name):
                source=(game/name).read_text(encoding='utf-8').lower()
                self.assertIn('call "%~dp0launch-frontend.cmd"',source)
                self.assertNotIn('python -m bvr_game play',source)

    def test_interactive_play_routes_through_loader_but_worker_does_not_recurse(self):
        import bvr_game.__main__ as entry
        with patch.dict('os.environ',{'BVR_GAME_STARTUP_WORKER':'0'}),patch('bvr_game.launcher.main',return_value=7) as loader:
            self.assertEqual(entry.main(['play','--hidden']),7)
            loader.assert_called_once_with(['play','--hidden'])
        with patch.dict('os.environ',{'BVR_GAME_STARTUP_WORKER':'1'}),patch('bvr_game.app.main',return_value=0) as app:
            self.assertEqual(entry.main(['play']),0)
            app.assert_called_once_with()

    def test_owned_child_can_be_cancelled_after_ready_without_cooperation(self):
        real_popen=subprocess.Popen
        code="import time; print('BVR_STARTUP {\"stage\":\"ready\",\"message\":\"ready\"}',flush=True); time.sleep(90)"
        def child(command,**kwargs):return real_popen([sys.executable,'-u','-c',code],**kwargs)
        with tempfile.TemporaryDirectory() as folder,patch('bvr_game.launcher.subprocess.Popen',side_effect=child):
            worker=GameWorker(['play'],Path(folder))
            try:
                deadline=time.monotonic()+5
                while not worker.ready and time.monotonic()<deadline:worker.update();time.sleep(.02)
                self.assertTrue(worker.ready)
                started=time.monotonic();worker.cancel()
                self.assertIsNotNone(worker.process.poll());self.assertLess(time.monotonic()-started,3)
                worker.update();worker.reader.join(2)
                self.assertEqual(json.loads((worker.directory/'status.json').read_text())['status'],'cancelled')
                self.assertIn('BVR_STARTUP',(worker.directory/'worker.log').read_text())
            finally:
                if worker.process.poll() is None:worker.cancel()

    def test_worker_failure_and_traceback_are_retained(self):
        real_popen=subprocess.Popen
        def child(command,**kwargs):return real_popen([sys.executable,'-c',"raise RuntimeError('startup fixture')"],**kwargs)
        with tempfile.TemporaryDirectory() as folder,patch('bvr_game.launcher.subprocess.Popen',side_effect=child):
            worker=GameWorker(['play'],Path(folder))
            worker.process.wait(timeout=5);worker.reader.join(2);code=worker.update()
            self.assertNotEqual(code,0);self.assertEqual(worker.status['status'],'failed')
            self.assertIn('startup fixture',(worker.directory/'worker.log').read_text())

if __name__=='__main__':unittest.main()
