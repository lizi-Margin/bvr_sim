"""DDSx corruption bounds and verified resource fetches, without a GPU or game installation."""
import hashlib,importlib.util,json,struct,tempfile,unittest,zlib
from pathlib import Path
from bvr_game.wt_assets import search,fetch

FILE=Path(__file__).resolve().parents[2]/'game/tools/import_wt_textures.py'
SPEC=importlib.util.spec_from_file_location('wt_decoder',FILE)
decoder=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(decoder)

class WTResourceTests(unittest.TestCase):
    def blob(self,payload,flags=0,size=None,packed=None):
        return struct.pack('<IIIHHBBHHBBII',0x78534444,0x31545844,flags,4,4,1,0,0,0,0,0,
            len(payload) if size is None else size,len(payload) if packed is None else packed)+payload

    def test_uncompressed_mip_flags_retained(self):
        converted,meta=decoder.decode_payload(self.blob(b'12345678',0x40000))
        header=decoder.HEADER.unpack_from(converted)
        self.assertEqual(header[2],0x40000);self.assertEqual(header[12],0)
        self.assertEqual(converted[32:],b'12345678');self.assertEqual(meta['width'],4)

    def test_zlib_roundtrip_keeps_format_and_mip_order(self):
        source=b'abcd'*128;payload=zlib.compress(source)
        converted,meta=decoder.decode_payload(self.blob(payload,0x80040000,size=len(source)))
        self.assertEqual(converted[32:],source)
        self.assertEqual(decoder.HEADER.unpack_from(converted)[2],0x40000)
        self.assertEqual(meta['payload_sha256'],hashlib.sha256(source).hexdigest())

    def test_truncation_size_bounds_and_missing_codec(self):
        for blob in (b'DDSx',self.blob(b'a',size=2),self.blob(b'a',size=1025),
            self.blob(b'a',0x80000000,packed=5),self.blob(b'a',0x60000000),self.blob(b'a',0x40000000)):
            with self.subTest(blob=blob),self.assertRaises(ValueError):decoder.decode_payload(blob,max_bytes=1024)

    def test_resource_fetch_rejects_changed_pixels(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source=root/'landclass/forest.png';source.parent.mkdir();source.write_bytes(b'original pixels')
            digest=hashlib.sha256(source.read_bytes()).hexdigest();report=root/'report.json'
            report.write_text(json.dumps({'textures':[{'status':'decoded','png':str(source),'png_sha256':digest,
                'source':'original.ddsx','source_sha256':'source-hash','width':4,'height':4,'mode':'RGB'}]}))
            self.assertEqual(search(report,'forest',8)['total'],1)
            result=fetch(report,root/'cache','landclass/forest',1)
            self.assertEqual((Path(result['directory'])/result['entry']).read_bytes(),source.read_bytes())
            self.assertFalse(json.loads(Path(result['manifest']).read_text())['distribution_allowed'])
            source.write_bytes(b'changed pixels')
            with self.assertRaisesRegex(ValueError,'changed'):fetch(report,root/'cache','landclass/forest',1)

    def test_registered_model_fetch_preserves_geometry_and_rejects_corruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);report=root/'report.json';report.write_text(json.dumps({'textures':[]}))
            asset=root/'registered/WT-Test';asset.mkdir(parents=True);mesh=asset/'test.glb';mesh.write_bytes(b'mesh fixture')
            digest=hashlib.sha256(mesh.read_bytes()).hexdigest()
            manifest={'id':'WT-Test','name':'Source oak','file':'test.glb','glb_sha256':digest,'triangles':412,
                'bounds_blender':{},'license':'user-owned-local-War-Thunder-resource','source_url':'local://test',
                'lods':[{'file':'test.glb','sha256':digest}]}
            (asset/'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(search(report,'oak',8,root/'registered','model')['total'],1)
            self.assertEqual(search(report,'oak',8,root/'registered','material')['total'],0)
            result=fetch(report,root/'cache','WT-Test',1,root/'registered')
            self.assertEqual((Path(result['directory'])/result['entry']).read_bytes(),b'mesh fixture')
            mesh.write_bytes(b'changed mesh')
            with self.assertRaisesRegex(ValueError,'changed'):fetch(report,root/'cache','WT-Test',1,root/'registered')

if __name__=='__main__':unittest.main()
