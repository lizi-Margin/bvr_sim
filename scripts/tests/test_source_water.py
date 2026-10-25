import numpy as np
from shapely import contains_xy,union_all
from shapely.geometry import box
from bvr_game.source_water import wet_footprint,without_holes
from bvr_game.heightfield import sample_grid


def test_water_uses_exact_indexed_triangles_including_saddles():
    h=np.array([[-1,1],[1,-1]],dtype=np.float32)
    m={'rows':2,'columns':2,'spacing':1,'origin_north':0,'origin_west':0}
    water=wet_footprint(h,m)
    assert abs(water.area-.25)<1e-12
    n,w=np.random.default_rng(170).uniform(0,1,(2,10000))
    np.testing.assert_array_equal(contains_xy(water,n,w),sample_grid(h,m,n,w)<0)


def test_core_polygons_preserve_dry_islands_and_refinement_cutout():
    source=box(0,0,10,10).difference(box(3,3,7,7));parts=without_holes(source)
    assert all(not p.interiors for p in parts)
    assert union_all(parts).symmetric_difference(source).area<1e-12
    h=np.full((5,5),-2,dtype=np.float32)
    m={'rows':5,'columns':5,'spacing':1,'origin_north':0,'origin_west':0}
    water=wet_footprint(h,m,cutout=[1,1,3,3])
    assert water.symmetric_difference(box(0,0,4,4).difference(box(1,1,3,3))).area<1e-12
