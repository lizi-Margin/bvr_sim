import numpy as np
import pytest
from bvr_game.authored_canopy import woodland_mask

POLICY={'kind':'authored_reference_woodland','seed':189,'clearing_cell_m':700,'clearing_radius_m':[75,145]}


def test_authoring_is_independent_of_raster_chunks_and_has_small_openings():
    rng=np.random.default_rng(189);points=rng.uniform(-40000,40000,(120000,2))
    full=woodland_mask(*points.T,POLICY)
    chunked=np.concatenate([woodland_mask(*p.T,POLICY) for p in np.array_split(points,13)])
    np.testing.assert_array_equal(full,chunked)
    assert .80<full.mean()<.97
    # Scalar editor queries and the bulk bake use precisely the same support.
    for p,expected in zip(points[:50],full[:50]):assert woodland_mask(*p,POLICY)==expected


def test_policy_rejects_unbounded_clearing_size():
    with pytest.raises(ValueError):woodland_mask(0,0,dict(POLICY,clearing_radius_m=[75,500]))

def test_small_irregular_openings_are_chunk_stable_and_probability_preserves_support():
    policy=dict(POLICY,clearing_cell_m=450,clearing_radius_m=[25,75],clearing_probability=.85,
        clearing_shape='world_noise',clearing_edge_scale_m=45,clearing_edge_strength=.28)
    points=np.random.default_rng(278).uniform(-40000,40000,(70000,2))
    full=woodland_mask(*points.T,policy)
    chunks=np.concatenate([woodland_mask(*p.T,policy) for p in np.array_split(points,11)])
    np.testing.assert_array_equal(full,chunks)
    no_small_openings=woodland_mask(*points.T,dict(policy,clearing_probability=0))
    assert np.all(~full|no_small_openings)
    legacy=woodland_mask(*points.T,POLICY)
    assert full.mean()>legacy.mean()+.025 and no_small_openings.mean()>full.mean()+.015
    with pytest.raises(ValueError):woodland_mask(0,0,dict(policy,clearing_probability=1.1))

def test_local_meadow_fragmentation_preserves_existing_trees_and_outer_map():
    policy=dict(POLICY,clearing_cell_m=450,clearing_radius_m=[25,75])
    fragment={'bounds_nw':[13000,31000,19500,39500],'scale_m':600,'threshold':.88,'fade_m':500}
    changed=dict(policy,meadow_fragmentation=fragment)
    points=np.random.default_rng(318).uniform([14000,33000],[18500,38000],(24000,2))
    before=woodland_mask(*points.T,policy);after=woodland_mask(*points.T,changed)
    assert after[before].all() and after.mean()>before.mean()+.10
    np.testing.assert_array_equal(after,np.concatenate([woodland_mask(*part.T,changed) for part in np.array_split(points,7)]))
    outer=np.array([[13000,35000],[19500,35000],[16000,31000],[16000,39500],[10000,35000],[16000,40000]])
    np.testing.assert_array_equal(woodland_mask(*outer.T,changed),woodland_mask(*outer.T,policy))
    for bad in [dict(fragment,bounds_nw=[0,0,0,1]),dict(fragment,threshold=1.1),dict(fragment,scale_m=0)]:
        with pytest.raises(ValueError):woodland_mask(0,0,dict(policy,meadow_fragmentation=bad))
