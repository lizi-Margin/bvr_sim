"""Read actual draw buffers on the GPU and inspect per-tree terrain deformation."""
from pathlib import Path
import argparse,json,math,os,subprocess,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.grove_grounding import placed_stems


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    p.add_argument('--orbit-frames',type=int,default=0,help='Paused camera dolly across the ordinary900mLOD boundary; not physical flight or performance evidence')
    p.add_argument('--sample-groves',type=int,default=0,help='Select bounded diagnostic samples in a complete map;0inspects every grounding batch')
    p.add_argument('--anchor-samples-only',action='store_true',help='One actual GPU vertex per source-tree index/subset; not an all-vertex bounds audit')
    a=p.parse_args()
    if not 0<=a.sample_groves<=24:raise ValueError('Use0..24grounding samples')
    if not 0<=a.orbit_frames<=600:raise ValueError('Use0..600 paused camera frames')
    if a.output.exists():raise FileExistsError(a.output)
    a.output.mkdir(parents=True);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    from bvr_game.app import FlightGame,serialize,native
    g=FlightGame(render=True,visible=False,map_path=a.map,visual_profile=a.visual_profile,output=a.output/'client')
    report={'status':'running','map_sha256':sha(a.map),'visual_profile_sha256':sha(a.visual_profile),
        'core_sha256':sha(Path(native.__file__)),
        'renderer_sha256':sha(Path(g.r.__file__)),
        'vertex_scope':'One GPU vertex per source-tree/subset' if a.anchor_samples_only else 'Every indexed draw vertex',
        'scope':'Compute readback executes the raster vertex grounding helper over actual draw instance/geometry/material/packed-position/UV buffers. It is not a post-raster stream-output capture or collision/CCIP certification.', 'groves':[],'captures':[]}
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True);g.show_hud=False;g.renderer.set_quality('high')
        baseline=serialize(g.sim.frame());terrain=g.sim.terrain();meta=g.baked_scene.document['terrain']['ground_atlas']
        def inspection_eye(n,w,h,distance,minimum_height):
            x=-w+distance*.8;z=n-distance*.6
            y=max(h+max(minimum_height,distance*.16),terrain.height(z,-x)+45)
            # Above-ground eyes can still look through an intervening ridge.
            # Raise only the diagnostic camera, sampling the same core surface.
            for t in np.linspace(0,.984375,64):
                ground=terrain.height(z+(n-z)*t,-(x+(-w-x)*t))
                y=max(y,(ground+3-t*(h+14))/(1-t))
            return [x,y,z]
        def sight_clearance(eye,n,w,h):
            return min(eye[1]+(h+14-eye[1])*t-terrain.height(eye[2]+(n-eye[2])*t,-(eye[0]+(-w-eye[0])*t)) for t in np.linspace(0,1,65))
        candidates=[i for i in g.baked_scene.document['instances'] if 'ground_stems' in i or 'grove_ground_conform' in i]
        if a.sample_groves and len(candidates)>a.sample_groves:
            chosen={}
            for order in [sorted(candidates,key=lambda i:i.get('grove_ground_conform',{}).get('source_height_span_m',0),reverse=True),
                          sorted(candidates,key=lambda i:i['radius_m'],reverse=True),sorted(candidates,key=lambda i:len(i.get('ground_stems',[]))),
                          sorted(candidates,key=lambda i:(i['position'][0]+2500)**2+(i['position'][1]+2100)**2)]:
                for item in order[:max(1,a.sample_groves//4)]:chosen[item['id']]=item
            for item in candidates:
                if len(chosen)>=a.sample_groves:break
                chosen[item['id']]=item
            candidates=list(chosen.values())[:a.sample_groves]
        original_lods={i['id']:i['lod_distance'] for i in candidates}
        report['grounding_batches_in_map']=sum('ground_stems' in i or 'grove_ground_conform' in i for i in g.baked_scene.document['instances'])
        report['selected_grounding_batches']=[i['id'] for i in candidates]
        rng=np.random.default_rng(4901);points=rng.uniform(-9999,9999,(12000,2));boundaries=[]
        for tile in g.baked_scene.document['terrain']['details']:
            n0,w0=tile['origin_north'],tile['origin_west'];n1=n0+(tile['columns']-1)*tile['spacing'];w1=w0+(tile['rows']-1)*tile['spacing']
            for f in [.001,.137,.421,.777,.999]:
                for delta in [-.5,-.1,-.01,0,.01,.1,.5]:
                    boundaries.extend([(n0+delta,w0+f*(w1-w0)),(n1+delta,w0+f*(w1-w0)),(n0+f*(n1-n0),w0+delta),(n0+f*(n1-n0),w1+delta)])
        points=np.asarray([*points,*[p for p in boundaries if max(abs(p[0]),abs(p[1]))<=10000],[-10000,-10000],[10000,10000]],dtype=np.float32)
        heights=np.asarray(g.renderer.gpu_ground_heights(points.tolist()));expected=np.array([terrain.height(float(n),float(w)) for n,w in points]);errors=abs(heights-expected)
        np.savez_compressed(a.output/'gpu-height-samples.npz',points=points,gpu=heights,core=expected,error=errors)
        report['height_atlas']={'state':serialize(g.renderer.ground_atlas_state()),'samples':len(points),'maximum_error_m':float(errors.max()),'p99_error_m':float(np.quantile(errors,.99))}
        assert np.isfinite(heights).all() and errors.max()<.01,report['height_atlas']
        rejected=False
        try:g.renderer.gpu_ground_heights([[10001.,0.]])
        except ValueError:rejected=True
        assert rejected,'Out-of-coverage query was not rejected'
        report['outside_coverage_rejected']=True
        for lod in ['near','far']:
            for item in candidates:item['lod_distance']=100000. if lod=='near' else 0.
            g.baked_scene.configure(g.renderer,g.r,terrain,g.visual_profile)
            for item in candidates:
                n,w,h=item['position'];distance=160 if lod=='near' else 1150
                eye=inspection_eye(n,w,h,distance,55)
                g.set_camera(eye,[-w,h+14,n],.8)
                for _ in range(45):g.draw()
                rows=g.renderer.scenery_ground_vertices(item['id'],all_vertices=not a.anchor_samples_only)
                gpu=np.array([r.world_position for r in rows]);bases=np.array([r.world_base for r in rows]);uv=np.array([r.uv_anchor for r in rows]);indices=np.array([[r.subset,r.vertex_index] for r in rows],dtype=np.uint32)
                manifest=json.loads((ASSETS/'registered'/item['model']/'manifest.json').read_text(encoding='utf8'));cluster=manifest['cluster'];encoding=cluster['ground_conform'];center=np.asarray(cluster['recentering'])
                anchors=np.array([pose['base_anchor'] for pose in cluster['poses_before_recentering']])-center
                if encoding.get('anchor_encoding')=='source_tree_index_uv1':source_uv=np.column_stack([(np.arange(len(anchors))+.5)/len(anchors),np.zeros(len(anchors))])
                else:source_uv=(anchors[:,[0,1]]-encoding['min_local_xz'])/encoding['span_local_xz']
                distances=np.max(abs(uv[:,None,:]-source_uv[None,:,:]),axis=2);match=distances.argmin(axis=1)
                assert distances.min(axis=1).max()<1e-5
                expected_bases=placed_stems(manifest,item);active=np.array([r.source_tree_active for r in rows],dtype=bool)
                np.testing.assert_array_equal(active,match<len(expected_bases))
                source_match=np.where(active,match,0)
                expected_xz=np.column_stack([-expected_bases[source_match,1],expected_bases[source_match,0]])
                horizontal=abs(bases[:,[0,2]]-expected_xz).max()
                actual_heights=np.array([terrain.height(float(z),float(-x)) for x,y,z in bases]);vertical=abs(bases[:,1]-actual_heights)
                true_heights=np.array([terrain.height(float(n),float(w)) for n,w,z in expected_bases]);source_vertical=abs(bases[:,1]-true_heights[source_match])
                lo=np.array(rows[0].bounds_min);hi=np.array(rows[0].bounds_max);outside=np.maximum(np.maximum(lo-gpu,gpu-hi),0)
                surface=np.array([r.surface_position for r in rows]);previous=np.array([r.previous_position for r in rows]);sphere=np.array(rows[0].gpu_instance_sphere)
                surface_error=float(abs(surface-gpu).max());previous_error=float(abs(previous-surface).max())
                expected_center=(lo+hi)/2;expected_radius=float(np.linalg.norm((hi-lo)/2))
                sphere_error=max(float(abs(sphere[:3]-expected_center).max()),abs(sphere[3]-expected_radius))
                assert np.isfinite(gpu).all() and np.isfinite(bases).all()
                assert horizontal<.01 and vertical.max()<.01 and source_vertical.max()<.01,(item['id'],horizontal,vertical.max(),source_vertical.max())
                assert outside.max()==0,(item['id'],outside.max())
                if not active.all():assert abs(gpu[~active]-bases[~active]).max()==0,'Unused source slots must collapse to zero-area geometry'
                assert surface_error<.002 and previous_error<.002 and sphere_error<.002,(surface_error,previous_error,sphere_error)
                np.savez_compressed(a.output/(item['id']+'-'+lod+'-draw-buffers.npz'),world=gpu,bases=bases,uv=uv,indices=indices,expected_bases_nwu=expected_bases,bounds_min=lo,bounds_max=hi,surface=surface,previous=previous,gpu_instance_sphere=sphere,active=active)
                record={'id':item['id'],'lod':lod,'gpu_vertices':len(rows),'source_anchors':len(np.unique(match[active])),'inactive_vertex_records':int((~active).sum()),
                    'subsets':len(set(int(r.subset) for r in rows)),'scale':item['scale'],'yaw':item['yaw'],
                    'maximum_base_horizontal_error_m':float(horizontal),'maximum_gpu_core_height_error_m':float(vertical.max()),
                    'maximum_source_base_height_error_m':float(source_vertical.max()),'maximum_outside_culling_bounds_m':float(outside.max()),
                    'maximum_surface_raster_vertex_error_m':surface_error,'maximum_static_previous_current_error_m':previous_error,
                    'gpu_instance_bounds_sphere_error_m':sphere_error,
                    'bounds_min':lo.tolist(),'bounds_max':hi.tolist(),'source_height_span_m':float(np.ptp(true_heights))}
                report['groves'].append(record);capture=g.capture(item['id']+'-'+lod)
                report['captures'].append({'id':item['id'],'lod':lod,'file':str(capture),'eye':eye,'camera_ground_clearance_m':eye[1]-terrain.height(eye[2],-eye[0]),'sampled_sight_clearance_m':sight_clearance(eye,n,w,h),'statistics':serialize(g.renderer.statistics())})
                write_json(a.output/'partial-report.json',report)
                print('GPU_GROVE',item['id'],lod,'vertices',len(rows),'height_error',vertical.max(),'outside',outside.max(),flush=True)
        if a.orbit_frames:
            import imageio_ffmpeg
            for item in candidates:item['lod_distance']=original_lods[item['id']]
            g.baked_scene.configure(g.renderer,g.r,terrain,g.visual_profile)
            hero=candidates[0];n,w,h=hero['position'];movie=a.output/'ground-lod-dolly.mp4'
            encoder=subprocess.Popen([imageio_ffmpeg.get_ffmpeg_exe(),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','1920x1080','-r','10','-i','-','-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p',str(movie)],stdin=subprocess.PIPE)
            frames=[]
            try:
                for index in range(a.orbit_frames):
                    phase=math.tau*index/max(1,a.orbit_frames-1);distance=110+1290*(.5-.5*math.cos(phase))
                    eye=inspection_eye(n,w,h,distance,45);g.set_camera(eye,[-w,h+14,n],.8);g.draw();encoder.stdin.write(g.renderer.capture_rgb())
                    frames.append({'index':index,'eye':eye,'camera_ground_clearance_m':eye[1]-terrain.height(eye[2],-eye[0]),'sampled_sight_clearance_m':sight_clearance(eye,n,w,h),'visible_lods':list(g.renderer.statistics().visible_lods),'tick':g.sim.frame().tick})
                    if index%15==0:g.capture('dolly-'+str(index));print('GROUND_DOLLY',index,flush=True)
            finally:encoder.stdin.close();code=encoder.wait()
            if code:raise RuntimeError('Ground dolly encoder failed: '+str(code))
            assert min(f['camera_ground_clearance_m'] for f in frames)>=44.99
            assert min(f['sampled_sight_clearance_m'] for f in frames)>=2.99
            report['motion_inspection']={'file':str(movie),'fps':10,'frames':frames,'minimum_camera_ground_clearance_m':min(f['camera_ground_clearance_m'] for f in frames),'minimum_sampled_sight_clearance_m':min(f['sampled_sight_clearance_m'] for f in frames),'scope':'Paused-scene ordinary near/far LOD camera dolly with shared-terrain camera and65-sample sight clearance; not a continuous occlusion proof, physical flight route or performance benchmark'}
        report['core_frame_unchanged']=baseline==serialize(g.sim.frame());report['shader_errors']=g.renderer.shader_errors()
        assert report['core_frame_unchanged'] and report['shader_errors']==0
        report['status']='passed';write_json(a.output/'report.json',report);print('GROUND_GPU_VALIDATION_PASSED',flush=True)
    except BaseException as error:
        report['status']='failed';report['error']=repr(error);write_json(a.output/'failure-report.json',report);raise
    finally:g.close()


if __name__=='__main__':main()
