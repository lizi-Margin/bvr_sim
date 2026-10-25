"""Keep old AI/RL evidence read-only; report deliberate FDM numerical changes."""
from pathlib import Path
import argparse,json,os,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.ground import apply_config
from bvr_game.content import sha,write_json
from validate_player_response_replay import first_difference


def ai(baseline,output):
    file=baseline/'input-tapes/frozen-ai-fullframes.json';rows=json.loads(file.read_text());reference=[];results=[];g=None
    try:
        for altered in [False,True]:
            for index,row in enumerate(rows):
                if g is None:g=FlightGame(map_path=ROOT/'game/maps/training_range_v3/generated-map.json',output=output/'client')
                assert g.scene_hash==row['map_sha256'],'Old baseline map must remain unchanged'
                g.select_aircraft(row['model']);apply_config(native,g.config,row['config']);g.start()
                if altered:
                    p=g.sim.player_flight_profile();p.bank_gain*=1.7;p.pitch_gain*=.4;p.max_bank*=.7;p.release_seconds*=2;g.sim.configure_player_flight(p)
                actual=[];first=None;old_equal=0
                for i,(action,expected) in enumerate(zip(row['actions'],row['frames'])):
                    g.command(**action['command']);g.step(action['ticks']);frame=serialize(g.sim.frame());actual.append(frame)
                    assert not g.sim.player_flight_state().active,'Legacy command entered player assistance'
                    assert frame['tick']==expected['tick'] and frame['sim_time']==expected['sim_time'],'Outer tick/time contract changed'
                    if frame==expected:old_equal+=1
                    elif first is None:first={'sample':i,'tick':frame['tick'],'path':first_difference(expected,frame),'top_level_fields':[k for k in expected if expected[k]!=frame.get(k)]}
                if not altered:reference.append(actual)
                else:assert actual==reference[index],'Changing only player gains changed AI full frames'
                results.append({'model':row['model'],'speed':row['config']['speed'],'player_profile_altered':altered,'frames_compared':len(actual),
                    'old_frozen_frames_exact':old_equal,'first_old_difference':first,'new_player_profile_isolation_exact':altered})
    finally:
        if g:g.close()
    write_json(output/'candidate-ai-reference-fullframes.json',reference)
    return {'old_baseline':str(file),'old_baseline_sha256':sha(file),'cases':results,
        'old_frozen_all_frames_exact':all(r['old_frozen_frames_exact']==r['frames_compared'] for r in results),
        'player_profile_isolation_complete_frames_exact':sum(r['frames_compared'] for r in results if r['player_profile_altered']),
        'scope':'Every existing complete GameFrame field, no tolerance or ignored fields. Original action/tick/map/seed fixed. Old differences remain failures of old numerical equality; a new reference is explicitly named candidate, never substituted for the old baseline.'}


def plain(x):
    if isinstance(x,np.ndarray):return x.tolist()
    if isinstance(x,np.generic):return x.item()
    if isinstance(x,dict):return {k:plain(v) for k,v in x.items()}
    if isinstance(x,(tuple,list)):return [plain(v) for v in x]
    return x


def rl(baseline,output):
    from bvr_sim.bvr_env_cpp import BVR3DEnvCpp
    file=baseline/'before/rl-action-baseline.json';old=json.loads(file.read_text());env=BVR3DEnvCpp(old['config'],[0,1],str(output/'rl-core.log'),str(output/'rl.acmi'));rows=[];steps=[]
    try:
        initial=plain(env.reset(seed=old['seed']));space=env.action_space.nvec.tolist();assert space==old['action_space_nvec'],'RL action dimensions/normalization changed'
        for i,step in enumerate(old['steps']):
            answer=plain(env.step(np.asarray(step['action'])));steps.append({'action':step['action'],'answer':answer})
            rows.append({'step':i,'old_complete_result_exact':answer==step['answer'],'first_old_difference':first_difference(step['answer'],answer)})
        write_json(output/'candidate-rl-results.json',{'config':old['config'],'seed':old['seed'],'action_space_nvec':space,'initial':initial,'steps':steps})
    finally:env.close()
    return {'old_baseline':str(file),'old_baseline_sha256':sha(file),'action_space_nvec_equal':True,'initial_exact':initial==old['initial'],
        'old_frozen_all_steps_exact':all(x['old_complete_result_exact'] for x in rows),'steps':rows,
        'scope':'Actual original RL actions, config and seed; complete observation/reward/done/info compared, without ignored fields. New numeric results are retained as candidate evidence, not a replacement baseline.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--baseline-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--kind',choices=['ai','rl'],required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    result=(ai if a.kind=='ai' else rl)(a.baseline_root,a.output)
    write_json(a.output/'report.json',{'status':'numerical_difference_audit','kind':a.kind,'core_sha256':sha(Path(native.__file__)),'result':result,
        'change':'Shared JSBSim numerical integration maximum5ms; outer commands/time unchanged. The once-per-outer-step AI command filter uses outer dt; inner AI controller uses actual substep dt. No player gain, source force or actuator edits.'})
    print(a.kind,'AUDITED',flush=True)


if __name__=='__main__':main()
