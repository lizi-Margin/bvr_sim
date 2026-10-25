"""Large offline terrain remains typed,immutable and independent of rendering."""
import math,tempfile
from pathlib import Path
import numpy as np
import pytest
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as n


def terrain():
    t=n.GameTerrain();t.origin_north=t.origin_west=-12000;t.spacing=40;t.columns=t.rows=600
    north,west=np.meshgrid(-12000+np.arange(600)*40,-12000+np.arange(600)*40)
    t.heights=(-10+.001*north+.002*west).ravel().tolist();return t


def test_large_session_terrain_preserves_signed_heights_and_reset_contract(tmp_path):
    t=terrain();session=n.GameSession(str(tmp_path/'session.log'))
    try:
        session.set_terrain(t);assert abs(session.terrain().height(0,0)+10)<1e-10
        config=n.GameConfig();config.player_model='F16';config.mission='training';config.enemy_attacks=False
        session.reset(config);session.step(8)
        assert session.frame().tick==8
        with pytest.raises(RuntimeError):session.set_terrain(t)
        session.reset(config);assert session.frame().tick==0
        session.set_terrain(t);assert abs(session.terrain().height(500,-1000)+11.5)<1e-10
        invalid=n.GameTerrain();invalid.columns=4097;invalid.rows=2;invalid.heights=[0.]*(4097*2)
        with pytest.raises(ValueError):session.set_terrain(invalid)
        assert abs(session.terrain().height(0,0)+10)<1e-10
    finally:session.close()


def test_same_large_environment_runs_in_core_without_a_game_session(tmp_path):
    core=n.SimCore(.02,str(tmp_path/'core.log'),'',False)
    results=[]
    try:
        for _ in range(2):
            core.reset_world(173);core.set_environment(terrain())
            spec=n.AircraftSpawnSpec();spec.uid='own';spec.model='F16';spec.team='blue';spec.position=[0,0,2000];spec.velocity=[200,0,0];spec.loadout={}
            core.spawn_aircraft(spec);core.step(20)
            own=next(o for o in core.objects() if o.uid=='own')
            assert own.alive and all(math.isfinite(x) for x in own.position)
            assert math.dist(own.position,[0,0,2000])>10
            results.append((tuple(own.position),tuple(own.velocity)))
        assert results[0]==results[1]
    finally:core.close()
