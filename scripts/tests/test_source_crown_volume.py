"""Source-derived foliage volume invariants, independent of Blender and DX12."""
import json,struct,tempfile,unittest
from pathlib import Path
import numpy as np
from bvr_game.source_crown_volume import crown,export_cluster

class SourceCrownVolumeTests(unittest.TestCase):
    def test_volume_retains_actual_source_vertices_albedo_and_outward_normals(self):
        rng=np.random.default_rng(8103)
        points=rng.uniform([0,0,0],[2,1,3],(1500,3))
        colors=np.tile([.07,.13,.035],(len(points),1))
        first=crown(points,colors,.8);again=crown(points,colors,.8)
        for a,b in zip(first[:3],again[:3]):np.testing.assert_array_equal(a,b)
        vertices,normals,tints,cells=first
        self.assertGreater(cells,1)
        source={tuple(v) for v in points}
        self.assertTrue(all(tuple(v) in source for v in vertices))
        np.testing.assert_allclose(np.linalg.norm(normals,axis=1),1,atol=1e-12)
        tri=vertices.reshape(-1,3,3)
        facing=np.einsum('ij,ij->i',np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),normals[::3])
        self.assertTrue(np.all(facing>0))
        np.testing.assert_allclose(tints,np.tile([.07,.13,.035,1],(len(vertices),1)),atol=1e-12)

    def test_exported_glb_has_tree_indices_and_source_color_for_each_real_copy(self):
        rng=np.random.default_rng(918)
        mesh=crown(rng.uniform(0,1,(200,3)),np.tile([.1,.2,.05],(200,1)),.8)
        cluster={'recentering':[0,0,0],'poses_before_recentering':[
            {'position':[0,0,0],'yaw':0.,'scale':1.},
            {'position':[3,4,0],'yaw':.5,'scale':1.2}]}
        with tempfile.TemporaryDirectory() as temp:
            file=Path(temp)/'tree.glb';faces,vertices=export_cluster(file,mesh,cluster)
            data=file.read_bytes();magic,version,size=struct.unpack_from('<III',data)
            self.assertEqual((magic,version,size),(0x46546c67,2,len(data)))
            length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length])
            attrs=doc['meshes'][0]['primitives'][0]['attributes'];offset=28+length
            accessor=doc['accessors'][attrs['TEXCOORD_1']];view=doc['bufferViews'][accessor['bufferView']]
            uv=np.frombuffer(data,dtype='<f4',count=vertices*2,offset=offset+view['byteOffset']).reshape(-1,2)
            self.assertEqual(vertices,len(mesh[0])*2);self.assertEqual(faces,vertices//3)
            np.testing.assert_array_equal(uv[:vertices//2,0],.25)
            np.testing.assert_array_equal(uv[vertices//2:,0],.75)
            np.testing.assert_array_equal(uv[:,1],0.)
            self.assertIn('COLOR_0',attrs)

if __name__=='__main__':unittest.main()
