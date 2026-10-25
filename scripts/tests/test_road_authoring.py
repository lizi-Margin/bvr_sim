from types import SimpleNamespace
import numpy as np
from shapely.geometry import box,LineString,Polygon,Point
from bvr_game.road_authoring import drape_polygon,scene_heights,placed_blender_points,DryRoadPlanner
from bvr_game.source_woodland import protected_footprints
from bvr_game.authored_canopy import woodland_mask


def test_drape_shares_actual_indexed_planes_including_saddle_diagonal():
    meta={'rows':2,'columns':2,'spacing':10,'origin_north':0,'origin_west':0}
    scene=SimpleNamespace(document={'terrain':{'base':meta,'details':[]}},arrays={'base':np.array([[0,10],[10,0]],dtype=float)})
    footprint=LineString([[0,2],[10,8]]).buffer(1)
    vertices,indices=drape_polygon(scene,footprint,.03);v=np.array(vertices);i=np.array(indices).reshape(-1,3)
    rng=np.random.default_rng(218);weights=rng.random((len(i),3));weights/=weights.sum(axis=1,keepdims=True)
    points=(v[i]*weights[...,None]).sum(axis=1)
    np.testing.assert_allclose(points[:,2],scene_heights(scene,*points[:,:2].T)+.03,atol=1e-10)
    assert sum(Polygon(t[:,:2]).area for t in v[i])>10


def test_winding_roads_keep_their_actual_footprint_and_optional_shore_roots():
    # Two narrow rectangles form an L. Its empty inside corner is not road.
    vertices=[[0,0,0],[100,0,0],[100,5,0],[0,5,0],[95,5,0],[100,5,0],[100,100,0],[95,100,0]]
    doc={'environment':{'contact_surfaces':[{'vertices':vertices,'indices':[0,1,2,0,2,3,4,5,6,4,6,7]}]},'instances':[]}
    blocked=protected_footprints(doc,box(-20,-20,-10,-10),3,shore_root_clearance_m=1)
    assert blocked.contains(Point(50,1)) and not blocked.contains(Point(50,40))
    assert not blocked.contains(Point(-15,-7))
    policy={'kind':'authored_reference_woodland','seed':189,'clearing_cell_m':700,'clearing_radius_m':[75,145],
        'roads':[{'points':[[0,-1000],[0,1000]],'forest_clearance_m':40}]}
    assert not woodland_mask(0,0,policy)


def test_static_source_bridge_pose_matches_nwu_scale_and_yaw():
    item={'scale':2,'yaw':np.pi/2,'position':[100,200,10],'up_normal':[0,1,0]}
    points=placed_blender_points([[0,1,0],[1,0,0],[0,0,1]],item)
    np.testing.assert_allclose(points,[[100,202,10],[102,200,10],[100,200,12]],atol=1e-12)
