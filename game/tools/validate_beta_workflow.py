"""Live resident protocol, real Explorer launch and extended flight control evidence."""
import sys,os,json,math,subprocess,time
from pathlib import Path
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,serialize,native
from bvr_game.content import write_json

def validate(out):
 out=Path(out);os.environ['BVR_SORTIE_LOG_ROOT']=str(out/'sortie-logs'/'中文 sortie logs')
 g=FlightGame(output=out/'after/workflow-client');cases=[]
 try:
  assert not g.log_paths()['current']
  g.select_aircraft('F16');g.config.mission='training';g.start();g.step(10)
  before=serialize(g.sim.frame());expected=g.log_paths()['current']
  g.input(SimpleNamespace(held=[],pressed=[120],quit=False,x=960,y=540),.02)
  assert g.last_log_opened==expected and serialize(g.sim.frame())==before
  shell=[]
  for i in range(8):
   r=subprocess.run(['powershell','-NoProfile','-Command',"[Console]::OutputEncoding=[System.Text.UTF8Encoding]::new(); $s=New-Object -ComObject Shell.Application; @($s.Windows() | ForEach-Object { try { $_.Document.Folder.Self.Path } catch {} }) | ConvertTo-Json -Compress"],capture_output=True,text=True,encoding='utf8',timeout=15)
   try:shell=json.loads(r.stdout.strip() or '[]')
   except json.JSONDecodeError:shell=[]
   if isinstance(shell,str):shell=[shell]
   if any(os.path.normcase(x)==os.path.normcase(expected) for x in shell):break
   time.sleep(.25)
  f9={'handler_vk':120,'expected':expected,'actual_opened':g.last_log_opened,'explorer_folders':shell,'shell_window_confirmed':any(os.path.normcase(x)==os.path.normcase(expected) for x in shell),'full_frame_unchanged':serialize(g.sim.frame())==before,'path_contains_unicode_and_space':True}
  write_json(out/'reports/f9-explorer.json',f9)
  assert f9['shell_window_confirmed'],f9
  for model in ['F22','F16']:
   g.select_aircraft(model);g.config.mission='training'
   for speed in [180,300,500]:
    for key in [87,83]:
     g.config.speed=speed;g.start();initial=serialize(g.player())
     for i in range(40):g.input(SimpleNamespace(held=[key],pressed=[],quit=False,x=960,y=540),.02);g.step()
     p=g.player();up=key==83
     assert (p.orientation[1]<initial['orientation'][1])==up
     cases.append({'model':model,'speed_mps':speed,'key':chr(key),'initial':initial,'final':serialize(p),'pitch_input_positive_still_up':True})
   g.config.speed=300;g.start();samples=[]
   for i in range(15000):
    # Five minutes: long alternating assisted turns, two short direct reversals.
    command={'heading':0.,'pitch':.01,'throttle':1.,'manual_roll':True,'roll_input':max(-.12,min(.12,(.15*math.sin(i/1000)-g.player().orientation[0])*.5))}
    if 100<=i<125:command.update(manual_pitch=True,pitch_input=-1,manual_roll=True,roll_input=-.4)
    if 125<=i<150:command.update(manual_pitch=True,pitch_input=1,manual_roll=True,roll_input=.4)
    if i%25==0:g.command(**command)
    g.step()
    if i%250==0:samples.append(serialize(g.player()))
    assert g.player().alive and all(math.isfinite(v) for v in [*g.player().position,*g.player().velocity,*g.player().orientation]),(model,i)
   cases.append({'model':model,'case':'300sec_bounded_bank_with_short_pitch_roll_reversals','samples':samples,'final':serialize(g.player())})
 finally:g.close()
 # A single resident subprocess survives an invalid request and owns both resets.
 requests=[{'action':'reset','seed':101},{'action':'pause','paused':True},{'action':'step','ticks':25,'command':{'throttle':.8}},{'action':'step','ticks':5,'exact':True},{'action':'unknown'}, {'action':'pause','paused':False},{'action':'reset','seed':102,'model':'F16'},{'action':'observe'},{'action':'logs'},{'action':'close'}]
 r=subprocess.run([sys.executable,'-X','utf8','-m','bvr_game.playtest','serve','--output',str(out/'reports/resident-service')],input=''.join(json.dumps(x)+'\n' for x in requests),capture_output=True,text=True,encoding='utf8',cwd=ROOT,timeout=90)
 (out/'reports/resident-service-stdout.jsonl').write_text(r.stdout,encoding='utf8');(out/'reports/resident-service-stderr.log').write_text(r.stderr,encoding='utf8')
 answers=[json.loads(x) for x in r.stdout.splitlines() if x.startswith('{')];assert r.returncode==0 and len(answers)==9,(r.returncode,r.stderr,r.stdout[:500])
 assert answers[2]['result']['tick']==0 and answers[3]['result']['tick']==5
 assert not answers[4]['ok'] and answers[6]['result']['tick']==0
 o=answers[7]['result'];assert set(o)=={'tick','time','own','contacts','warnings','selected_target','missiles','radar_warning','missile_warning','rwr_mode','mission'} and 'entities' not in o
 write_json(out/'reports/extended-controls-resident-f9.json',{'f9':f9,'control_cases':cases,'resident':{'returncode':r.returncode,'requests':requests,'answers':answers,'player_observation_fields':list(o),'privacy':'Only copied own state, true radar tracks, local RWR/MWS and public mission state; diagnostics are a separate privileged action'}})
 print('F9, extended controls and resident service passed')
if __name__=='__main__':validate(sys.argv[1])
