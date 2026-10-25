"""Hold the player controller tick fixed; refine only actual source FDM steps."""
from pathlib import Path
import argparse,json,math,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_sim.bvr_env_cpp import bvr_sim_cpp as native
from bvr_game.player_profiles import PlayerProfileStore
from bvr_game.app import serialize
from bvr_game.content import sha,write_json
from player_flight_response import intent_values,angle


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--inner-dts',nargs='+',type=float,default=[.02,.01,.005,.0025]);p.add_argument('--outer-dt',type=float,default=.02)
    p.add_argument('--seconds',type=float,default=40);p.add_argument('--models',nargs='+',default=['F16'])
    p.add_argument('--speeds',nargs='+',type=float,default=[500]);p.add_argument('--altitude',type=float,default=3000)
    p.add_argument('--cases',nargs='+',default=['fine','down']);a=p.parse_args()
    if a.output.exists():raise FileExistsError(a.output)
    for dt in a.inner_dts:
        if not 0<dt<=a.outer_dt or abs(a.outer_dt/dt-round(a.outer_dt/dt))>1e-8:raise ValueError('Inner dt must evenly divide the fixed outer controller tick')
    profiles=PlayerProfileStore();rows=[]
    for model in a.models:
        for speed in a.speeds:
            for case in a.cases:
                for dt in a.inner_dts:
                    # New modules expose an explicit legacy integration override;
                    # older modules used their requested dt directly below20ms.
                    fdm=native.JSBSimFDM(dt,model,dt) if hasattr(native.JSBSimFDM,'inner_dt') else native.JSBSimFDM(dt,model)
                    fdm.reset([-20000,0,a.altitude],[speed,0,0],[0,0,0])
                    controller=native.PlayerFlightController();controller.configure(profiles.native_profile(native,model));samples=[]
                    for tick in range(round(a.seconds/a.outer_dt)):
                        t=tick*a.outer_dt;values=intent_values(case,math.floor(t/.5)*.5)
                        intent=native.PlayerFlightIntent();intent.direction=values['direction'];intent.throttle=values['throttle']
                        controls=controller.update(fdm.world_flight_measurements(),intent,a.outer_dt)
                        for _ in range(round(a.outer_dt/dt)):fdm.step_surfaces(controls)
                        m=serialize(fdm.world_flight_measurements());state=serialize(controller.state())
                        samples.append({'tick':tick+1,'time':(tick+1)*a.outer_dt,'measured':m,'controller':state,'path_error_deg':angle(values['direction'],m['velocity'])})
                        if fdm.terminated:break
                    m=[x['measured'] for x in samples];g=[x['normal_g'] for x in m if x['normal_g'] is not None]
                    row={'model':model,'speed_mps':speed,'altitude_m':a.altitude,'case':case,'requested_fdm_dt':dt,'actual_inner_dt':getattr(fdm,'inner_dt',dt),'controller_dt':a.outer_dt,'fdm_calls_per_controller_tick':round(a.outer_dt/dt),
                        'ticks':len(samples),'terminated':fdm.terminated,'profile_sha256':profiles.resolve(model)['effective_sha256'],
                        'normal_g_range':[min(g),max(g)] if g else None,'maximum_abs_body_pitch_rate':max(abs(x['body_rates'][1]) for x in m),
                        'final_error_deg':samples[-1]['path_error_deg'],'minimum_speed_mps':min(x['speed'] for x in m),'final_speed_mps':m[-1]['speed']}
                    file=a.output/f'{model}-{speed}-{case}-{dt}.json';write_json(file,{'summary':row,'samples':samples});row['file']=str(file);rows.append(row)
                    print(json.dumps(row),flush=True)
    write_json(a.output/'report.json',{'scope':'Direct source FDM and native player controller, no GameSession/rendering. Same0.02scontroller update and held controls across FDM substeps. No gain,actuator,force,pose or velocity edits after reset.','core_sha256':sha(Path(native.__file__)),'source_sha256':sha(Path(__file__)),'profile_file_sha256':profiles.file_sha256,'cases':rows})


if __name__=='__main__':main()
