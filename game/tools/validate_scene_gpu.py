"""Measure actual renderer resources, LODs and terrain vertices against simulation."""
from pathlib import Path
import json,sys,math,random
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json

def validate(out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    g=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/training_range_v2/generated-map.json',output=out/'after/gpu-checks');g.start();g.sim.set_paused(True);g.quality='high';g.renderer.set_quality('high')
    try:
        d=g.baked_scene.document;probes=[]
        for airport in d['airfields']:
            n,w=airport['center']
            for dn in [-1400,-800,0,800,1400]:
                for dw in [-26,0,26,300,700]:probes.append(('airport',n+dn,w+dw,.1))
        for road in d['roads']:
            for a,b in zip(road['points'][:-1],road['points'][1:]):
                for t in [.1,.25,.5,.75,.9]:probes.append(('road',a[0]+(b[0]-a[0])*t,a[1]+(b[1]-a[1])*t,.1))
        for river in d['rivers']:
            for n,w in river['points']:
                for delta in [-200,-85,0,85,200]:probes.append(('riverbank',n,w+delta,.1))
        rng=random.Random(7)
        for _ in range(250):probes.append(('valley_and_focus',rng.uniform(-10000,10000),rng.uniform(-10000,10000),.5))
        for _ in range(100):probes.append(('outer',rng.uniform(-250000,250000),rng.uniform(-250000,250000),.5))
        for n in [-10000.01,-10000,-9999.99,9999.99,10000,10000.01]:
            for w in [-9500,-100,0,1100,9500]:probes.append(('fine_coarse_seam',n,w,.1))
        terrain=g.sim.terrain();samples=[]
        for category,n,w,tolerance in probes:
            sim=terrain.height(n,w);render=g.renderer.render_height(n,w);error=abs(sim-render)
            samples.append({'category':category,'north':n,'west':w,'simulation_height':sim,'render_vertex_height':render,'absolute_error_m':error,'tolerance_m':tolerance})
            if error>tolerance:raise AssertionError(samples[-1])
        parity={'status':'passed','terrain_sha256':d['terrain']['sha256'],'samples':samples,'maximum_absolute_error_m':max(s['absolute_error_m'] for s in samples),'method':'Independent interpolation over renderer CPU vertices uploaded to GPU versus typed GameTerrain; identical triangle planes.'}
        write_json(out/'terrain-parity.json',parity)
        tree=next(x for x in d['instances'] if x['model']=='tree_oak');n,w,h=tree['position'];views={}
        for name,eye in [('near',[-w+200,h+60,n-200]),('far',[-w+4000,h+3000,n-4000]),('reverse',[-w-4000,h+3000,n+4000])]:
            g.set_camera(eye,[-w,h,n])
            for _ in range(10):g.draw()
            views[name]={'statistics':serialize(g.renderer.statistics()),'capture':g.capture('lod_'+name)}
        assert views['near']['statistics']['visible_lods'][0]>0
        assert views['far']['statistics']['visible_lods'][1]>0
        before=serialize(g.renderer.statistics())
        for i in range(100):g.renderer.place_asset('reuse_probe_'+str(i),'tree_oak',[n+i%10*15,w+i//10*15,h],1)
        for _ in range(5):g.draw()
        after=serialize(g.renderer.statistics())
        for key in ['mesh_resources','material_resources','import_counts']:assert before[key]==after[key],key
        assert all(count==1 for count in after['import_counts'].values())
        instancing={'status':'passed','views':views,'one_import_per_glb':True,'additional_shared_instances':100,'before_extra_instances':before,'after_extra_instances':after,'draw_group_definition':'Distinct visible mesh/material subset pairs, an equivalent batching metric; not asserted to be literal GPU draw calls.','chunk_definition':'1-km baked instance lists and 1-km focus terrain meshes; engine frustum culling and per-resource distance culling.'}
        write_json(out/'instancing-and-lod-report.json',instancing)
        assert g.renderer.shader_errors()==0
        return {'terrain_samples':len(samples),'max_height_error_m':parity['maximum_absolute_error_m'],'near_lods':views['near']['statistics']['visible_lods'],'far_lods':views['far']['statistics']['visible_lods'],'imports':after['imported_glbs'],'shader_errors':g.renderer.shader_errors()}
    finally:g.close()
if __name__=='__main__':print(json.dumps(validate(Path(sys.argv[1])),indent=2))
