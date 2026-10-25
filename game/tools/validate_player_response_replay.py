"""Compare recorded complete player states and GameFrames against this core."""
from pathlib import Path
import argparse,json,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.playtest import digest
from bvr_game.ground import apply_config
from bvr_game.content import write_json,sha

def first_difference(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        if set(a)!=set(b):return path+'.keys'
        for k in a:
            different=first_difference(a[k],b[k],path+'.'+k)
            if different:return different
        return None
    if isinstance(a,list) and isinstance(b,list):
        if len(a)!=len(b):return path+'.length'
        for i,(x,y) in enumerate(zip(a,b)):
            different=first_difference(x,y,path+f'[{i}]')
            if different:return different
        return None
    return None if a==b else path

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    folders=sorted(p.parent for p in a.run.glob('*/intent-tape.json'));rows=[];g=None
    try:
        for folder in folders:
            tape=json.loads((folder/'intent-tape.json').read_text());samples=json.loads((folder/'samples.json').read_text())
            if sha(tape['map'])!=tape['map_sha256']:raise ValueError('Recorded map changed')
            if g is None:g=FlightGame(map_path=Path(tape['map']),output=a.output/'client');g.player_profiles_frozen=True
            if g.scene_hash!=tape['map_sha256']:raise ValueError('Mixed maps require separate validation runs')
            apply_config(native,g.config,tape['config']);g.start(start_position=tape['initial_position'],initial_speed=tape['initial_speed']);g.apply_recorded_player_profile(tape['player_profile'])
            index=0;frames=0;difference=None
            for action in tape['actions']:
                g.submit_player(**action['player_intent']);remaining=action['ticks']
                while remaining:
                    count=min(remaining,tape.get('sample_ticks',5));g.step(count);remaining-=count
                    current=serialize(g.sim.player_flight_state());expected=samples[index]
                    if g.sim.frame().tick!=expected['tick']:difference={'sample':index,'path':'tick'};break
                    path=first_difference(expected['state'],current)
                    if path:difference={'sample':index,'tick':expected['tick'],'path':path,'expected':expected['state'],'actual':current};break
                    index+=1
                if difference:break
                if digest(serialize(g.sim.frame()))!=action['frame_sha256']:difference={'action':frames,'path':'complete_GameFrame'};break
                frames+=1
            row={'case':folder.name,'player_state_samples_equal':index,'complete_frames_equal':frames,
                'status':'passed' if difference is None and index==len(samples) and frames==len(tape['actions']) else 'failed','difference':difference,
                'tape_sha256':sha(folder/'intent-tape.json')};rows.append(row)
            write_json(a.output/'progress.json',{'cases':rows});print(row['case'],row['status'],index,frames,flush=True)
            if difference:break
        status='passed' if len(rows)==len(folders) and all(r['status']=='passed' for r in rows) else 'failed'
        write_json(a.output/'report.json',{'status':status,
            'core_sha256':sha(Path(native.__file__)),'source_run':str(a.run),'cases':rows,'comparison':'Exact equality of every existing typed player state field at each recorded sample interval (sample_ticks in each tape; legacy default5), and complete GameFrame SHA at every0.5sintent boundary. No ignored fields or tolerance.'})
        if status!='passed':raise SystemExit(1)
    finally:
        if g:g.close()
if __name__=='__main__':main()
