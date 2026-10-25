import numpy as np
from bvr_game.ground_color_mix import linear_ground_mix


def test_albedo_mixture_uses_linear_light_and_preserves_endpoints():
    dark=np.zeros((1,1,3),dtype=np.uint8);bright=np.full_like(dark,255)
    np.testing.assert_array_equal(linear_ground_mix(dark,bright,np.zeros((1,1))),dark)
    np.testing.assert_array_equal(linear_ground_mix(dark,bright,np.ones((1,1))),bright)
    assert np.all(linear_ground_mix(dark,bright,np.full((1,1),.5))==188)
def test_prefiltered_color_coverage_does_not_change_planting_mask():
    import numpy as np
    from bvr_game.ground_color_mix import filtered_landcover
    mask=np.zeros((80,80),dtype=np.uint8);mask[:,:40]=1;before=mask.copy()
    filtered=filtered_landcover(mask,2,12)
    np.testing.assert_array_equal(mask,before)
    assert 0<filtered[40,40]<.5<filtered[40,39]<1
    assert filtered[40,0]>.99 and filtered[40,-1]<.01
    np.testing.assert_allclose(filtered.sum(),mask.sum(),atol=.01)
