import tempfile,unittest
from pathlib import Path
from PIL import Image
import numpy as np
from game.tools.extend_source_region import region,reflect,macro
from bvr_game.heightfield import sample_grid
from bvr_game.scene_runtime import BakedScene

class RegionalTerrainTests(unittest.TestCase):
    def setUp(self):
        self.meta={'origin_north':-8,'origin_west':-8,'spacing':1,'columns':17,'rows':17,'material':'source_macro'}
        n,w=np.meshgrid(np.arange(-8,9),np.arange(-8,9));self.source=(n*n*.3+np.sin(w)*2+n*w*.1).astype(np.float32)
        self.base,self.outer,self.tile,self.detail=region(self.source,self.meta,half=32,spacing=4,band=4)
    def test_original_nodes_and_triangle_planes_unchanged(self):
        np.testing.assert_array_equal(self.tile[4:21,4:21],self.source)
        points=np.random.default_rng(12).uniform(-8,8,(1000,2))
        np.testing.assert_allclose(sample_grid(self.source,self.meta,*points.T),sample_grid(self.tile,self.detail,*points.T),atol=2e-12,rtol=0)
    def test_outer_seam_matches_regional_triangle_edges(self):
        p=np.linspace(-12,12,2401)
        for n,w in [(p,np.full_like(p,12)),(p,np.full_like(p,-12)),(np.full_like(p,12),p),(np.full_like(p,-12),p)]:
            np.testing.assert_allclose(sample_grid(self.tile,self.detail,n,w),sample_grid(self.base,self.outer,n,w),atol=3e-6,rtol=0)
    def test_mirror_uses_source_coordinates_and_is_continuous(self):
        np.testing.assert_array_equal(reflect(np.array([-24,-16,-8,0,8,16,24]),-8,16),[8,0,-8,0,8,0,-8])
        n,w=np.meshgrid(np.arange(-32,33,4),np.arange(-32,33,4))
        np.testing.assert_array_equal(self.base,sample_grid(self.source,self.meta,reflect(n,-8,16),reflect(w,-8,16)).astype(np.float32))
    def test_airport_compatibility_selects_the_declared_finest_array(self):
        scene=object.__new__(BakedScene);scene.arrays={'base':np.zeros((2,2)),'regional_transition':np.ones((5,5))*2,'focus':np.ones((3,3))*17}
        grid=lambda key,spacing,size:{'origin_north':-spacing,'origin_west':-spacing,'spacing':spacing,'columns':size,'rows':size,'array_key':key}
        scene.document={'name':'regional','mission':{'player_start':[0,0,100]},'terrain':{'base':grid('base',100,2),'details':[grid('regional_transition',20,5),grid('focus',5,3)]},'airfields':[{'center':[0,0],'runway_length_m':100,'runway_width_m':10}]};scene.target=[0,0,0]
        self.assertEqual(scene.compatibility_view()['runway']['position'][2],17)
    def test_authored_canopy_mask_is_not_repeated_into_the_region(self):
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder);Image.new('RGB',(32,32),(160,180,110)).save(p/'source.png');Image.new('RGB',(32,32),(20,40,20)).save(p/'authored.png')
            meta={'origin_north':-8000,'origin_west':-8000,'spacing':1000,'columns':17,'rows':17}
            material={'uv_origin_north':-8000,'uv_origin_west':-8000,'tile_m':16000}
            macro(p/'source.png',material,meta,64000,p/'result.png',resolution=256,authored_source=p/'authored.png')
            pixels=np.array(Image.open(p/'result.png'));np.testing.assert_array_equal(pixels[:32],np.broadcast_to([160,180,110],pixels[:32].shape))
            np.testing.assert_array_equal(pixels[128,128],[20,40,20])

if __name__=='__main__':unittest.main()
