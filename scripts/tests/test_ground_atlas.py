"""Source terrain representation, provenance failures and curved grove placement."""
import tempfile,unittest
from pathlib import Path
import numpy as np
from bvr_game.ground_atlas import build_atlas,write_atlas,load_atlas
from bvr_game.heightfield import sample_grid
from bvr_game.grove_grounding import conform_grove


class GroundAtlasTests(unittest.TestCase):
    def setUp(self):
        self.terrain={'sha256':'checked-source','base':{'origin_north':0,'origin_west':0,'spacing':20,'columns':2,'rows':2},'details':[]}
        self.arrays={'base':np.array([[0,0],[0,20]],dtype=np.float32)}
        self.grid={'origin_north':0,'origin_west':0,'spacing':5,'columns':5,'rows':5}

    def test_refinement_preserves_indexed_triangle_crease(self):
        atlas=build_atlas(self.arrays,self.terrain,self.grid)
        points=np.random.default_rng(49).uniform(0,20,(1000,2));n,w=points.T
        actual=sample_grid(atlas,self.grid,n,w)
        np.testing.assert_allclose(actual,np.maximum(0,n+w-20),rtol=0,atol=1e-6)
        # Bilinear interpolation of the same coarse four corners is observably
        # a different surface: at (5,5), indexed height=0, bilinear=1.25m.
        self.assertEqual(float(sample_grid(atlas,self.grid,5,5)),0.)
        self.assertGreater((5/20)*(5/20)*20,1.)

    def test_rejects_misaligned_grids_and_modified_or_foreign_files(self):
        with self.assertRaisesRegex(ValueError,'align'):build_atlas(self.arrays,self.terrain,{**self.grid,'spacing':3})
        with self.assertRaisesRegex(ValueError,'beyond'):build_atlas(self.arrays,self.terrain,{**self.grid,'columns':6})
        with tempfile.TemporaryDirectory() as d:
            metadata=write_atlas(d,self.arrays,self.terrain,self.grid)
            np.testing.assert_array_equal(load_atlas(metadata,Path(d)/'map.json','checked-source'),build_atlas(self.arrays,self.terrain,self.grid))
            with self.assertRaisesRegex(ValueError,'different'):load_atlas(metadata,Path(d)/'map.json','other-version')
            Path(metadata['file']).write_bytes(b'altered')
            with self.assertRaisesRegex(ValueError,'bytes/hash'):load_atlas(metadata,Path(d)/'map.json','checked-source')

    def test_each_source_tree_uses_curved_terrain_instead_of_a_rigid_plane(self):
        manifest={'cluster':{'ground_conform':{'anchor_local_y':0},'recentering':[0,0,0],
            'poses_before_recentering':[{'base_anchor':[x,y,0]} for x,y in [(-10,-10),(-10,10),(10,-10),(10,10),(0,0)]]}}
        height=lambda n,w:100+.1*n*n+.05*w*w
        result=conform_grove(manifest,5,7,.7,1.2,height,include_anchors=True)
        stems=np.array(result['_world_anchors']);np.testing.assert_allclose(stems[:,2],height(stems[:,0],stems[:,1]))
        self.assertGreater(np.ptp(stems[:,2]),20)
        self.assertEqual(result['up_normal'],[0,1,0])
        plane=np.column_stack([stems[:,:2],np.ones(len(stems))]);fit=plane@np.linalg.lstsq(plane,stems[:,2],rcond=None)[0]
        self.assertGreater(abs(fit-stems[:,2]).max(),5)


if __name__=='__main__':unittest.main()
