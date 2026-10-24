"""Exercise the real player controller/FDM without GameSession, renderer or world truth."""
from pathlib import Path
import argparse,json,math,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import native,serialize
from bvr_game.player_profiles import PlayerProfileStore
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seconds',type=float,default=80);p.add_argument('--throttle',type=float,default=.85)
    p.add_argument('--models',nargs='+',choices=['F22','F16'],default=['F22','F16'])
    p.add_argument('--cases',nargs='+',choices=['upright','inverted','near_vertical','heading_wrap'])
    p.add_argument('--profile-file',type=Path)
    p.add_argument('--unprotected',action='store_true',help='Explicitly disable the existing assistance envelope switch for a diagnostic comparison; defaults remain protected')
    a=p.parse_args()
    if not math.isfinite(a.seconds) or a.seconds<=0 or not 0<=a.throttle<=1:p.error('Positive finite duration and throttle in[0,1] required')
    if a.output.exists():p.error('Use a new output directory to preserve earlier failures')
    profiles=PlayerProfileStore(a.profile_file) if a.profile_file else PlayerProfileStore();rows=[]
    cases=[('upright',0.,0.,0.,[1,.1,.03]),('inverted',math.pi,0.,0.,[1,0,0]),
        ('near_vertical',0.,-math.radians(88),0.,[1,0,0]),
        ('heading_wrap',0.,0.,math.radians(179),[-math.cos(math.radians(1)),-math.sin(math.radians(1)),0])]
    if a.cases:cases=[x for x in cases if x[0] in a.cases]
    for model in a.models:
        for name,roll,pitch,yaw,target in cases:
            fdm=native.JSBSimFDM(.02,model);speed=300
            fdm.reset([0,0,8500],[speed*math.cos(pitch)*math.cos(yaw),speed*math.cos(pitch)*math.sin(yaw),-speed*math.sin(pitch)],[roll,pitch,yaw])
            initial=serialize(fdm.world_flight_measurements())
            if abs(math.remainder(initial['orientation'][0]-roll,2*math.pi))>.02 or abs(initial['orientation'][1]-pitch)>.02:
                raise AssertionError(('Requested initial attitude was not applied',model,name,initial))
            controller=native.PlayerFlightController();controller.configure(profiles.native_profile(native,model))
            intent=native.PlayerFlightIntent();intent.direction=target;intent.throttle=a.throttle;intent.protection=not a.unprotected;samples=[]
            for tick in range(round(a.seconds/.02)):
                controls=controller.update(fdm.world_flight_measurements(),intent,.02);fdm.step_surfaces(controls)
                if tick%10==0:samples.append({'tick':tick+1,'measurements':serialize(fdm.world_flight_measurements()),'controller':serialize(controller.state())})
                if fdm.terminated:break
            final=serialize(fdm.world_flight_measurements())
            row={'model':model,'case':name,'initial_rpy':[roll,pitch,yaw],'target':target,'ticks':tick+1,'throttle':a.throttle,'requested_seconds':a.seconds,'protection':intent.protection,
                'terminated':fdm.terminated,'initial':initial,'final':final,'profile_sha256':profiles.resolve(model)['effective_sha256']}
            write_json(a.output/(model+'-'+name+'.json'),{'summary':row,'samples':samples});rows.append(row)
            print(model,name,'ticks',tick+1,'rpy',final['orientation'],'speed',final['speed'],flush=True)
    write_json(a.output/'report.json',{'scope':'Direct core controller and JSBSim FDM; no GameSession or renderer constructed',
        'core_sha256':sha(Path(native.__file__)),'profile_file_sha256':profiles.file_sha256,'source_sha256':sha(Path(__file__)),'cases':rows})
if __name__=='__main__':main()
