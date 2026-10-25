"""Independent placement retains content and clearance while sharing source meshes."""
import random,unittest
from types import SimpleNamespace
import numpy as np
from shapely.geometry import box,GeometryCollection
from bvr_game.source_tree_layout import spatial_batches,build_rule,flush_occupancy,forbidden_geometry,edge_density_probability
from bvr_game.grove_grounding import stem_spacing_report


class SourceTreeLayoutTests(unittest.TestCase):
    def test_accelerated_edge_density_matches_exact_boundary_distances(self):
        from shapely import distance,points
        from shapely.geometry import Point
        from bvr_game.regional_cover import smooth_noise
        forest=box(-2000,-2000,2000,2000).difference(Point(150,100).buffer(250)).difference(box(-1700,-80,-1200,70))
        locations=np.random.default_rng(901).uniform(-2200,2200,(20000,2))
        for width,variation in [(30.,12.),(160.,72.)]:
            cfg={'width_m':width,'variation_m':variation,'patch_scale_m':90.}
            n,w=locations.T
            exact_depth=distance(forest.boundary,points(locations))
            local_width=width*(.5+smooth_noise(n,w,90.,3124+191))
            setback=variation*smooth_noise(n,w,90.*.63,3124+197)
            u=np.clip((exact_depth-setback)/local_width,0,1)
            expected=.005+.995*(u*u*(3-2*u))**1.5
            np.testing.assert_array_equal(edge_density_probability(forest,locations,cfg,3124),expected)

    def test_spatial_batches_preserve_every_input_point_and_are_local(self):
        points=np.random.default_rng(5001).uniform(-1000,1000,(4096,2));groups=list(spatial_batches(points,64))
        self.assertEqual(len(groups),64);self.assertTrue(all(len(g)==64 for g in groups))
        self.assertEqual(set(map(tuple,points)),set(map(tuple,np.concatenate(groups))))
        self.assertLess(max(np.ptp(g,axis=0).max() for g in groups),400)
        with self.assertRaises(ValueError):list(spatial_batches(points[:-1],64))
        sparse=np.column_stack([np.r_[np.arange(32),10000+np.arange(32)],np.zeros(64)])
        tails=list(spatial_batches(sparse,64,max_extent_m=250))
        self.assertEqual([len(g) for g in tails],[32,32]);self.assertTrue(all(np.ptp(g,axis=0).max()<=250 for g in tails))
        self.assertEqual(set(map(tuple,sparse)),set(map(tuple,np.concatenate(tails))))

    def baker(self):
        bounds=[{'min':[-1,-1,0],'max':[1,1,4]} for _ in range(4)]
        manifest={'cluster':{'poses_before_recentering':[{'base_anchor':[i*10,0,0]} for i in range(4)],
            'recentering':[0,0,0],'ground_conform':{'anchor_encoding':'source_tree_index_uv1','tree_bounds_relative_blender':bounds}},
            'conversion_recipe':{'policy':{'cluster':{'inter_grove_stem_spacing_m':2.5}}}}
        return SimpleNamespace(r={'asset_roles':{'canopy':['source']},'settlements':[],'chunk_m':1000},rng=random.Random(5001),
            metadata={'source':manifest},forests={'forest':box(-100,-100,100,100)},water=box(-20,-200,20,200),
            road_exclusion=GeometryCollection(),industry=box(2000,2000,2100,2100),exclusions=[],occupied={(1,1):[(50,50,10)]},
            terrain=SimpleNamespace(height=lambda n,w:100+.002*n+.001*w,height_many=lambda n,w:100+.002*n+.001*w),
            instances=[],serial=0,rejections={})

    def test_sampling_is_seeded_complete_and_respects_source_clearance(self):
        rule={'id':'forest','roles':'canopy','zones':['forest'],'count':16,'scale_range':[1,1],'lod_distance_m':900,'cull_distance_m':35000}
        a=self.baker();b=self.baker();build_rule(a,rule);build_rule(b,rule)
        self.assertEqual(a.instances,b.instances);self.assertEqual(len(a.instances),16)
        points=np.concatenate([i['ground_stems'] for i in a.instances]);self.assertEqual(len(points),64)
        self.assertTrue(np.all(abs(points[:,0])>21.4));self.assertTrue(np.all(np.linalg.norm(points-[50,50],axis=1)>11.4))
        self.assertFalse(stem_spacing_report(a.instances,a.metadata)['failures'])
        flush_occupancy(a);self.assertEqual(a.source_tree_index.n,64);self.assertEqual(len(a.source_tree_clearance),64)
        self.assertEqual(sum(len(v) for v in a.occupied.values()),1)

    def test_streamed_tree_spacing_is_checked_inside_the_same_batch(self):
        b=self.baker();item={'id':'batch','model':'source','position':[0,0,100],'ground_stems':[[-40,40],[-39,40],[40,-40],[40,-30]]}
        report=stem_spacing_report([item],b.metadata);self.assertEqual(len(report['failures']),1)
        self.assertEqual(report['failures'][0]['distance_m'],1.)

    def test_settlement_polygon_does_not_cut_inside_analytic_circle(self):
        b=self.baker();b.r['settlements']=[{'center':[0,0],'radius_m':850}];shape=forbidden_geometry(b)
        from shapely import points,distance
        angles=np.linspace(0,2*np.pi,1000,endpoint=False);boundary=points(np.column_stack([850*np.cos(angles),850*np.sin(angles)]))
        self.assertTrue(np.all(distance(shape,boundary)<1e-9))

    def test_edge_density_has_sparse_fringe_and_retains_deep_interior(self):
        forest=box(-1000,-1000,1000,1000);cfg={'width_m':160,'variation_m':72,'patch_scale_m':180}
        west=np.linspace(-500,500,1000)
        samples=[np.column_stack([np.full(1000,-1000+d),west]) for d in [0,20,80,350]]
        values=[edge_density_probability(forest,p,cfg,3124) for p in samples]
        self.assertTrue(np.all(values[0]==.005));self.assertTrue(np.all(values[-1]==1))
        self.assertLess(values[1].mean(),values[2].mean());self.assertLess(values[2].mean(),.5)
        np.testing.assert_array_equal(values[2],edge_density_probability(forest,samples[2],cfg,3124))
        self.assertGreater(np.ptp(values[2]),.05)

    def test_edge_sampling_keeps_full_target_and_clearance(self):
        b=self.baker();b.r['seed']=3124
        rule={'id':'forest','roles':'canopy','zones':['forest'],'count':16,'scale_range':[1,1],'lod_distance_m':900,'cull_distance_m':35000,
            'edge_density':{'width_m':35,'variation_m':15,'patch_scale_m':180}}
        build_rule(b,rule);self.assertEqual(sum(len(i['ground_stems']) for i in b.instances),64)
        self.assertFalse(stem_spacing_report(b.instances,b.metadata)['failures'])


if __name__=='__main__':unittest.main()
