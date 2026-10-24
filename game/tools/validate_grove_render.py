"""Inspect actual DX12 grove root transforms and core terrain contact heights."""
from pathlib import Path
import argparse,json,math,os,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import ASSETS,sha,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if (a.output/'report.json').exists():raise FileExistsError(a.output/'report.json')
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(render=True,visible=False,map_path=a.map,visual_profile=ROOT/'game/recipes/player_daylight.json',output=a.output/'client')
    try:
        g.select_aircraft('F16');g.config.mission='training';g.start();g.sim.set_paused(True);g.show_hud=False;g.renderer.set_quality('high')
        document=g.baked_scene.document;groves=[i for i in document['instances'] if 'grove_ground_fit' in i]
        selected={}
        for key in ['tilt_rad','max_anchor_error_m']:
            for item in sorted(groves,key=lambda i:i['grove_ground_fit'][key],reverse=True)[:6]:selected[item['id']]=item
        for item in sorted(groves,key=lambda i:math.hypot(i['position'][0]+2500,i['position'][1]+2100))[:6]:selected[item['id']]=item
        rows=[]
        for item in selected.values():
            manifest=json.loads((ASSETS/'registered'/item['model']/'manifest.json').read_text(encoding='utf-8'))
            cluster=manifest['cluster'];center=np.asarray(cluster['recentering'])
            local=np.array([pose.get('base_anchor',pose['position']) for pose in cluster['poses_before_recentering']])-center
            # Registered source world coordinates: Blender X/Z/Y -> Wicked X/Y/Z.
            actual=np.asarray(g.renderer.scenery_points(item['id'],local[:,[0,2,1]].tolist()))
            n,w,z=actual[:,2],-actual[:,0],actual[:,1]
            heights=np.array([g.sim.terrain().height(float(x),float(y)) for x,y in zip(n,w)])
            errors=np.abs(z-heights)
            rows.append({'id':item['id'],'map_fit':item['grove_ground_fit'],'actual_rendered_anchors_nwu':np.column_stack([n,w,z]).tolist(),
                'core_heights':heights.tolist(),'maximum_error_m':float(errors.max())})
        captures=[]
        hero=next(i for i in groves if i['id'] in selected and i['zone']=='sample_woodland') if any(i['zone']=='sample_woodland' for i in selected.values()) else next(iter(selected.values()))
        n,w,h=hero['position'];target=[-w,h+6,n]
        for label,distance in [('near',90),('near_lod_edge',850),('far_lod_edge',950)]:
            g.set_camera([-w+distance*.8,h+max(18,distance*.16),n-distance*.6],target,.8)
            for _ in range(50):g.draw()
            captures.append({'view':label,'capture':g.capture(label),'statistics':serialize(g.renderer.statistics())})
        maximum=max(row['maximum_error_m'] for row in rows)
        write_json(a.output/'report.json',{'status':'passed' if maximum<=.255 else 'failed','map_sha256':sha(a.map),
            'checked_groves':len(rows),'maximum_actual_render_anchor_error_m':maximum,'rows':rows,'captures':captures,
            'forest_representation':document['forest_representation'],'shader_errors':g.renderer.shader_errors(),
            'scope':'Actual native world transforms against independent core terrain height. Checks source-copy base reference anchors, not every bark vertex or terrain collision outcomes.'})
        assert maximum<=.255,maximum
        assert g.renderer.shader_errors()==0
        print('GROVE_RENDER_CHECKED',len(rows),'max_error_m',maximum,'shader',g.renderer.shader_errors())
    finally:g.close()


if __name__=='__main__':main()
