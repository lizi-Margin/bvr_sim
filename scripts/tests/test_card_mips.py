import struct,unittest,json,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import numpy as np
from bvr_game.card_mips import source_mips,dds_bytes
from bvr_game.scene_runtime import BakedScene
from bvr_game.content import sha


class CardMipTests(unittest.TestCase):
    def test_area_conservation_and_maximum_negative_control(self):
        rgba=np.zeros((8,8,4),dtype=np.uint8);rgba[3,4]=[80,160,40,255]
        area,stats=source_mips(rgba,srgb=True);maximum,control=source_mips(rgba,srgb=True,maximum_alpha=True)
        np.testing.assert_array_equal(area[0],rgba)
        for a,b,s in zip(area,maximum,stats):
            np.testing.assert_array_equal(a[:,:,:3],b[:,:,:3]);self.assertLessEqual(abs(s['mean_alpha']-1/64),.5/255)
        self.assertEqual(maximum[-1][0,0,3],255);self.assertEqual(area[-1][0,0,3],4)
        np.testing.assert_array_equal(area[-1][0,0,:3],rgba[3,4,:3])

    def test_linear_light_color_and_linear_vectors(self):
        rgba=np.full((2,2,4),255,dtype=np.uint8);rgba[:1,:,:3]=0
        color,_=source_mips(rgba,srgb=True);normal,_=source_mips(rgba,srgb=False)
        self.assertEqual(color[-1][0,0,0],188);self.assertEqual(normal[-1][0,0,0],128)

    def test_dds_header_payload_retains_all_levels(self):
        rgba=np.full((4,4,4),80,dtype=np.uint8);levels,_=source_mips(rgba,srgb=True);data=dds_bytes(levels,srgb=True)
        self.assertEqual(data[:4],b'DDS ');self.assertEqual(struct.unpack_from('<I',data,28)[0],3)
        self.assertEqual(struct.unpack_from('<5I',data,128),(29,3,0,1,1));self.assertEqual(data[148:],b''.join(x.tobytes() for x in levels))

    def rejected_sidecar(self,*,supported=True,escape=False):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);asset=root/'registered/sample';asset.mkdir(parents=True);(asset/'model.glb').write_bytes(b'fixture')
            (asset/'bad.dds').write_bytes(b'changed DDS bytes')
            manifest={'source_card_mips':{'materials_by_lod_file':{'model.glb':{'source_impostor_0':{'base_color':{'file':'../escaped.dds' if escape else 'bad.dds','sha256':'wrong'}}}}}}
            (asset/'manifest.json').write_text(json.dumps(manifest));scene=BakedScene.__new__(BakedScene);scene.ground_atlas=None
            scene.document={'resource_versions':{'sample':{'lods':[{'file':'model.glb','sha256':sha(asset/'model.glb')}]}}}
            with patch('bvr_game.content.ASSETS',root):scene.configure(None,SimpleNamespace(SOURCE_CARD_AREA_MIPS=supported),None)

    def test_corrupt_sidecar_fails_before_renderer_configuration(self):
        with self.assertRaisesRegex(ValueError,'sidecar changed'):self.rejected_sidecar()

    def test_sidecar_cannot_escape_registered_asset(self):
        with self.assertRaisesRegex(ValueError,'leaves registered'):self.rejected_sidecar(escape=True)

    def test_old_renderer_cannot_silently_ignore_explicit_mips(self):
        with self.assertRaisesRegex(RuntimeError,'rebuild the renderer'):self.rejected_sidecar(supported=False)


if __name__=='__main__':unittest.main()
