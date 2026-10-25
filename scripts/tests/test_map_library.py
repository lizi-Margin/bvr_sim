"""Published versions must survive draft edits, reject corruption and load core terrain."""
from pathlib import Path
from types import SimpleNamespace
import copy,json,tempfile,unittest
import numpy as np
from bvr_game.content import sha,write_json
from bvr_game.map_authoring import publish
from bvr_game.map_library import MapLibrary,scene_profile,registered_directory
from bvr_game.app import FlightGame,serialize

class MapLibraryTests(unittest.TestCase):
    def test_registered_junction_requires_declared_root_and_same_asset_id(self):
        import os,subprocess
        with tempfile.TemporaryDirectory() as temp:
            base=Path(temp);registered=base/'registered';external=base/'external'
            registered.mkdir();external.mkdir();target=external/'tree';target.mkdir();link=registered/'tree'
            if os.name=='nt':
                subprocess.run(['cmd','/c','mklink','/J',str(link),str(target)],capture_output=True,check=True)
            else:link.symlink_to(target,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'escapes'):registered_directory(registered,'tree',{})
            self.assertEqual(registered_directory(registered,'tree',{'registered_storage_roots':[str(external)]}),target.resolve())
            for bad in ['../tree','tree/other','']:
                with self.assertRaisesRegex(ValueError,'Invalid registered'):registered_directory(registered,bad,{})
            with self.assertRaisesRegex(ValueError,'absolute'):registered_directory(registered,'tree',{'registered_storage_roots':['relative']})
            wrong=external/'different';wrong.mkdir();other=registered/'other'
            if os.name=='nt':subprocess.run(['cmd','/c','mklink','/J',str(other),str(wrong)],capture_output=True,check=True)
            else:other.symlink_to(wrong,target_is_directory=True)
            with self.assertRaisesRegex(ValueError,'escapes'):registered_directory(registered,'other',{'registered_storage_roots':[str(external)]})

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.catalog=self.root/'library/catalog.json'
    def tearDown(self):self.temp.cleanup()
    def source(self,id,height):
        root=self.root/id;root.mkdir();grid=np.full((3,3),height,dtype=np.float32)
        np.savez(root/'terrain.npz',base=grid,focus=grid,landcover=np.zeros((2,2)),macro_color=np.ones((3,3,4)),outer_landcover=np.zeros((2,2)),outer_macro_color=np.ones((3,3,4)))
        tile={'origin_north':-1000,'origin_west':-1000,'spacing':1000,'columns':3,'rows':3}
        doc={'schema_version':2,'name':id,'terrain':{'file':'terrain.npz','sha256':sha(root/'terrain.npz'),'base':tile,'details':[tile]},
             'mission':{'player_start':[0,0,5000],'strike_start':[0,0,5000],'target':[500,0,height],'enemy_range_m':5000,'speed_mps':250},
             'airfields':[{'center':[0,0],'runway_length_m':200,'runway_width_m':20}],
             'materials':{},'resource_versions':{},'instances':[],'surfaces':[]}
        write_json(root/'generated-map.json',doc);(root/'image.png').write_bytes(b'unit-test-image-fixture')
        write_json(root/'captures.json',{'map_sha256':sha(root/'generated-map.json'),'shader_errors':0,'captures':[{'capture':str(root/'image.png')}]})
        write_json(root/'review.json',{'map_sha256':sha(root/'generated-map.json'),'quality':'candidate','capture_report':str(root/'captures.json'),'notes':'Unit-test protocol fixture, not visual acceptance.'})
        return root
    def release(self,source):return publish(source/'generated-map.json',self.catalog,name='test',label=source.name,review=source/'review.json')
    def test_release_freezes_draft_and_rejects_changed_baked_terrain(self):
        source=self.source('first',10);release=self.release(source);library=MapLibrary(self.catalog)
        before=Path(release['map']).read_bytes();(source/'terrain.npz').write_bytes(b'changed draft')
        library.resolve(release['id']);self.assertEqual(Path(release['map']).read_bytes(),before)
        doc=json.loads(before);frozen=Path(release['map']).parent/doc['terrain']['file'];frozen.write_bytes(b'corrupted release')
        with self.assertRaisesRegex(ValueError,'package file changed'):library.resolve(release['id'])
    def test_review_cannot_publish_another_map_revision(self):
        source=self.source('first',10);review=json.loads((source/'review.json').read_text());review['map_sha256']='wrong';write_json(source/'review.json',review)
        with self.assertRaisesRegex(ValueError,'another map'):self.release(source)
        self.assertFalse(self.catalog.exists())
    def test_external_volume_freezes_and_selects_without_a_local_package_copy(self):
        first=self.release(self.source('local',10));source=self.source('external',70)
        index=json.loads(self.catalog.read_text());external=self.root/'other-volume'
        index['storage_roots']={'resources':str(external)};index['default_storage_root']='resources';write_json(self.catalog,index)
        second=publish(source/'generated-map.json',self.catalog,name='external',label='external',review=source/'review.json')
        self.assertTrue(Path(second['map']).is_relative_to(external))
        self.assertFalse((self.catalog.parent/'published/external').exists())
        (source/'terrain.npz').write_bytes(b'draft edited after publication')
        row=MapLibrary(self.catalog).resolve(second['id']);self.assertEqual(row['storage_root'],'resources')
        game=FlightGame(map_path=Path(first['map']),map_catalog=self.catalog,output=self.root/'external-client')
        try:
            game.frontend.open_preparation(True);game.frontend.action(('option','map_version',second['id']));game.frontend.launch()
            self.assertEqual(game.map_path,Path(second['map']));self.assertEqual(game._terrain.height(0,0),70)
            game.input(SimpleNamespace(pressed=[27],held=[],x=0,y=0,quit=False,wheel=0),.02)
            game.load_map_version(first['id']);self.assertEqual(game._terrain.height(0,0),10)
        finally:game.close()
        package=Path(second['map']).parent
        terrain=json.loads(Path(second['map']).read_text())['terrain']['file'];(package/terrain).write_bytes(b'corrupt external release')
        with self.assertRaisesRegex(ValueError,'package file changed'):MapLibrary(self.catalog).resolve(second['id'])

    def test_external_storage_rejects_unknown_alias_relative_root_and_escape(self):
        source=self.source('external-rejected',10)
        with self.assertRaisesRegex(ValueError,'Unknown map storage root'):
            publish(source/'generated-map.json',self.catalog,name='external',label='external',review=source/'review.json',storage_root='missing')
        self.assertFalse(self.catalog.exists())
        write_json(self.catalog,{'schema_version':1,'storage_roots':{'resources':'relative/path'},'maps':[]})
        with self.assertRaisesRegex(ValueError,'absolute directory'):
            publish(source/'generated-map.json',self.catalog,name='external',label='external',review=source/'review.json',storage_root='resources')
        write_json(self.catalog,{'schema_version':1,'storage_roots':{'resources':str(self.root/'other-volume')},
            'maps':[{'id':'escape','storage_root':'resources','manifest':'../outside/release.json'}]})
        with self.assertRaisesRegex(ValueError,'escapes'):MapLibrary(self.catalog).versions()
    def test_selector_cancel_is_a_draft_and_confirm_loads_exact_saved_core_height(self):
        first=self.release(self.source('first',10));second=self.release(self.source('second',70))
        game=FlightGame(map_path=Path(first['map']),map_catalog=self.catalog,output=self.root/'client')
        try:
            old=serialize(game.sim.frame());game.frontend.open_preparation(True)
            game.frontend.action(('option','map_version',second['id']));game.frontend.action(('cancel',))
            self.assertEqual(game.map_path,Path(first['map']));self.assertEqual(serialize(game.sim.frame()),old)
            game.frontend.open_preparation(True);game.frontend.action(('option','map_version',second['id']));game.frontend.launch()
            self.assertEqual(game.mode,'flight');self.assertEqual(game.map_path,Path(second['map']))
            self.assertEqual(game._terrain.height(0,0),70);self.assertEqual(game.config.ground_north,500)
            self.assertEqual(game.sim.frame().tick,0)
            with self.assertRaisesRegex(ValueError,'hangar'):game.load_map_version(first['id'])
        finally:game.close()
    def test_invalid_version_never_changes_core_or_config(self):
        first=self.release(self.source('first',10));game=FlightGame(map_path=Path(first['map']),map_catalog=self.catalog,output=self.root/'client')
        try:
            before=serialize(game.sim.frame());config=serialize(game.config);game.frontend.open_preparation()
            game.frontend.preparation['map_version']='missing';game.frontend.launch()
            self.assertEqual(game.mode,'hangar');self.assertEqual(serialize(game.sim.frame()),before);self.assertEqual(serialize(game.config),config)
        finally:game.close()

    def test_saved_cloud_data_is_frozen_resolved_and_verified(self):
        from PIL import Image
        first=self.release(self.source('plain-cloud-reset',10));source=self.source('cloud-data',70)
        weather=source/'weather.png';Image.new('RGBA',(128,128),(100,160,0,255)).save(weather)
        expected=sha(weather);profile=source/'profile.json'
        write_json(profile,{'volumetric_clouds':True,'cloud_weather_map':{'file':str(weather),'sha256':expected}})
        captures=json.loads((source/'captures.json').read_text());captures.update(visual_profile=str(profile),visual_profile_sha256=sha(profile));write_json(source/'captures.json',captures)
        second=self.release(source);saved=json.loads(Path(second['map']).read_text())['baked_environment']['profile']['cloud_weather_map']
        self.assertTrue(saved['file'].startswith('data/'));weather.unlink();profile.unlink()
        game=FlightGame(map_path=Path(second['map']),map_catalog=self.catalog,output=self.root/'cloud-client')
        try:
            resolved=Path(game.visual_profile['cloud_weather_map']['file']);self.assertEqual(sha(resolved),expected)
            game.load_map_version(first['id']);self.assertNotIn('cloud_weather_map',game.visual_profile)
            game.load_map_version(second['id']);self.assertEqual(sha(game.visual_profile['cloud_weather_map']['file']),expected)
        finally:game.close()
        resolved.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'Map package file changed'):MapLibrary(self.catalog).resolve(second['id'])

    def test_saved_ground_detail_is_frozen_and_rejects_later_file_changes(self):
        from PIL import Image
        from bvr_game.scene_runtime import BakedScene
        source=self.source('ground-detail',10);file=source/'detail.png';Image.new('RGB',(2,2),(90,100,80)).save(file)
        expected=sha(file);detail={k:str(file) for k in ['base_color','normal','roughness_map']};detail.update({k+'_sha256':expected for k in ['base_color','normal','roughness_map']})
        detail.update(tile_m=2.,mean_linear_luminance=.2,strength=.45)
        doc=json.loads((source/'generated-map.json').read_text());doc['materials']={'source':{'color':[1,1,1,1],'tile_m':2000,'roughness':.9,'ground_detail':detail}}
        deck=source/'source-deck.json';deck.write_text('{"unit_fixture":true}')
        doc['source_road_bake']={'bridge':{'source_deck':str(deck),'source_deck_sha256':sha(deck)}}
        (source/'water-footprint.wkb').write_bytes(b'unit-water-footprint')
        write_json(source/'generated-map.json',doc)
        for name in ['captures.json','review.json']:
            value=json.loads((source/name).read_text());value['map_sha256']=sha(source/'generated-map.json');write_json(source/name,value)
        release=self.release(source);file.unlink();saved=BakedScene(release['map']).document['materials']['source']['ground_detail']
        for slot in ['base_color','normal','roughness_map']:self.assertEqual(sha(saved[slot]),expected)
        self.assertTrue(Path(saved['normal']).is_relative_to(Path(release['map']).parent))
        frozen_doc=json.loads(Path(release['map']).read_text());deck.unlink()
        self.assertEqual(sha(Path(release['map']).parent/frozen_doc['source_road_bake']['bridge']['source_deck']),frozen_doc['source_road_bake']['bridge']['source_deck_sha256'])
        self.assertEqual((Path(release['map']).parent/'water-footprint.wkb').read_bytes(),b'unit-water-footprint')
        Path(saved['normal']).write_bytes(b'changed frozen detail')
        with self.assertRaisesRegex(ValueError,'Map package file changed'):MapLibrary(self.catalog).resolve(release['id'])

    def test_saved_weather_is_frozen_switches_on_confirm_and_resets_on_legacy_map(self):
        first=self.release(self.source('clear',10));source=self.source('cloudy',70)
        profile=source/'profile.json';write_json(profile,{'sky_exposure':4,'volumetric_clouds':True,'cloud_layer':{'ray_steps':512},'sun_shadow_cascades_m':[500,4500,10000,24000],'sun_shadow_resolution':4096,'shader_cache':'not-map-weather'})
        report=json.loads((source/'captures.json').read_text());report.update(visual_profile=str(profile),visual_profile_sha256=sha(profile));write_json(source/'captures.json',report)
        second=self.release(source);profile.write_text('{}')
        frozen=json.loads(Path(second['map']).read_text())['baked_environment']
        self.assertNotIn('shader_cache',frozen['profile']);self.assertEqual(frozen['profile']['cloud_layer']['ray_steps'],512)
        self.assertEqual(frozen['profile']['sun_shadow_cascades_m'],[500,4500,10000,24000])
        self.assertEqual(frozen['profile']['sun_shadow_resolution'],4096)
        MapLibrary(self.catalog).resolve(second['id'])
        game=FlightGame(map_path=Path(first['map']),map_catalog=self.catalog,output=self.root/'weather')
        try:
            base=copy.deepcopy(game.visual_profile);before=serialize(game.sim.frame())
            game.frontend.open_preparation(True);game.frontend.action(('option','map_version',second['id']));game.frontend.action(('cancel',))
            self.assertEqual(game.visual_profile,base);self.assertEqual(serialize(game.sim.frame()),before)
            game.load_map_version(second['id']);self.assertEqual(game.visual_profile['sky_exposure'],4)
            self.assertEqual(game.visual_profile['shader_cache'],base['shader_cache'])
            game.load_map_version(first['id']);self.assertEqual(game.visual_profile,base)
        finally:game.close()
        self.assertEqual(scene_profile(base,{'baked_environment':frozen},use_environment=False),base)
        with self.assertRaisesRegex(ValueError,'Invalid baked'):scene_profile(base,{'baked_environment':{'schema_version':1,'profile':{'shader_cache':'bad'}}})

if __name__=='__main__':unittest.main()
