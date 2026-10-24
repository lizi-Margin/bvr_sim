"""End-to-end acceptance of baked content, typed terrain and Agent presentation."""
import json,math,tempfile,unittest
from types import SimpleNamespace
from pathlib import Path
import numpy as np
from bvr_game.content import ROOT,sha
from bvr_game.worldgen import Baker
from bvr_game.mapcheck import validate
from bvr_game.scene_runtime import BakedScene
from bvr_game.presentation import Labels,overlap,safe_aim,ChaseCamera,curve
from bvr_game.geography import local_nwu
from bvr_game.app import FlightGame,native,serialize
from bvr_game.pilots import CombatPilot,StrikePilot
MAP=ROOT/'game/maps/training_range_v2/generated-map.json'

class ContentTests(unittest.TestCase):
    def test_overlapping_grove_crowns_still_enforce_source_stem_spacing(self):
        from bvr_game.grove_grounding import stem_spacing_report
        manifest={'cluster':{'recentering':[0,0,0],'poses_before_recentering':[{'base_anchor':[0,0,0]},{'base_anchor':[0,4,0]}]},
            'conversion_recipe':{'policy':{'cluster':{'inter_grove_stem_spacing_m':2.5}}}}
        a={'id':'a','model':'source','position':[0,0,0],'yaw':0,'scale':1,'radius_m':10}
        b={**a,'id':'b','position':[0,2.6,0]}
        self.assertFalse(stem_spacing_report([a,b],{'source':manifest})['failures'])
        b['position']=[0,2,0]
        report=stem_spacing_report([a,b],{'source':manifest})
        self.assertEqual(len(report['failures']),2)
        self.assertTrue(all(x['distance_m']==2 for x in report['failures']))

    def test_batch_terrain_and_grove_grounding_match_scalar_path(self):
        from bvr_game.worldgen import BakedTerrain
        from bvr_game.grove_grounding import fit_grove
        scene=BakedScene(MAP);meta=scene.document['terrain'];grid=BakedTerrain(scene.arrays['base'],scene.arrays['focus'],meta['base'],meta['details'][0])
        random=np.random.default_rng(3124);points=random.uniform(-12000,12000,(300,2))
        boundary=meta['details'][0]['origin_north'];points=np.vstack([points,[[boundary,0],[boundary-.01,0],[boundary+.01,0]]])
        scalar=np.array([grid.height(*p) for p in points]);batch=grid.height_many(points[:,0],points[:,1])
        np.testing.assert_array_equal(batch,scalar)
        # A real source's64 stem anchors exercise fitting, tilt rejection and
        # retained world anchors. Both paths must accept/reject identically.
        manifest=json.loads((ROOT/'game/assets/registered/fir_grove_normal_a/manifest.json').read_text())
        accepted=0
        for n,w in [(-2500,-2100),(-3000,-2000),(-4000,-1000),(0,0),(7000,7000)]:
            a=fit_grove(manifest,n,w,.37,.9,grid.height,include_anchors=True)
            b=fit_grove(manifest,n,w,.37,.9,grid.height,sample_heights=grid.height_many,include_anchors=True)
            self.assertEqual(a,b)
            accepted+=a is not None
        self.assertGreater(accepted,0)

    def test_channel_uses_shared_bed_banks_and_independent_level_water(self):
        from bvr_game.river_valley import height_rule
        baker=Baker.__new__(Baker)
        baker.r={'terrain':{'river_level_m':120,'airport_height_m':220},'focus_area_km':[20,20],
            'airfields':[],'rivers':[{'points':[[-20000,0],[20000,0]],'width_m':95}],
            'landscape':{'valley_base_rise_m':95,'valley_scale_m':1800,'ridge_start_m':2200,'ridge_scale_m':6000,
                'ridge_amplitude_m':450,'undulation_m':35,'earthwork_blend_m':180,'regional_transition_m':1200}}
        n=np.array([0.,0.,0.,0.,11000.]);w=np.array([0.,35.,47.5,120.,0.]);outer=np.full(n.shape,125.)
        original=height_rule(baker,n,w,outer)
        baker.r['landscape']['river_channel']={'depth_m':4,'bank_width_m':22,'bank_height_m':.8}
        generated=height_rule(baker,n,w,outer)
        self.assertAlmostEqual(float(generated[0]),116.,places=4)
        self.assertLess(generated[1],120.)
        self.assertGreater(generated[2],120.7)
        np.testing.assert_array_equal(generated[3:],original[3:])
        baker.surfaces=[]
        baker.terrain=SimpleNamespace(height=lambda n,w:float(height_rule(baker,np.asarray(n),np.asarray(w),np.asarray(125.))))
        baker.surface_ribbon('river',[[-500,0],[500,0]],95,'water',.025)
        water=np.asarray(baker.surfaces[0]['vertices'])
        np.testing.assert_array_equal(water[:,2],np.full(len(water),120.))
        self.assertGreater(water[0,2]-baker.terrain.height(-500,0),3.9)

    def test_material_only_base_metadata_preserves_complete_core_terrain(self):
        original=BakedScene(MAP);document=json.loads(json.dumps(original.document))
        document['terrain']['base']['material']='presentation_only'
        candidate=BakedScene(MAP,document)
        self.assertEqual(serialize(original.terrain(native)),serialize(candidate.terrain(native)))

    def test_outer_landcover_noise_is_world_coherent_across_bake_stripes(self):
        from bvr_game.regional_cover import smooth_noise
        n,w=np.meshgrid(np.linspace(-12000,14000,51),np.linspace(-10000,18000,65))
        whole=smooth_noise(n,w,3600,3124)
        striped=np.concatenate([smooth_noise(n[:32],w[:32],3600,3124),smooth_noise(n[32:],w[32:],3600,3124)])
        self.assertTrue(np.array_equal(whole,striped))
        self.assertTrue(np.isfinite(whole).all() and np.all((whole>=0)&(whole<=1)))
        self.assertFalse(np.array_equal(whole,smooth_noise(n,w,3600,3125)))

    def test_water_render_batches_preserve_every_triangle_and_local_plane(self):
        # A long conformed ribbon's global bounds can sit far above its local
        # water. Splitting render batches must correct that without moving or
        # removing even one triangle. No asset library or GPU is needed.
        baker=Baker.__new__(Baker);baker.r={};baker.surfaces=[]
        baker.terrain=SimpleNamespace(height=lambda n,w:120+max(n,0)*.001)
        points=[[-80000,600],[-2000,280],[80000,600]]
        baker.surface_ribbon('river',points,95,'water',.025)
        original=baker.surfaces[0]
        def triangles(surfaces):
            return np.concatenate([np.asarray(s['vertices'])[np.asarray(s['indices']).reshape(-1,3)] for s in surfaces])
        before=triangles(baker.surfaces)
        baker.surfaces=[];baker.r={'landscape':{'water_render_chunk_m':500}}
        baker.surface_ribbon('river',points,95,'water',.025)
        self.assertTrue(np.array_equal(before,triangles(baker.surfaces)))
        self.assertTrue(all(s['length_m']<=500 for s in baker.surfaces))
        self.assertTrue(all(s['source_surface']=='river' for s in baker.surfaces))
        old_height=np.asarray(original['vertices'])[:,2]
        self.assertGreater((old_height.min()+old_height.max())/2-120,30)
        local=min(baker.surfaces,key=lambda s:abs(np.asarray(s['vertices'])[:,0].mean()+2000))
        height=np.asarray(local['vertices'])[:,2]
        self.assertLess(abs((height.min()+height.max())/2-120),.1)

    def test_baked_scene_resources_geometry_and_exclusions(self):
        result=validate(MAP);self.assertEqual(result['failures'],[])
        self.assertGreaterEqual(result['instances'],8000);self.assertGreater(result['chunks'],100)
        self.assertLessEqual(result['fine_sample_m'],100);self.assertEqual(len(result['landcover_classes']),7)

    def test_recipe_reproducibility_and_seed_changes(self):
        recipe=json.loads((ROOT/'game/recipes/training_range_v2.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);a=Baker(recipe).bake(root/'a');b=Baker(recipe).bake(root/'b')
            self.assertEqual(a['terrain_sha256'],b['terrain_sha256']);self.assertEqual(a['generated_map_sha256'],b['generated_map_sha256'])
            recipe['seed']+=1;c=Baker(recipe).bake(root/'c')
            self.assertNotEqual(a['generated_map_sha256'],c['generated_map_sha256'])

    def test_corrupted_height_data_is_rejected(self):
        document=json.loads(MAP.read_text())
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'terrain.npz').write_bytes(b'corrupted');(root/'generated-map.json').write_text(json.dumps(document))
            with self.assertRaisesRegex(ValueError,'hash'):BakedScene(root/'generated-map.json')

    def test_multi_resolution_triangle_height_and_occlusion(self):
        terrain=native.GameTerrain();terrain.origin_north=terrain.origin_west=-100;terrain.spacing=200;terrain.heights=[10]*4
        tile=native.TerrainTile();tile.origin_north=tile.origin_west=0;tile.spacing=50;tile.heights=[0,0,0,100];terrain.detail_tiles=[tile]
        self.assertEqual(terrain.height(25,25),0);self.assertEqual(terrain.height(40,40),60)
        self.assertEqual(terrain.height(-25,-25),10)
        self.assertFalse(terrain.line_of_sight([30,30,10],[50,50,10]))

    def test_hud_labels_and_input_stay_outside_panels(self):
        labels=Labels()
        for i in range(8):labels.place(1900,400,'contact_'+str(i)+' / TRACK')
        for i,a in enumerate(labels.placed):
            x0,y0,x1,y1=a['bounds'];self.assertTrue(0<=x0<x1<=1920 and 0<=y0<y1<=1080)
            self.assertFalse(any(overlap(a['bounds'],b['bounds']) for b in labels.placed[i+1:]))
        for x,y in [(1850,400),(-100,-100),(5000,5000)]:
            ax,ay=safe_aim(x,y,1920,1080);self.assertTrue(420<=ax<=1500 and 230<=ay<=780)
        self.assertEqual(curve(.02),0);self.assertLess(curve(.2),.04)

    def test_geographic_origin_axes(self):
        self.assertLess(math.dist(local_nwu(7,50,0,[7,50,0]),[0,0,0]),1e-6)
        north=local_nwu(7,50.01,0,[7,50,0]);east=local_nwu(7.01,50,0,[7,50,0])
        self.assertTrue(1100<north[0]<1120);self.assertTrue(-730<east[1]<-700)

    def test_chase_camera_does_not_fall_behind_fast_exact_steps(self):
        camera=ChaseCamera();plane=SimpleNamespace(position=[0,0,8500],velocity=[300,0,0],orientation=[0,0,0])
        a=camera.update(plane,.02,False,(960,540),1920,1080,False)
        plane.position=[1000,0,8500];b=camera.update(plane,.02,False,(960,540),1920,1080,False)
        self.assertAlmostEqual(b[0][2]-a[0][2],1000,places=6)
        self.assertTrue(25<math.dist(b[0],[0,8500,1000])<40)
        fov=camera.update(plane,.02,False,(960,540),1920,1080,True)[2]
        self.assertTrue(.72<fov<1)

class MissionTests(unittest.TestCase):
    def test_natural_miss_does_not_end_the_sortie(self):
        with tempfile.TemporaryDirectory() as directory:
            game=FlightGame(map_path=MAP,output=directory)
            try:
                game.config.enemy_attacks=False;game.start()
                # A separate 60-km, 6-km-altitude initial condition; support is
                # broken by flying away, never by changing a missile or target.
                game.config.enemy_range=60000;game.config.altitude=6000;game.sim.reset(game.config)
                pilot=CombatPilot(force_early_support_break=True);missed=False
                for _ in range(1100):
                    frame=game.sim.frame();game.command(**pilot.command(frame,game.player(frame)));frame=game.step(5)
                    if any(e.kind=='missile_missed' and e.actor=='player' for e in frame.events):missed=True;break
                    if frame.result!='running':break
                self.assertTrue(missed);self.assertEqual(frame.result,'running')
                game.command(heading=game.player(frame).orientation[2],pitch=0,throttle=1);game.step(250)
                self.assertEqual(game.sim.frame().result,'running')
            finally:game.close()

    def test_live_bvr_uses_real_missile_time_and_enemy_evasion(self):
        with tempfile.TemporaryDirectory() as directory:
            game=FlightGame(map_path=MAP,output=directory)
            try:
                game.start();pilot=CombatPilot();airborne=False;warning=False
                for _ in range(1800):
                    frame=game.sim.frame();game.command(**pilot.command(frame,game.player(frame)));frame=game.step(5)
                    airborne=airborne or any(m.age>5 and m.owner=='player' for m in frame.missiles)
                    warning=warning or frame.missile_warning
                    if frame.result!='running':break
                self.assertEqual(frame.result,'succeeded');self.assertTrue(airborne and warning)
                self.assertTrue(45<=frame.sim_time<=180)
                self.assertTrue(any(e.kind=='missile_launched' and e.actor=='bandit' for e in frame.events))
                self.assertIn('Enemy maneuver: defend',[e.message for e in frame.events])
            finally:game.close()

    def test_ccip_bomb_hits_shared_baked_terrain(self):
        with tempfile.TemporaryDirectory() as directory:
            game=FlightGame(map_path=MAP,output=directory)
            try:
                game.config.mission='strike';game.start();pilot=StrikePilot(game.map['ground_target']['position'])
                for _ in range(1200):
                    frame=game.sim.frame();game.command(**pilot.command(frame,game.player(frame)));frame=game.step(5)
                    if frame.result!='running':break
                self.assertEqual(frame.result,'succeeded');impact=next(e for e in frame.events if e.kind=='bomb_impact')
                self.assertLess(math.dist(impact.position,game.map['ground_target']['position']),45)
                self.assertAlmostEqual(impact.position[2],game.sim.terrain().height(*impact.position[:2]),places=4)
            finally:game.close()

if __name__=='__main__':unittest.main()
