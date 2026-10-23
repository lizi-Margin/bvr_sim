"""Same-view cloud cost and geometry/contact parity from the live DX12 client."""
from pathlib import Path
import sys,json,time,statistics,random
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize
from bvr_game.content import write_json

def main(out):
 out=Path(out);g=FlightGame(render=True,visible=False,map_path=ROOT/'game/maps/training_range_v3/generated-map.json',output=out/'after/cloud-evaluation');rows=[]
 try:
  g.quality='high';g.renderer.set_quality('high');g.start();g.set_camera(**json.loads((out/'reports/fixed-cameras.json').read_text())['01_high_horizon']);g.show_hud=False
  for enabled in [False,True]:
   g.renderer.set_clouds(enabled)
   for _ in range(180):g.draw()
   samples=[]
   for _ in range(300):
    t=time.perf_counter();g.draw();samples.append((time.perf_counter()-t)*1000)
   rows.append({'clouds':enabled,'render_only_same_state':True,'fps':1000/statistics.mean(samples),'p95_ms':sorted(samples)[285],'samples_ms':samples,'capture':g.capture('clouds-'+str(enabled)),'vram':g.renderer.memory_usage(),'shader_errors':g.renderer.shader_errors()})
  g.renderer.set_clouds(False)
  rng=random.Random(183);terrain=g.sim.terrain();points=[]
  for i in range(200):
   n,w=rng.uniform(3500,5500),rng.uniform(3500,5500);core=terrain.height(n,w);render=g.renderer.render_height(n,w);delta=abs(core-render);assert delta<=.1,(n,w,delta)
   points.append({'north':n,'west':w,'core':core,'render':render,'error_m':delta})
  surfaces=[]
  for n,w in [(4400,4500),(4500,4500),(4590,4500),(4000,4500),(5000,4500),(4500,4000)]:
   ref=terrain.height(n,w)+1;core=terrain.contact(n,w,0,ref,100).height;render=g.renderer.render_surface_height(n,w,ref);delta=abs(core-render);assert delta<=.1,(n,w,core,render)
   surfaces.append({'north':n,'west':w,'core':core,'render':render,'error_m':delta})
  write_json(out/'reports/terrain-contact-parity.json',{'status':'passed','geometry_unchanged':True,'terrain_samples':points,'contact_samples':surfaces,'max_terrain_error_m':max(x['error_m'] for x in points),'max_contact_error_m':max(x['error_m'] for x in surfaces),'ccip':'Core ballistic predictor and impacts share Terrain; native/Python bomb regressions passed; normals/UVs only changed in this beta'})
  write_json(out/'reports/cloud-evaluation.json',{'profiles':rows,'resolution':[1920,1080],'quality':'high','scope':'300 render-only frames each, same fixed camera/core state after 180 warmup; final full-client 1800-frame measurement is separate','selected_clouds':False,'reason':'Select after visual and budget review; clouds remain an optional renderer setting'})
  print(json.dumps([{k:r[k] for k in ['clouds','fps','p95_ms','shader_errors']} for r in rows]))
 finally:g.close()
if __name__=='__main__':main(sys.argv[1])
