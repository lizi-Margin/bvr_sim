"""Actual core/camera parity between player game and standalone entry."""
import math,os,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from bvr_game.app import FlightGame,native,serialize,ROOT,DEFAULT_VISUAL_PROFILE
from bvr_game.aircraft import aircraft
from bvr_game.aircraft_library import player_test_flight
from bvr_game.ground import apply_config

def event(index):
    held=[83] if 20<=index<40 else [87] if 45<=index<60 else [65] if 65<=index<75 else [87,83] if 76<=index<80 else [2] if 90<=index<100 else [67,83] if 100<=index<115 else []
    pressed={80:[80],81:[117],82:[190],85:[80]}.get(index,[])
    width,height=(1600,900) if 90<=index<125 else (1920,1080)
    return SimpleNamespace(held=held,pressed=pressed,x=width*.65 if 100<=index<125 else width*.5,
        y=height*.3 if 100<=index<125 else height*.5,width=width,height=height,wheel=0,quit=False,active=True)

class StandalonePlayerTests(unittest.TestCase):
    def test_mixed_input_full_core_frames_and_camera_match_main_game(self):
        for model in ['F22','F16','FG-A-10']:
            with self.subTest(model=model),tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'BVR_SORTIE_LOG_ROOT':str(Path(folder)/'sorties')}):
                a=player_test_flight(aircraft(model),Path(folder)/'standalone',render=False,map_path=ROOT/'game/maps/training.json')
                config=serialize(a.config);frames=[];states=[];cameras=[];clock=0.;paused_tick=None
                try:
                    for index in range(220):
                        dt=[.01,.03,.02][index%3];e=event(index)
                        running,clock=a.run_client_frame(e,dt,clock);self.assertTrue(running)
                        frames.append(serialize(a.sim.frame()));states.append(serialize(a.sim.player_flight_state()));cameras.append(serialize(a.camera_params))
                        if index==80:paused_tick=a.sim.frame().tick
                        if index==81:self.assertEqual(a.sim.frame().tick,paused_tick)
                        if index==82:self.assertEqual(a.sim.frame().tick,paused_tick+1)
                    self.assertTrue(a.player().alive)
                    self.assertEqual(a.config.missiles+a.config.bombs,0)
                finally:a.close()
                # Native ownership permits one live session per process.
                # Compare sequential fresh sessions with every stored sample.
                b=FlightGame(output=Path(folder)/'main',map_path=ROOT/'game/maps/training.json')
                try:
                    b.select_aircraft(model);apply_config(native,b.config,config)
                    b.start(start_position=[config['player_north'],config['player_west'],config['altitude']],initial_speed=config['speed'])
                    clock=0.
                    for index in range(220):
                        running,clock=b.run_client_frame(event(index),[.01,.03,.02][index%3],clock);self.assertTrue(running)
                        self.assertEqual(frames[index],serialize(b.sim.frame()))
                        self.assertEqual(states[index],serialize(b.sim.player_flight_state()))
                        self.assertEqual(cameras[index],b.camera_params)
                finally:b.close()

    def test_f9_routes_to_current_standard_sortie_and_pause_reload_is_shared(self):
        with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'BVR_SORTIE_LOG_ROOT':str(Path(folder)/'sorties')}):
            game=player_test_flight(aircraft('FG-A-10'),Path(folder)/'client',render=False,map_path=ROOT/'game/maps/training.json')
            try:
                directory=game.log_paths()['current'];self.assertTrue(Path(directory).is_dir())
                e=SimpleNamespace(held=[],pressed=[120],x=960,y=540,wheel=0,quit=False)
                with patch('bvr_game.app.open_logs_directory',return_value=directory) as opener:
                    game.run_client_frame(e,.02);opener.assert_called_once()
                self.assertEqual(game.last_log_opened,directory)
                self.assertEqual(DEFAULT_VISUAL_PROFILE,ROOT/'game/recipes/player_daylight.json')
            finally:game.close()

if __name__=='__main__':unittest.main()
