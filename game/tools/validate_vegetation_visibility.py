"""Render the same source groves across LOD/cull thresholds, then return near.

Uses a bounded subset of real map placements, unchanged source meshes and core
terrain. Both policies are run in separate processes by --policy. Counts prove
submission/LOD selection; saved images require separate visual inspection.
"""
from pathlib import Path
import argparse,copy,json,math,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json
from bvr_game.scene_runtime import BakedScene

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--map',type=Path,required=True);p.add_argument('--runtime',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--policy',choices=['legacy','full','lod-visible'],required=True)
    p.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json')
    a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    source=BakedScene(a.map);doc=copy.deepcopy(source.document)
    groves=[i for i in doc['instances'] if i.get('ground_stems')]
    seed=min(groves,key=lambda i:math.dist(i['position'][:2],[-2500,-1800]))
    groves=sorted(groves,key=lambda i:math.dist(i['position'][:2],seed['position'][:2]))[:8]
    doc['instances']=groves
    doc['terrain']['file']=str(source.height_file)
    atlas=doc['terrain'].get('ground_atlas')
    if atlas:
        atlas['file']=str((a.map.parent/atlas['file']).resolve())
    write_json(a.output/'map.json',doc)
    profile=json.loads(a.visual_profile.read_text(encoding='utf8'))
    profile['aircraft_exhaust_profiles_file']=str(ROOT/'game/config/aircraft_exhaust_profiles.json')
    profile['vegetation_full_detail']=a.policy=='full'
    if a.policy=='lod-visible':profile['vegetation_lod_distance_m']=1200
    write_json(a.output/'profile.json',profile)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sorties')
    from bvr_game.app import FlightGame,serialize,native
    g=FlightGame(render=True,visible=False,map_path=a.output/'map.json',runtime=a.runtime,
                 visual_profile=a.output/'profile.json',output=a.output/'client')
    rows=[]
    try:
        g.select_aircraft('F16');g.start(record=False);g.sim.set_paused(True)
        g.show_hud=False;g.renderer.set_quality('high')
        before=serialize(g.sim.frame())
        n,w,h=seed['position'];target=[-w,h+12,n]
        for name,distance in [('near',500),('lod_threshold',4000),('beyond_cull',50000),('return_mid',4000),('return_near',500)]:
            eye=[target[0],target[1]+distance*.25,target[2]-distance]
            g.set_camera(eye,target,fov=1.)
            for _ in range(8):g.draw(1/60)
            stats=serialize(g.renderer.statistics())
            rows.append({'case':name,'distance_m':distance,'eye':eye,'target':target,
                         'statistics':stats,'vegetation':json.loads(g.renderer.vegetation_state()) if hasattr(g.renderer,'vegetation_state') else None,
                         'capture':g.capture(name)})
            print('VEGETATION_VISIBILITY',a.policy,name,stats['visible_instances'],stats['visible_lods'],flush=True)
        assert before==serialize(g.sim.frame())
        if a.policy=='full':
            for row in rows:
                assert row['statistics']['visible_instances']==len(groves),row
                assert row['statistics']['visible_lods']==[len(groves),0],row
        elif a.policy=='lod-visible':
            for row in rows:
                assert row['statistics']['visible_instances']==len(groves),row
                assert row['vegetation']['distance_hidden_trees']==0,row
            assert rows[0]['statistics']['visible_lods']==[len(groves),0]
            assert rows[2]['statistics']['visible_lods']==[0,len(groves)]
            assert rows[-1]['statistics']['visible_lods']==[len(groves),0]
        else:
            assert rows[1]['statistics']['visible_lods'][1]>0
            assert rows[2]['statistics']['visible_instances']==0
        assert g.renderer.shader_errors()==0
        write_json(a.output/'report.json',{'policy':a.policy,'source_map':str(a.map),'source_map_sha256':sha(a.map),
            'renderer':str(g.r.__file__),'renderer_sha256':sha(Path(g.r.__file__)),
            'core_sha256':sha(Path(native.__file__)),'source_placements':groves,
            'core_frame_unchanged':True,'shader_errors':g.renderer.shader_errors(),'cases':rows,
            'scope':'8 original source groves; all GPU draws and saved frames. No full-map pixel coverage or distant subpixel visibility claim.'})
    finally:g.close()
if __name__=='__main__':main()
