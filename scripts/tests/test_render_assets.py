import copy,hashlib,json,tempfile,unittest
from pathlib import Path
from bvr_game.render_assets import distance_lod_models


class DistanceLodIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        root=Path(self.temp.name);parent=root/'parent';derived=root/'derived';parent.mkdir();derived.mkdir()
        self.near=parent/'near.glb';self.near.write_bytes(b'original near mesh')
        self.digest=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
        self.parent=parent/'manifest.json'
        cluster={'recentering':[1,2,3],'source_base_anchor_blender':[0,0,0],
                 'poses_before_recentering':[{'base_anchor':[1,2,0]}]}
        self.parent.write_text(json.dumps({'id':'tree','glb_sha256':self.digest(self.near),'cluster':cluster}))
        (derived/'near.glb').write_bytes(self.near.read_bytes());(derived/'far.glb').write_bytes(b'far source bake')
        self.manifest=derived/'manifest.json'
        self.data={'id':'tree-distance','glb_sha256':self.digest(self.near),'cluster':copy.deepcopy(cluster),
                   'source_distance_lod':{'parent_asset':'tree','parent_manifest_sha256':self.digest(self.parent)},
                   'lods':[{'file':name,'sha256':self.digest(derived/name)} for name in ['near.glb','far.glb']]}
        self.save()

    def save(self):
        self.manifest.write_text(json.dumps(self.data))
        self.profile={'vegetation_distance_lods':{'tree':{'manifest':str(self.manifest),
            'manifest_sha256':self.digest(self.manifest),'parent_manifest':str(self.parent)}}}

    def test_near_bytes_preserved_and_repeated_map_binding_is_valid(self):
        models=distance_lod_models({'tree':str(self.near)},self.profile)
        self.assertEqual(Path(models['tree']).read_bytes(),self.near.read_bytes())
        self.assertEqual(distance_lod_models(models,self.profile),models)

    def test_changed_tree_placement_rejected(self):
        self.data['cluster']['poses_before_recentering'][0]['base_anchor'][0]=99
        self.save()
        with self.assertRaisesRegex(ValueError,'tree placements'):
            distance_lod_models({'tree':str(self.near)},self.profile)

    def test_changed_near_geometry_rejected(self):
        self.data['lods'][0]['sha256']='bad';self.save()
        with self.assertRaisesRegex(ValueError,'near geometry'):
            distance_lod_models({'tree':str(self.near)},self.profile)

    def test_changed_far_file_rejected(self):
        (self.manifest.parent/'far.glb').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'mesh changed'):
            distance_lod_models({'tree':str(self.near)},self.profile)


if __name__=='__main__':unittest.main()
