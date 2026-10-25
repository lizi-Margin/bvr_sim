import json,tempfile,unittest
from pathlib import Path
from bvr_game.tacview_assets import inventory,search,fetch

class TacviewAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)/'source';self.cache=Path(self.temp.name)/'cache'
        meshes=self.root/'3D Models/Data/Meshes';db=self.root/'Database/Default Properties';meshes.mkdir(parents=True);db.mkdir(parents=True)
        (self.root/'LICENSE.txt').write_text('Local license fixture')
        (meshes/'F-22.obj').write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
        self.xml=db/'objects.xml';self.xml.write_text('<DefaultPropertiesCollection><DefaultProperties Id="Core"><Criteria><Type>Air+FixedWing</Type></Criteria><Properties><Shape>F-22.obj</Shape></Properties></DefaultProperties><DefaultProperties Id="F22" Base="Core"><Criteria><Name>F-22</Name></Criteria><Properties><FullName>Raptor</FullName></Properties></DefaultProperties><DefaultProperties Id="F22A" Base="F22"><Criteria><Name>F-22A</Name></Criteria></DefaultProperties></DefaultPropertiesCollection>')
    def tearDown(self):self.temp.cleanup()
    def test_inherited_shape_does_not_claim_a_separate_variant_mesh(self):
        data=inventory(self.root,self.cache);a=next(r for r in data['objects'] if r['id']=='F22A')
        self.assertEqual(a['shape_owner'],'Core');self.assertEqual(a['type'],'Air+FixedWing');self.assertEqual(a['model_specificity'],'inherited_shared_shape')
        self.assertEqual(len(data['meshes']),1);self.assertEqual(search(self.root,self.cache,'F-22A')['total'],1)
    def test_fetch_retains_source_coordinates_and_provenance(self):
        result=fetch(self.root,self.cache,'F22A',1);root=Path(result['directory'])
        self.assertEqual((root/'F-22.obj').read_bytes(),(self.root/'3D Models/Data/Meshes/F-22.obj').read_bytes())
        self.assertTrue((root/'LICENSE.txt').exists());props=json.loads((root/'properties.json').read_text())
        self.assertEqual(props['mesh']['triangles'],1);self.assertEqual(props['database_object']['shape_owner'],'Core')
    def test_index_refreshes_when_xml_changes_and_reports_missing_shapes(self):
        inventory(self.root,self.cache);self.xml.write_text(self.xml.read_text().replace('F-22.obj','missing.obj'))
        data=inventory(self.root,self.cache);self.assertFalse(any(r['mesh_exists'] for r in data['objects']))
        with self.assertRaisesRegex(ValueError,'No OBJ'):fetch(self.root,self.cache,'F22A',1)

if __name__=='__main__':unittest.main()
