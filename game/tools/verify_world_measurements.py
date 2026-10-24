"""Independent position-derivative check of the real source FDM world adapter."""
from pathlib import Path
import argparse,json,math,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import native,serialize
from bvr_game.content import sha,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--dt',type=float,default=.02,help='Source-only numerical convergence study; does not change the game dt')
    a=p.parse_args();dt=a.dt
    if not .001<=dt<=.02:raise ValueError('Numerical study dt outside[.001,.02]')
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    cases=[([0,0,8500],0.,300),([150000,-50000,8500],.3,300),([-200000,100000,6000],-1.1,500)]
    for model in ['F22','F16']:
        for position,yaw,speed in cases:
            fdm=native.JSBSimFDM(dt,model);fdm.reset(position,[speed*math.cos(yaw),speed*math.sin(yaw),0],[.1,0,yaw])
            world=[];legacy=[]
            ticks=round(3/dt)
            for tick in range(ticks+1):
                old=serialize(fdm.flight_measurements());before=(list(fdm.position),list(fdm.velocity),list(fdm.rpy))
                measured=serialize(fdm.world_flight_measurements())
                assert before==(list(fdm.position),list(fdm.velocity),list(fdm.rpy)),'World measurement mutated source state'
                assert old['position']==measured['position'] and old['speed']==measured['speed']
                assert old['body_rates']==measured['body_rates'] and old['alpha']==measured['alpha'] and old['normal_g']==measured['normal_g']
                assert old['reference_frame']=='legacy_position_map_velocity_attitude_local_nwu'
                assert measured['reference_frame']=='map_nwu'
                assert abs(np.linalg.norm(measured['gravity_up'])-1)<1e-12
                world.append(measured);legacy.append(old)
                if tick<ticks:
                    controls=native.FlightSurfaceControls();controls.throttle=.85;fdm.step_surfaces(controls)
                    assert not fdm.terminated
            position_array=np.array([x['position'] for x in world]);velocity=np.array([x['velocity'] for x in world])
            original=np.array([x['velocity'] for x in legacy])
            # Independent central differences of measured source positions;
            # no reproduction of geodetic rotation equations in this verifier.
            derivative=(position_array[2:]-position_array[:-2])/(2*dt)
            errors=np.linalg.norm(derivative-velocity[1:-1],axis=1)
            old_errors=np.linalg.norm(derivative-original[1:-1],axis=1)
            row={'model':model,'initial_position':position,'source_local_yaw':yaw,'speed':speed,
                'max_world_velocity_error_mps':float(errors.max()),'rms_world_velocity_error_mps':float(np.sqrt(np.mean(errors**2))),
                'max_legacy_velocity_error_mps':float(old_errors.max()),'samples':world,'legacy_samples':legacy}
            rows.append(row);print(model,position,'world_max',row['max_world_velocity_error_mps'],'legacy_max',row['max_legacy_velocity_error_mps'],flush=True)
    maximum=max(row['max_world_velocity_error_mps'] for row in rows)
    write_json(a.output/'report.json',{'status':'passed' if maximum<=.05 else 'failed','maximum_velocity_error_mps':maximum,
        'core_sha256':sha(Path(native.__file__)),'source_fdm_dt':dt,'cases':rows,
        'method':'Actual source FDM integration and independent central difference of fixed-map positions; read-only adapter invariants checked every tick. No GameSession, renderer, forced poses or copied rotation formula.'})
    assert maximum<=.05,maximum


if __name__=='__main__':main()
