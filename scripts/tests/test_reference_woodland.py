"""Clearing geometry must remain open in the woodland recipe and Baker."""
import copy,json,unittest,tempfile,struct,io
from pathlib import Path
from unittest.mock import patch
from shapely.geometry import Polygon
from shapely.ops import unary_union
from bvr_game.reference_woodland import configure,clearing_fields
from bvr_game.worldgen import Baker

ROOT=Path(__file__).resolve().parents[2]

class ReferenceWoodlandTests(unittest.TestCase):
    def test_small_clearings_keep_a_continuous_forest_and_required_openings(self):
        from shapely.geometry import Point
        recipe=json.loads((ROOT/'game/recipes/river_valley_airfield.json').read_text(encoding='utf8'))
        with patch('bvr_game.reference_woodland.crown_mean',return_value=([.04,.06,.035],Path(__file__))),patch('bvr_game.reference_woodland.sha',return_value='fixture'):
            candidate,woods=configure(recipe,recipe['asset_roles']['canopy'][0],clearing_policy={'count':320,'radius_range_m':[35,125]})
        self.assertGreater(woods.area,320e6);self.assertLess(woods.area,380e6)
        for item in [*recipe['settlements'],*recipe['airfields']]:self.assertFalse(woods.contains(Point(item['center'])))
        self.assertEqual(candidate['landscape']['reference_woodland']['version'],2)
        self.assertGreater(sum(len(p.interiors) for p in (woods.geoms if hasattr(woods,'geoms') else [woods])),100)

    def test_textured_crown_mean_uses_opaque_source_pixels_in_linear_light(self):
        from PIL import Image
        from bvr_game.content import sha
        from bvr_game.reference_woodland import crown_mean
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);folder=root/'registered/test';folder.mkdir(parents=True)
            image=Image.new('RGBA',(2,1));image.putdata([(0,255,0,255),(255,0,255,0)]);stream=io.BytesIO();image.save(stream,format='PNG');pixels=stream.getvalue()
            doc={'meshes':[{'primitives':[{'attributes':{'POSITION':0}}]}],
                 'materials':[{'name':'source_leaf','alphaMode':'MASK','alphaCutoff':.35,'pbrMetallicRoughness':{'baseColorFactor':[1,.5,1,1],'baseColorTexture':{'index':0}}}],
                 'textures':[{'source':0}],'images':[{'bufferView':0}],
                 'bufferViews':[{'buffer':0,'byteOffset':0,'byteLength':len(pixels)}]}
            encoded=json.dumps(doc).encode();encoded+=b' '*(-len(encoded)%4);binary=pixels+b'\0'*(-len(pixels)%4)
            file=folder/'test.glb';file.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(binary))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(binary),0x004e4942)+binary)
            (folder/'manifest.json').write_text(json.dumps({'lods':[{'file':'test.glb','sha256':sha(file)}],'conversion_recipe':{'policy':{'crown_albedo_material':'source_leaf'}}}))
            with patch('bvr_game.reference_woodland.ASSETS',root):mean,source=crown_mean('test')
            self.assertEqual(mean,[0,.5,0]);self.assertEqual(source,file)
    def test_holes_survive_into_the_actual_baker_and_fields_stay_outside_woods(self):
        recipe=json.loads((ROOT/'game/recipes/river_valley_airfield.json').read_text(encoding='utf8'))
        with patch('bvr_game.reference_woodland.crown_mean',return_value=([.04,.06,.035],Path(__file__))),patch('bvr_game.reference_woodland.sha',return_value='fixture'):
            candidate,woods=configure(recipe,recipe['asset_roles']['canopy'][0],batches=24000,resolution=8192)
        baker=Baker(candidate)
        zones=candidate['landscape']['reference_woodland']['forest_zone_ids']
        actual=unary_union([baker.forests[id] for id in zones])
        self.assertLess(actual.symmetric_difference(woods).area,1e-6)
        self.assertGreater(woods.area,150e6)
        self.assertTrue(any(len(p.interiors)>0 for p in baker.forests.values()))
        for poly in baker.forests.values():
            for hole in poly.interiors:
                probe=Polygon(hole).representative_point()
                self.assertFalse(poly.contains(probe))
        fields=[{'id':'test','polygon':[[-9000,-9000],[9000,-9000],[9000,9000],[-9000,9000]],
                 'holes':[],'color':[1,1,1,1]}]
        retained=clearing_fields(fields,woods,candidate['settlements'])
        self.assertGreater(len(retained),0)
        for field in retained:
            shape=Polygon(field['polygon'],field['holes'])
            self.assertLess(shape.intersection(woods).area,1e-6)
        self.assertEqual(recipe,json.loads((ROOT/'game/recipes/river_valley_airfield.json').read_text(encoding='utf8')))

if __name__=='__main__':unittest.main()
