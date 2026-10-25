"""Airport terrain creases/grass islands and source footprint collision, headless."""
import math,unittest
from types import SimpleNamespace
import numpy as np
from shapely.geometry import box,LineString
from bvr_game.airport_layout import SharedHeightView,polygon_surface
from bvr_game.river_valley import building_foundation
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native


class AirportLayoutTests(unittest.TestCase):
    def test_curved_service_edges_at_world_coordinates_do_not_drop_triangles(self):
        road=LineString([[-2200,-3000],[-2181,-3000],[-2164,-2987]]).buffer(3.5)
        shoulder=road.buffer(1.).difference(road)
        height=SimpleNamespace(height_many=lambda n,w:30.+np.zeros(np.broadcast(n,w).shape))
        for polygon in [road,shoulder]:
            s=polygon_surface('edge',polygon,height,'pavement')
            t=np.asarray(s['vertices'])[np.asarray(s['indices']).reshape(-1,3)]
            a=t[:,1,:2]-t[:,0,:2];b=t[:,2,:2]-t[:,0,:2]
            area=float(np.sum((a[:,0]*b[:,1]-a[:,1]*b[:,0])/2))
            self.assertAlmostEqual(area,polygon.area,places=4)

    def test_clipped_courts_follow_core_creases_and_leave_grass_hole(self):
        meta={'origin_north':-20.,'origin_west':-20.,'spacing':5.,'columns':9,'rows':9}
        n,w=np.meshgrid(np.arange(9)*5-20,np.arange(9)*5-20)
        data=(30+np.sin(n/7)*np.cos(w/9)).astype('float32')
        source=SimpleNamespace(document={'terrain':{'base':meta,'details':[]}},arrays={'base':data})
        polygon=box(-17,-16,16,18).difference(box(-4,-6,7,3))
        surface=polygon_surface('courts',polygon,SharedHeightView(source),'pavement',offset=.06)
        terrain=native.GameTerrain()
        for k,v in meta.items():setattr(terrain,k,v)
        terrain.heights=data.astype(float).ravel().tolist()
        contact=native.ContactSurface()
        for k in ['id','material','vertices','indices','drivable']:setattr(contact,k,surface[k])
        terrain.contact_surfaces=[contact];terrain.prepare_surfaces()
        triangles=np.asarray(surface['vertices'])[np.asarray(surface['indices']).reshape(-1,3)]
        area=0.
        for a,b,c in triangles:
            area+=abs((b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]))/2
            p=(a+2*b+3*c)/6
            self.assertAlmostEqual(p[2],terrain.height(*p[:2])+.06,places=6)
            self.assertAlmostEqual(p[2],terrain.collision_height(*p[:2]),places=6)
        self.assertAlmostEqual(area,polygon.area,places=6)
        self.assertFalse(terrain.contact(0,0).supported)
        self.assertAlmostEqual(terrain.collision_height(0,0),terrain.height(0,0),places=10)

    def test_rotated_asymmetric_source_foundation_matches_core_solid(self):
        item={'id':'hangar','scale':1.15,'yaw':math.pi/2,'position':[100.,200.,0.]}
        manifest={'bounds_blender':{'min':[-20.,-12.,-1.],'max':[30.,18.,10.]}}
        foundation,solid=building_foundation(item,manifest,lambda n,w:30.+.01*n+.02*w)
        self.assertAlmostEqual(solid['center'][0],105.75)
        self.assertAlmostEqual(solid['center'][1],203.45)
        terrain=native.GameTerrain();obstacle=native.CollisionBox()
        for k in ['id','center','half_size','yaw']:setattr(obstacle,k,solid[k])
        terrain.obstacles=[obstacle];terrain.prepare_surfaces()
        n,w,z=solid['center'];self.assertAlmostEqual(terrain.collision_height(n,w),z+solid['half_size'][2])
        outside=n+solid['half_size'][1]+1
        self.assertAlmostEqual(terrain.collision_height(outside,w),terrain.height(outside,w))
        self.assertFalse(terrain.line_of_sight([n-50,w,z],[n+50,w,z]))
        self.assertAlmostEqual(item['position'][2]-1.15,foundation['vertices'][0][2],places=6)


if __name__=='__main__':unittest.main()
