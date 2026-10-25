"""Fixed real DX12 views for the reference-map quality goal, without UI clicks."""
from pathlib import Path
import argparse,json,math,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.content import sha,write_json
TOOL_SHA256=sha(Path(__file__))

VIEWS={
    'woodland_aerial':([-3800,-2800,2400],[300,100,220]),
    'reference_downlook':([-1500,-1200,2482],[0,0,0]),
    'river_confluence':([13900,33900,2482],[15750,35500,0]),
    'bridge_oblique':([-300,100,160],[-56,300,8]),
    'river_oblique':([-4500,-1600,2200],[5000,750,150]),
    'woodland_low':([-3800,-2000,380],[-2000,-1750,230]),
    'daylight_horizon':([-4000,-3000,2200],[25000,2000,2000]),
    'cloud_layer':([-4000,-3000,2200],[1000,2000,8000])}
def wicked(v):return [-v[1],v[2],v[0]]


def check_grounding(game,extent,output):
    """Bounded GPU draw/atlas and uploaded-mesh comparison against typed core."""
    import numpy as np
    points=np.random.default_rng(165).uniform(-extent+5,extent-5,(12000,2)).astype(np.float32)
    atlas=np.asarray(game.renderer.gpu_ground_heights(points.tolist()))
    core=np.array([game._terrain.height(float(n),float(w)) for n,w in points])
    mesh=np.array([game.renderer.render_height(float(n),float(w)) for n,w in points])
    np.savez_compressed(output/'ground-height-readback.npz',points=points,gpu_atlas=atlas,core=core,uploaded_terrain_mesh=mesh)
    groups=[i for i in game.baked_scene.document['instances'] if 'ground_stems' in i]
    if not groups:raise ValueError('Grounding check requires actual source-tree batches')
    checks=[]
    for target in [[extent*.85,0],[-extent*.7,-extent*.5],[extent*.7,extent*.7],[0,-extent*.85]]:
        item=min(groups,key=lambda i:np.linalg.norm(np.array(i['position'][:2])-target))
        rows=game.renderer.scenery_ground_vertices(item['id'],False)
        bases=np.array([r.world_base for r in rows]);uvs=np.array([r.uv_anchor for r in rows]);active=np.array([r.source_tree_active for r in rows],dtype=bool)
        slots=item['independent_source_layout']['source_slots'];indices=np.rint(uvs[:,0]*slots-.5).astype(int)
        assert ((indices>=0)&(indices<slots)).all(),'Unexpected source-tree UV index'
        stems=np.asarray(item['ground_stems']);np.testing.assert_array_equal(active,indices<len(stems))
        expected=stems[indices[active]];horizontal=float(abs(bases[active][:,[2,0]]-expected*np.array([1,-1])).max())
        expected_height=np.array([game._terrain.height(float(n),float(w)) for n,w in expected]);vertical=float(abs(bases[active,1]-expected_height).max())
        np.savez_compressed(output/(item['id']+'-ground-vertices.npz'),bases=bases,active=active,source_indices=indices,expected_nwu=expected)
        checks.append({'id':item['id'],'active_vertex_samples':int(active.sum()),'maximum_horizontal_error_m':horizontal,'maximum_core_height_error_m':vertical})
    result={'extent_half_m':extent,'atlas_state':serialize(game.renderer.ground_atlas_state()),'height_samples':len(points),
        'maximum_atlas_core_error_m':float(abs(atlas-core).max()),'maximum_uploaded_mesh_core_error_m':float(abs(mesh-core).max()),
        'groves':checks,'scope':'Actual GPU readback and uploaded terrain-mesh vertices at bounded samples;not every tree/vertex certification.'}
    assert max(result['maximum_atlas_core_error_m'],result['maximum_uploaded_mesh_core_error_m'],*[max(i['maximum_horizontal_error_m'],i['maximum_core_height_error_m']) for i in checks])<.01,result
    result['status']='passed';return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    p.add_argument('--runtime',type=Path,default=ROOT/'game/runtime.json')
    p.add_argument('--ignore-map-environment',action='store_true')
    p.add_argument('--warmup-frames',type=int,default=48)
    p.add_argument('--preview-frame',type=int,default=4,help='Save an intermediate native frame without changing the final warmup')
    p.add_argument('--render-scale',type=float,default=1.)
    p.add_argument('--animate-weather',action='store_true',help='Advance Wicked weather time during capture instead of freezing it')
    p.add_argument('--ground-check-extent-m',type=float,default=0,help='Additionally read actual GPU tree/height data over this half-extent;0disables')
    p.add_argument('--environment-variant',type=Path,action='append',default=[],help='Additional environment profile to compare in the same loaded scene;no geometry regeneration')
    p.add_argument('--variant-views',nargs='+',choices=VIEWS,default=['woodland_aerial','daylight_horizon'])
    p.add_argument('--views',nargs='+',choices=VIEWS,default=[v for v in VIEWS if v!='river_confluence']);a=p.parse_args()
    if not math.isfinite(a.ground_check_extent_m) or a.ground_check_extent_m<0:p.error('Ground check extent must be finite and nonnegative')
    a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=a.map,visual_profile=a.visual_profile,runtime=a.runtime,output=a.output/'client',map_environment=not a.ignore_map_environment)
    rows=[];grounding=None;bridge_check=None
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True)
        g.show_hud=False;g.quality='high';g.renderer.set_quality('high')
        if hasattr(g.renderer,'set_presentation_paused'):g.renderer.set_presentation_paused(not a.animate_weather)
        if a.render_scale!=1:
            if not hasattr(g.renderer,'set_render_scale'):raise RuntimeError('Rebuild renderer for supersampled captures')
            g.renderer.set_render_scale(a.render_scale)
        before=serialize(g.sim.frame())
        for name in a.views:
            eye,target=VIEWS[name];g.set_camera(wicked(eye),wicked(target),fov=1.)
            print('REFERENCE_VIEW_BEGIN',name,flush=True)
            for index in range(a.warmup_frames):
                g.draw(1/60)
                if index==0 and hasattr(g.renderer,'primitive_id_state'):
                    write_json(a.output/'primitive-id-state.json',json.loads(g.renderer.primitive_id_state()))
                if index+1==a.preview_frame:
                    preview=g.renderer.capture(str(a.output/(name+'-preview.png')))
                    write_json(a.output/'progress.json',{'view':name,'completed_warmup_frames':index+1,
                        'map_sha256':g.scene_hash,'capture':preview,'scope':'Intermediate frame; final report is written only after every requested view completes'})
                if (index+1)%4==0:print('REFERENCE_WARMUP',name,index+1,'/',a.warmup_frames,flush=True)
            rows.append({'view':name,'eye_nwu':eye,'target_nwu':target,'capture':g.capture(name),
                         'shader_errors':g.renderer.shader_errors(),
                         'reflection_plane':g.renderer.reflection_plane() if hasattr(g.renderer,'reflection_plane') else None})
            if a.ground_check_extent_m and grounding is None:grounding=check_grounding(g,a.ground_check_extent_m,a.output)
            if bridge_check is None and g.baked_scene and g.baked_scene.document.get('source_road_bake'):
                from game.tools.source_bridge_check import check_source_bridge
                bridge_check=check_source_bridge(g,a.output)
            print('REFERENCE_VIEW',name,flush=True)
        from bvr_game.map_library import ENVIRONMENT_KEYS,scene_profile
        base_environment={k:g.visual_profile[k] for k in ENVIRONMENT_KEYS if k in g.visual_profile}
        base_cascades=json.loads(g.renderer.visual_settings())['actual_output']['sun_shadow_cascades_m']
        variants=[]
        for number,path in enumerate(a.environment_variant):
            profile=scene_profile(json.loads(path.read_text()),{},use_environment=False,asset_root=path.parent)
            environment={k:profile[k] for k in ENVIRONMENT_KEYS if k in profile}
            g.renderer.apply_environment(json.dumps(environment));captures=[]
            if 'sun_shadow_cascades_m' in profile:g.renderer.set_shadow_cascades(profile['sun_shadow_cascades_m'])
            else:g.renderer.set_shadow_cascades(base_cascades)
            for name in a.variant_views:
                eye,target=VIEWS[name];g.set_camera(wicked(eye),wicked(target),fov=1.)
                print('ENVIRONMENT_VARIANT_BEGIN',number,name,flush=True)
                for _ in range(a.warmup_frames):g.draw(1/60)
                captures.append({'view':name,'eye_nwu':eye,'target_nwu':target,'capture':g.capture(f'environment_{number}_{name}')})
                print('ENVIRONMENT_VARIANT_VIEW',number,name,flush=True)
            variants.append({'profile':str(path.resolve()),'sha256':sha(path),'effective_environment':environment,
                'actual_settings':json.loads(g.renderer.visual_settings()),'captures':captures})
            write_json(a.output/'environment-progress.json',{'completed_variants':variants,'scope':'Intermediate comparison;final report follows all requested views'})
        if variants:
            g.renderer.apply_environment(json.dumps(base_environment));g.renderer.set_shadow_cascades(base_cascades)
        assert before==serialize(g.sim.frame()),'Rendering changed the paused core frame'
        report={'map':str(a.map.resolve()),'map_sha256':g.scene_hash,
                'visual_profile':str(a.visual_profile.resolve()),'visual_profile_sha256':sha(a.visual_profile),
                'actual_settings':json.loads(g.renderer.visual_settings()),'captures':rows,
                'core_sha256':sha(Path(native.__file__)),'renderer_sha256':sha(Path(g.r.__file__)),
                'statistics':serialize(g.renderer.statistics()),'vram':serialize(g.renderer.memory_usage()),
                'core_frame_unchanged':True,'shader_errors':g.renderer.shader_errors(),
                'warmup_frames_per_view':a.warmup_frames,
                'capture_tool_sha256':TOOL_SHA256,'requested_render_scale':a.render_scale,
                'presentation_clock_frozen':hasattr(g.renderer,'set_presentation_paused') and not a.animate_weather,
                'scope':'Actual1080pHigh paused scene and fixed camera. Images require visual comparison; no FPS gate or finished-quality claim.'}
        report['effective_environment']={k:g.visual_profile[k] for k in ENVIRONMENT_KEYS if k in g.visual_profile}
        if variants:report['environment_variants']=variants
        if grounding is not None:report['grounding_check']=grounding
        if bridge_check is not None:report['source_bridge_check']=bridge_check
        if hasattr(g.renderer,'primitive_id_state'):report['primitive_id_state']=json.loads(g.renderer.primitive_id_state())
        write_json(a.output/'report.json',report)
        assert report['shader_errors']==0
    finally:g.close()
if __name__=='__main__':main()
