import numpy as np
import pytest
from shapely.geometry import Polygon,Point
from bvr_game.source_woodland import planting_density,protected_footprints


def test_source_masks_use_original_xz_to_project_nwu_axes():
    c=np.zeros((4,4),dtype=bool);c[1,2]=True
    layer={'coverage':c,'density':c,'tile_m':[128,128],'density_per_100m2':.5}
    result=planting_density([layer],np.array([-65536+40,-65536+72]),np.array([65536-72,65536-40]))
    np.testing.assert_array_equal(result,[.5,0])


def test_airport_clearance_covers_the_whole_ribbon_not_first_quad():
    vertices=[[x,y,0] for x in [0,10,20,30,100] for y in [-5,5]]
    doc={'environment':{'contact_surfaces':[{'vertices':vertices}]},'instances':[],
         'roads':[{'points':[[0,0],[100,0]]}]}
    blocked=protected_footprints(doc,Polygon(),3)
    assert blocked.contains(Point(95,0))
    assert blocked.contains(Point(50,9))
    assert not blocked.contains(Point(50,20))

def test_narrow_road_root_clearance_keeps_full_airport_clearance():
    road={'id':'road_surface','vertices':[[0,-5,0],[100,-5,0],[100,5,0],[0,5,0]]}
    airport={'id':'runway','vertices':[[0,95,0],[100,95,0],[100,105,0],[0,105,0]]}
    doc={'roads':[{'id':'road'}],'environment':{'contact_surfaces':[road,airport]},'instances':[]}
    legacy=protected_footprints(doc,Polygon(),10)
    narrow=protected_footprints(doc,Polygon(),10,road_root_clearance_m=2)
    assert legacy.contains(Point(50,8)) and not narrow.contains(Point(50,8))
    assert narrow.contains(Point(50,6))
    assert narrow.contains(Point(50,114)) and legacy.contains(Point(50,114))
    with pytest.raises(ValueError):protected_footprints(doc,Polygon(),10,road_root_clearance_m=-1)
