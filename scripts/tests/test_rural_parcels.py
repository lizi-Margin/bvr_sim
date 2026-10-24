"""Rural topology preserves exclusions and seed; forest samples cover their areas."""
import random,unittest
from types import SimpleNamespace
import numpy as np
from shapely.geometry import Polygon,LineString,Point,box
from shapely.ops import unary_union
from bvr_game.rural_parcels import road_parcels
from bvr_game.worldgen import Baker


class RuralParcelTests(unittest.TestCase):
    def baker(self):
        return SimpleNamespace(r={'seed':3124,'landscape':{'rural_parcels':{
            'area_range_m2':[30000,280000],'palette_linear':[[.9,.9,.9,1],[.85,.9,.8,1]]}}},
            rng=random.Random(99),roads=[({},LineString([[-2200,-100],[2200,300]])),
                ({},LineString([[-100,-2200],[300,2200]]))],terrain=SimpleNamespace(slope=lambda n,w:abs(n)*.00002))

    def test_partition_covers_farm_without_overlaps_or_filling_excluded_holes(self):
        source=box(-2000,-2000,2000,2000).difference(box(-500,-400,600,500)).difference(box(-2200,-40,2200,40))
        result=road_parcels(self.baker(),source);polys=[Polygon(r['polygon'],r['holes']) for r in result];union=unary_union(polys)
        self.assertLess(union.symmetric_difference(source).area,1e-5)
        self.assertLess(abs(sum(p.area for p in polys)-union.area),1e-5)
        self.assertTrue(all(p.is_valid and p.area>0 for p in polys));self.assertGreater(len(polys),50)
        self.assertGreater(np.ptp([r['heading_rad'] for r in result]),1.)
        self.assertGreater(np.ptp([r['area_m2'] for r in result]),100000)

    def test_seed_reproduces_complete_parcels_without_changing_other_generators_rng(self):
        baker=self.baker();state=baker.rng.getstate();farm=box(-1200,-900,1500,1700)
        first=road_parcels(baker,farm);self.assertEqual(state,baker.rng.getstate())
        self.assertEqual(first,road_parcels(self.baker(),farm))
        other=self.baker();other.r['seed']+=1;self.assertNotEqual(first,road_parcels(other,farm))

    def test_uniform_forest_sampler_respects_area_and_covers_whole_polygons(self):
        forest={'large':box(0,0,2000,2000),'small':box(3000,0,4000,1000)};positions=[]
        rule={'id':'woods','roles':'canopy','zones':list(forest),'count':1000,'distribution':'area_uniform',
            'scale_range':[.8,1.2],'min_spacing_m':13,'lod_distance_m':900,'cull_distance_m':35000}
        sampler=SimpleNamespace(r={'asset_roles':{'canopy':['registered-source']},'scatter_rules':[rule]},
            forests=forest,rng=random.Random(3124),terrain=SimpleNamespace(slope=lambda n,w:0))
        def place(model,n,w,**kwargs):positions.append((n,w));return True
        sampler.place=place;Baker.build_scatter(sampler)
        self.assertEqual(len(positions),1000)
        large=sum(forest['large'].contains(Point(n,w)) for n,w in positions)
        self.assertTrue(.75<large/1000<.85)
        self.assertTrue(all(any(p.contains(Point(n,w)) for p in forest.values()) for n,w in positions))
        self.assertGreater(len({(int(n//200),int(w//200)) for n,w in positions}),115)


if __name__=='__main__':unittest.main()
