"""Camera-only override on the existing exact replay engine; actual DX12 bounds."""
from pathlib import Path
import argparse,json,math,sys
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native
from bvr_game.playtest import replay
from bvr_game.player_profiles import PlayerProfileStore
from bvr_game.content import sha,write_json
from validate_player_handler import basis_error


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--tape',type=Path,required=True)
    p.add_argument('--camera-profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=195);p.add_argument('--zoom-windows',nargs='*',type=float,default=[50,58,90,98])
    p.add_argument('--source-hull',action='store_true',help='Also project a convex hull of actual source rest-scene vertices; no geometry is rewritten')
    a=p.parse_args()
    if len(a.zoom_windows)%2:p.error('--zoom-windows needs start/end pairs')
    a.output.mkdir(parents=True,exist_ok=False);camera_store=PlayerProfileStore(a.camera_profile)
    rows=[];last_tick=None;settings=None;maximum_basis=0.;captures=[];hull=None;hull_source=None
    camera_implementation_sha256=sha(ROOT/'bvr_game/presentation.py')
    original_draw=FlightGame.draw;original_apply=FlightGame.apply_recorded_player_profile
    def apply(game,profile):
        nonlocal settings
        original_apply(game,profile);candidate=camera_store.resolve(profile['aircraft_id'])
        assert candidate['control']==profile['control'] and candidate['input']==profile['input'],'Camera comparison requires unchanged flight/input settings'
        settings=candidate['camera'];game.chase.settings=settings
    def draw(game,dt=1/60,*,free=False):
        nonlocal last_tick,maximum_basis,hull,hull_source
        t=game.sim.frame().sim_time;game.zoom=any(begin<=t<end for begin,end in zip(a.zoom_windows[::2],a.zoom_windows[1::2]))
        original_draw(game,dt,free=free)
        if settings is None or t<0 or t>a.seconds or game.sim.frame().tick==last_tick:return
        last_tick=game.sim.frame().tick;own=game.player();bounds=game.current_aircraft()['appearance']['bounds']
        basis=list(game.renderer.entity_basis('player'));origin=[-own.position[1],own.position[2],own.position[0]];pixels=[]
        for x in [bounds['min'][0],bounds['max'][0]]:
            for y in [bounds['min'][1],bounds['max'][1]]:
                for z in [bounds['min'][2],bounds['max'][2]]:
                    world=[origin[i]+x*basis[0][i]+z*basis[1][i]+y*basis[2][i] for i in range(3)]
                    pixels.append(list(game.renderer.project([world[2],-world[0],world[1]])))
        box=[min(p[0] for p in pixels),min(p[1] for p in pixels),max(p[0] for p in pixels),max(p[1] for p in pixels)]
        root=list(game.renderer.project(own.position));bottom=game.height*980/1080
        subject=game.chase.framing_state.get('subject_position_wicked',origin)
        subject_pixel=list(game.renderer.project([subject[2],-subject[0],subject[1]]))
        overlap=box[0]<game.width*1340/1920 and box[2]>game.width*580/1920 and box[3]>bottom
        maximum_basis=max(maximum_basis,basis_error(game))
        row={'tick':last_tick,'time_s':t,'bank_rad':own.orientation[0],'zoom':game.zoom,'camera':dict(game.camera_params),
            'framing':dict(game.chase.framing_state),'root_pixel':root,'source_bounds_projected':box,'bottom_hud_overlap':overlap,
            'subject_pixel':subject_pixel,
            'clearance_to_bottom_hud_pixels':bottom-box[3],'all_bounds_in_front':all(0<p[2]<1 for p in pixels)}
        if a.source_hull:
            if hull is None:
                from audit_aircraft_surface import scene_positions
                from scipy.spatial import ConvexHull
                import numpy as np
                file=Path(game.current_aircraft()['appearance']['file']);vertices=scene_positions(file)
                hull=vertices[ConvexHull(vertices).vertices].copy();hull[:,2]*=-1
                # Native GLTF import changes source right-handed Z to the
                # renderer's left-handed Z. Check against registered bounds.
                source_bounds=hull[:,[0,2,1]]
                assert np.max(np.abs(source_bounds.min(axis=0)-bounds['min']))<.03
                assert np.max(np.abs(source_bounds.max(axis=0)-bounds['max']))<.03
                hull_source={'file':str(file),'sha256':sha(file),'source_vertices':len(vertices),'hull_vertices':len(hull),
                    'scope':'Actual source rest-scene vertices with declared hierarchy, not an8cornerbox or pixel segmentation. Runtime surface/gear animations are inspected in the real movie separately.'}
            projected=[]
            for local in hull:
                world=[origin[i]+sum(local[j]*basis[j][i] for j in range(3)) for i in range(3)]
                projected.append(list(game.renderer.project([world[2],-world[0],world[1]])))
            hb=[min(p[0] for p in projected),min(p[1] for p in projected),max(p[0] for p in projected),max(p[1] for p in projected)]
            row.update(source_hull_projected=hb,source_hull_clearance_pixels=bottom-hb[3],
                source_hull_bottom_hud_overlap=hb[0]<game.width*1340/1920 and hb[2]>game.width*580/1920 and hb[3]>bottom,
                source_hull_in_front=all(0<p[2]<1 for p in projected))
        rows.append(row)
        if len(rows)%100==1:captures.append(game.capture('framing-'+str(last_tick)))
    with patch.object(FlightGame,'apply_recorded_player_profile',apply),patch.object(FlightGame,'draw',draw):
        result=replay(a.tape,a.output/'replay',render=True,video=True,window_start=0,window_end=a.seconds,
            visual_profile=ROOT/'game/recipes/player_daylight.json')
    report={'status':result['status'],'core_sha256':sha(Path(native.__file__)),'camera_profile_sha256':sha(a.camera_profile),
        'effective_camera':settings,'camera_implementation_sha256':camera_implementation_sha256,'tape_sha256':sha(a.tape),'replay':result,'samples':rows,'captures':captures,
        'maximum_render_basis_error':maximum_basis,'bottom_hud_overlap_samples':sum(x['bottom_hud_overlap'] for x in rows),
        'minimum_conservative_clearance_pixels':min(x['clearance_to_bottom_hud_pixels'] for x in rows),
        'maximum_root_anchor_error_pixels':max(abs(x['root_pixel'][1]-settings['subject_y']*1080) for x in rows) if 'subject_y' in settings else None,
        'maximum_subject_anchor_error_pixels':max(abs(x['subject_pixel'][1]-settings['subject_y']*1080) for x in rows) if 'subject_y' in settings else None,
        'source_hull':hull_source,'source_hull_overlap_samples':sum(x.get('source_hull_bottom_hud_overlap',False) for x in rows) if hull_source else None,
        'minimum_source_hull_clearance_pixels':min(x['source_hull_clearance_pixels'] for x in rows) if hull_source else None,
        'scope':'Existing exact replay engine and frozen native/input profile; only camera settings override. Zoom changes only presentation. Every drawn sample uses actual renderer projection and actual entity basis. Source bounds are conservative boxes, not pixel segmentation. No forced aircraft pose, simulation reset during flight, damage injection or hardware-input claim.'}
    write_json(a.output/'report.json',report)
    assert result['status']=='passed' and result['shader_errors']==0 and maximum_basis<1e-5
    print('CAMERA_VALIDATED',len(rows),'overlap',report['bottom_hud_overlap_samples'],'clearance',report['minimum_conservative_clearance_pixels'],'anchor',report['maximum_root_anchor_error_pixels'],flush=True)


if __name__=='__main__':main()
