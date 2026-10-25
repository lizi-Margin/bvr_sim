"""Offline extension places actual tree points outside the preserved scene."""
import numpy as np
from shapely.geometry import box
from scipy.spatial import cKDTree
from bvr_game.woodland_extension import extension_points


def test_fixed_extension_is_seeded_spaced_and_keeps_blocked_areas_open():
    blocked=box(-2000,-60,2000,60)
    kwargs=dict(inner_half_m=500.,outer_half_m=2000.,spacing_m=24.,jitter_m=4.,seed=155)
    a=extension_points(blocked,**kwargs);b=extension_points(blocked,**kwargs)
    assert len(a)>1000
    np.testing.assert_array_equal(a,b)
    assert np.all(np.max(abs(a),axis=1)>524)
    assert np.all(np.max(abs(a),axis=1)<1976)
    assert np.all(abs(a[:,1])>=60)
    assert cKDTree(a).query(a,k=2)[0][:,1].min()>=16-1e-9
