import numpy as np
from bvr_game.source_macro import weight_coordinates,to_linear,to_srgb,SourceMacro


def test_original_cells_clamp_and_nwu_axes_are_not_interchanged():
    # Adjacent source cells do not share their edge texels. The old regional
    # color bake clamped each source weight image independently.
    w,n=weight_coordinates(np.array([-65536+4096-1,-65536+4096+1]),np.array([-65536+64,-65536+96]))
    np.testing.assert_allclose(n,[127,128])
    np.testing.assert_allclose(w,[1.5,2.5])


def test_sampling_keeps_source_x_minus_w_and_texture_v_minus_n():
    sampler=object.__new__(SourceMacro);sampler.cell_side=128
    sampler.weights=np.ones((2,2,1),dtype=np.float32)
    image=np.arange(4*4*3,dtype=np.float32).reshape(4,4,3)/48
    sampler.definitions=[{'image':image,'size':[4,4],'offset':[0,0]}]
    # Centers of source texture pixels: U=(-W)mod4,V=(-N)mod4.
    color=sampler.sample_linear(np.array([-.5,-2.5]),np.array([-.5,-1.5]))
    np.testing.assert_allclose(color,[image[0,0],image[2,1]],atol=1e-7)
    np.testing.assert_array_equal(to_srgb(to_linear(np.arange(256,dtype=np.uint8))),np.arange(256))
