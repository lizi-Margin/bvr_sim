import unittest
from types import SimpleNamespace
from shapely.geometry import LineString,box,Polygon
from shapely.ops import unary_union
from bvr_game.water_surface import build_water_surfaces,conform_outer_water

class WaterSurfaceTests(unittest.TestCase):
    def test_outer_water_saddle_interior_stays_above_the_actual_triangle_planes(self):
        import numpy as np
        from bvr_game.heightfield import sample_grid
        base={'origin_north':0,'origin_west':0,'spacing':2000,'columns':2,'rows':2}
        heights=np.array([[0.,120.],[120.,0.]])
        height=lambda n,w:float(sample_grid(heights,base,n,w))
        xy=[(500,100),(1500,100),(1500,1900),(500,1900)]
        source={'id':'outer','material':'water','vertices':[[n,w,height(n,w)+.025] for n,w in xy],
            'indices':[0,1,2,0,2,3],'drivable':False}
        original=np.asarray(source['vertices'])[source['indices'][:3]].mean(axis=0)
        self.assertLess(original[2]-height(*original[:2]),-10)
        fixed=conform_outer_water(source,base,height,(-10000,-10000,-1000,-1000))
        self.assertTrue(fixed['outer_core_plane_conform'])
        for j in range(0,len(fixed['indices']),3):
            triangle=np.asarray([fixed['vertices'][i] for i in fixed['indices'][j:j+3]])
            for weights in ([1/3]*3,[.1,.2,.7],[.2,.7,.1]):
                p=np.asarray(weights)@triangle
                self.assertAlmostEqual(p[2]-height(*p[:2]),.25,places=7)
        self.assertFalse(source.get('outer_core_plane_conform',False))

    def test_confluence_and_island_have_no_overlapping_or_missing_water(self):
        water=unary_union([LineString([[-1500,0],[1500,0]]).buffer(130,cap_style=2),
                           LineString([[0,0],[0,1500]]).buffer(130,cap_style=2)]).difference(box(450,-30,500,30))
        baker=SimpleNamespace(water=water,terrain=SimpleNamespace(height=lambda n,w:116),
            r={'focus_area_km':[20,20],'terrain':{'river_level_m':120},'landscape':{'water_render_chunk_m':500,'regional_transition_m':1200}})
        surfaces=build_water_surfaces(baker);triangles=[];area=0
        for surface in surfaces:
            self.assertFalse(surface['drivable']);vertices=surface['vertices']
            self.assertTrue(all(abs(p[2]-120)<1e-6 for p in vertices))
            self.assertLessEqual(max(p[0] for p in vertices)-min(p[0] for p in vertices),500.00001)
            self.assertLessEqual(max(p[1] for p in vertices)-min(p[1] for p in vertices),500.00001)
            for i in range(0,len(surface['indices']),3):
                p=[vertices[k] for k in surface['indices'][i:i+3]]
                signed=((p[1][0]-p[0][0])*(p[2][1]-p[0][1])-(p[1][1]-p[0][1])*(p[2][0]-p[0][0]))/2
                self.assertGreater(signed,0);area+=signed;triangles.append(Polygon([v[:2] for v in p]))
        result=unary_union(triangles)
        self.assertLess(result.symmetric_difference(water).area,1e-6)
        self.assertAlmostEqual(area,result.area,places=6)

if __name__=='__main__':unittest.main()
