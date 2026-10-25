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
    samples=json.loads((folder/'samples.json').read_text());t=np.array([s['time'] for s in samples])
    # A sample at4.000000000000003 can still belong to the preceding intent
    # interval. Locate the actual recorded request change instead of treating
    # floating time>=4 as proof that the new command has been submitted.
    onset_index=next((i for i,s in enumerate(samples) if s['target']!=samples[0]['target']),None)
    tape=json.loads((folder/'intent-tape.json').read_text());dt=tape['config']['dt'];sample_ticks=summary.get('sample_ticks',tape.get('sample_ticks',5))
    onset_tick=samples[onset_index]['tick']-sample_ticks if onset_index is not None else None
    onset_s=onset_tick*dt if onset_tick is not None else None
    active=np.arange(len(samples))>=onset_index if onset_index is not None else np.zeros(len(samples),dtype=bool)
    m=[s['state']['measured'] for s in samples];vel=np.array([unit(x['velocity']) for x in m])
    errors=np.array([s['direction_error_deg'] for s in samples]);result={'source':str(folder),
        'source_samples_sha256':sha(folder/'samples.json'),'summary':summary,'step_response':None,
        'metrics_scope':('Every0.02s core-controller sample' if summary.get('sample_ticks',5)==1 else 'Extrema at recorded0.1s intervals; not guaranteed to capture every0.02s peak'),
        'protecting_sample_fraction':sum(s['state']['protecting'] for s in samples)/len(samples),
        'energy_limited_sample_fraction':sum(s['state']['energy_limited'] for s in samples)/len(samples),
        'control_normalized_abs_max':{k:max(abs(s['state']['controls'][k]) for s in samples) for k in ['aileron','elevator','rudder']},
        'raw_intent_error_rms_deg':float(np.sqrt(np.mean(errors[active]**2))) if active.any() else None,
        'missing_measurements':[k for k in ['body_rates','alpha','beta','normal_g','density'] if all(x[k] is None for x in m)]}
    steady=summary['case'] in ['fine','up','down','turn_45','turn_90','turn_180']
    if steady and active.any():
        before_window=(~active)&(t>=onset_s-1-1e-8)
        base=unit(np.mean(vel[before_window],axis=0));target=unit(samples[onset_index]['target']);amplitude=angle(base,target)
        if summary['case'].startswith('turn_'):
            yaw=np.unwrap(np.arctan2(vel[:,1],vel[:,0]));before=float(np.mean(yaw[before_window]))
            moved=np.degrees(yaw-before);index=next((i for i in np.flatnonzero(active) if abs(moved[i])>1),None)
            sign=math.copysign(1,moved[index]) if index is not None else 1
            progress=moved*sign;basis='Unwrapped heading progress in the actual initial turn direction; 180-degree intent has two equally valid turn directions'
            amplitude=abs(math.degrees(math.remainder(math.atan2(target[1],target[0])-before,math.tau)))
        else:
            axis=unit(np.cross(base,target));progress=np.degrees(np.unwrap(np.arctan2(np.cross(base,vel)@axis,vel@base)))
            basis='Signed angular progress in the initial path/target great-circle plane; cross-plane error is separately retained in vector direction error'
        def crossing(fraction):
            indices=np.flatnonzero(active&(progress>=amplitude*fraction))
            return float(t[indices[0]]-onset_s) if len(indices) else None
        tolerance=max(.2,min(2,.1*amplitude));remaining=np.maximum.accumulate(errors[::-1])[::-1]
        indices=np.flatnonzero(active&(remaining<=tolerance)&(t<=t[-1]-2))
        result['step_response']={'command_onset_s':onset_s,'command_onset_tick':onset_tick,'first_sample_with_new_request_tick':samples[onset_index]['tick'],
            'onset_source':'Actual recorded target change and preceding sample interval; not a floating-time threshold','command_amplitude_deg':amplitude,'progress_basis':basis,
            'response_delay_10pct_s':crossing(.1),'rise_to_90pct_s':crossing(.9),
            'overshoot_progress_deg':float(max(0,np.max(progress[active])-amplitude)),
            'settling_tolerance_deg':tolerance,'settling_s':float(t[indices[0]]-onset_s) if len(indices) else None,
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
