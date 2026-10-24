"""Derive response metrics from recorded actual FDM samples; never simulates."""
from pathlib import Path
import argparse,json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json,sha

def unit(v):
    v=np.asarray(v,dtype=float);return v/max(np.linalg.norm(v),1e-12)
def angle(a,b):return math.degrees(math.acos(float(np.clip(np.dot(unit(a),unit(b)),-1,1))))
def summarize(folder,summary):
    samples=json.loads((folder/'samples.json').read_text());t=np.array([s['time'] for s in samples]);active=t>=4
    m=[s['state']['measured'] for s in samples];vel=np.array([unit(x['velocity']) for x in m])
    errors=np.array([s['direction_error_deg'] for s in samples]);result={'source':str(folder),
        'source_samples_sha256':sha(folder/'samples.json'),'summary':summary,'step_response':None,
        'metrics_scope':'Extrema at recorded 0.1-second intervals; not guaranteed to capture every 0.02-second peak',
        'protecting_sample_fraction':sum(s['state']['protecting'] for s in samples)/len(samples),
        'energy_limited_sample_fraction':sum(s['state']['energy_limited'] for s in samples)/len(samples),
        'control_normalized_abs_max':{k:max(abs(s['state']['controls'][k]) for s in samples) for k in ['aileron','elevator','rudder']},
        'raw_intent_error_rms_deg':float(np.sqrt(np.mean(errors[active]**2))),
        'missing_measurements':[k for k in ['body_rates','alpha','beta','normal_g','density'] if all(x[k] is None for x in m)]}
    steady=summary['case'] in ['fine','up','down','turn_45','turn_90','turn_180']
    if steady and active.any():
        base=unit(np.mean(vel[(t>=3)&(t<4)],axis=0));target=unit(samples[np.flatnonzero(active)[0]]['target']);amplitude=angle(base,target)
        if summary['case'].startswith('turn_'):
            yaw=np.unwrap(np.arctan2(vel[:,1],vel[:,0]));before=float(np.mean(yaw[(t>=3)&(t<4)]))
            moved=np.degrees(yaw-before);index=next((i for i in np.flatnonzero(active) if abs(moved[i])>1),None)
            sign=math.copysign(1,moved[index]) if index is not None else 1
            progress=moved*sign;basis='Unwrapped heading progress in the actual initial turn direction; 180-degree intent has two equally valid turn directions'
            amplitude=abs(math.degrees(math.remainder(math.atan2(target[1],target[0])-before,math.tau)))
        else:
            axis=unit(np.cross(base,target));progress=np.degrees(np.unwrap(np.arctan2(np.cross(base,vel)@axis,vel@base)))
            basis='Signed angular progress in the initial path/target great-circle plane; cross-plane error is separately retained in vector direction error'
        def crossing(fraction):
            indices=np.flatnonzero(active&(progress>=amplitude*fraction))
            return float(t[indices[0]]-4) if len(indices) else None
        tolerance=max(.2,min(2,.1*amplitude));remaining=np.maximum.accumulate(errors[::-1])[::-1]
        indices=np.flatnonzero(active&(remaining<=tolerance)&(t<=t[-1]-2))
        result['step_response']={'command_onset_s':4,'command_amplitude_deg':amplitude,'progress_basis':basis,
            'response_delay_10pct_s':crossing(.1),'rise_to_90pct_s':crossing(.9),
            'overshoot_progress_deg':float(max(0,np.max(progress[active])-amplitude)),
            'settling_tolerance_deg':tolerance,'settling_s':float(t[indices[0]]-4) if len(indices) else None,
            'settling_definition':'First recorded sample after onset whose vector path error stays inside tolerance for the rest of the run, with at least two seconds remaining',
            'final_error_deg':float(errors[-1])}
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    plan=json.loads((a.run/'plan.json').read_text());summary=json.loads((a.run/'summary.json').read_text());rows=[]
    for item in summary['cases']:
        folder=a.run/f"{item['model']}-{item['speed_mps']}-{item['case']}";rows.append(summarize(folder,item))
    result={'status':'candidate_diagnostics','plan':plan,'completed_cases':len(rows),'planned_cases':len(plan['cases']),
        'acceptance_note':'Survival or low final error does not certify transient limits, source flight envelope, visual quality or all aircraft tuning',
        'cases':rows}
    destination=a.output or a.run/'response-metrics.json';write_json(destination,result)
    print('DERIVED_METRICS',len(rows),destination)
if __name__=='__main__':main()
