"""Validate real ACMI trajectories, types, lifecycles and sloped vehicle attitude."""
from pathlib import Path
import sys,json,math,hashlib
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import native,serialize
from bvr_game.content import write_json
from scripts.tests.test_sortie_logs import acmi,to_nwu

def validate(out):
 out=Path(out);battle=out/'reports/playtests/final-fixed20/102';d=json.loads((battle/'input-tape.json').read_text());r=json.loads((battle/'report.json').read_text());log=Path(r['logs']['recent'])
 rows,removed,headers=acmi(log/'battle.acmi');samples={round(f['sim_time']/.02):f for f in d['samples']};matches=[];types=set();uids=set();last_time=-1
 for t,id,props in rows:
  assert t>=last_time;last_time=t;types.add(props['Type']);uids.add(props['Pilot'])
  tick=round(t/.02)
  if tick in samples:
   e=next((e for e in samples[tick]['entities'] if e['uid']==props['Pilot'] and e['alive']),None)
   if e:
    lon,lat,alt,*angles=map(float,props['T'].split('|'));delta=math.dist(e['position'],to_nwu(lon,lat,alt));assert delta<.13,(t,e['uid'],delta)
    matches.append({'tick':tick,'uid':e['uid'],'nwu_error_m':delta})
 assert 'Air+FixedWing' in types and 'Weapon+Missile' in types and removed and len(matches)>100
 folder=out/'sortie-logs/typed-export-coverage';folder.mkdir(exist_ok=True)
 s=native.GameSession(str(folder/'base.log'));terrain=native.GameTerrain();terrain.origin_north=terrain.origin_west=-1000;terrain.spacing=2000;terrain.heights=[-100,100,-100,100];s.set_terrain(terrain)
 config=native.GameConfig();config.mission='training';config.altitude=5000;config.bombs=2
 ground=native.GroundUnitSpec();ground.uid='export_jeep';ground.position=[0,0,0];route=native.VehicleRoute();route.points=[[0,0],[100,0]];route.speed=5;ground.route=route;config.ground_units=[ground]
 try:
  s.reset(config);s.begin_recording(str(folder/'core.log'),str(folder/'battle.acmi'),'2026-10-24T00:00:00Z')
  command=native.PilotCommand();command.drop_bomb=True;command.throttle=.85;s.submit(command);s.step(100);frame=serialize(s.frame());s.end_recording()
 finally:s.close()
 cover,_,_=acmi(folder/'battle.acmi');assert any(x[2]['Type']=='Weapon+Bomb' for x in cover)
 final_ground=next(e for e in frame['entities'] if e['uid']=='export_jeep');last=next(p for _,_,p in reversed(cover) if p['Pilot']=='export_jeep');pitch=float(last['T'].split('|')[4]);assert abs(pitch-math.degrees(final_ground['orientation'][1]))<1e-5,(pitch,final_ground)
 write_json(folder/'core-frame.json',frame)
 f9=json.loads((out/'reports/f9-explorer.json').read_text())
 report={'status':'passed','battle':str(log),'battle_seed':102,'battle_duration_s':d['final_frame']['sim_time'],'actual_aircraft_and_missile_uids':sorted(uids),'types':sorted(types),'hex_ids_valid':True,'removed_objects':len(removed),'time_monotone':True,'position_samples_compared':len(matches),'max_nwu_error_m':max(x['nwu_error_m'] for x in matches),'coordinate_method':'independent WGS84 ECEF inverse at original core tangent origin','samples':matches,'extra_types':{'directory':str(folder),'types':sorted({p['Type'] for _,_,p in cover}),'ground_slope_pitch_export_deg':pitch,'core_pitch_deg':math.degrees(final_ground['orientation'][1])},'f9':f9,'unit_test_evidence':{'file':'scripts/tests/test_sortie_logs.py','coverage':['two distinct sorties preserve previous bytes','preview/select/reset no false sorties','exact fullFrame logging on/off and input journal replay','actual missile trajectory and removal','explicit bad-root path failure','Chinese and space paths']},'note':'Air/missile battle used the frozen patrol core; final core corrects ground pitch sign only. No simulation or scoring change.'}
 write_json(out/'acmi-logging-report.json',report);print('ACMI parsed and compared',len(matches),'samples; max error',report['max_nwu_error_m'])
if __name__=='__main__':validate(sys.argv[1])
