"""Fly actual physics through the immutable public river-valley route, then observed contact."""
from pathlib import Path
import argparse,json,os,sys,shutil
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.playtest import observe_local,digest
from bvr_game.route_pilot import ScenicRoutePilot
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seconds',type=int,default=420)
    p.add_argument('--map',type=Path,default=ROOT/'game/maps/river_valley_airfield/generated-map.json');a=p.parse_args();a.output.mkdir(parents=True,exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    doc=json.loads(a.map.read_text())
    if doc.get('data_version'):a.map=a.map.parent/'versions'/doc['data_version']/'generated-map.json'
    recipe=json.loads((a.map.parent/'scene-recipe.json').read_text())
    pilot=ScenicRoutePilot(recipe['display_flight']['waypoints_nwu'],180,180)
    g=FlightGame(map_path=a.map,output=a.output/'client');g.player_profiles_frozen=True
    records=[];samples=[]
    try:
        g.select_aircraft('F16','intercept');g.config.mission='air';g.config.seed=2201;g.config.enemy_attacks=False;g.config.enemy_evasion=False;g.config.enemy_range=140000
        g.start(initial_speed=180);profile=g.player_profile;config=serialize(g.config);initial=serialize(g.sim.frame())
        # JSBSim reset performs its own initial Run(); replay needs the
        # configured spawn, not the already-advanced tick-zero FDM position.
        position=[g.config.player_north,g.config.player_west,g.config.altitude]
        shutil.copy2(native.__file__,a.output/Path(native.__file__).name)
        for _ in range(a.seconds*2):
            o=observe_local(g);intent=pilot.intent(o);before=o.tick;g.submit_player(**intent);g.step(25);f=g.sim.frame()
            records.append({'tick':before,'ticks':f.tick-before,'player_intent':intent,'frame_sha256':digest(serialize(f)),'phase':pilot.phase})
            samples.append({'observation':serialize(observe_local(g)),'phase':pilot.phase,'state':serialize(g.sim.player_flight_state())})
            if len(records)%40==0:print('ROUTE',f.sim_time,pilot.phase,'wp',pilot.index,'own',list(g.player().position),'tracks',len(f.contacts),'result',f.result,flush=True)
            if pilot.complete(f.sim_time) or not g.player().alive or f.result!='running':break
        report={'status':'passed' if pilot.complete(f.sim_time) and f.sim_time>=180 else 'failed','duration_s':f.sim_time,'phase':pilot.phase,
            'arrivals':pilot.arrivals,'waypoints_total':len(pilot.waypoints),'first_observed_contact':pilot.first_contact,
            'approach_initial_range_m':pilot.approach_initial_range,'latest_observed_range_m':pilot.latest_range,'player_alive':g.player().alive,'core_result':f.result,
            'map':str(a.map.resolve()),'map_sha256':g.scene_hash,'core_sha256':sha(Path(native.__file__)),'player_profile':profile,'logs':g.log_paths(),
            'observation_boundary':'Pilot receives LocalObservation copies and public recipe waypoints; complete frames are diagnostic outputs only. No teleports or forced poses.'}
        write_json(a.output/'report.json',report);write_json(a.output/'samples.json',samples)
        write_json(a.output/'intent-tape.json',{'schema':2,'kind':'player_intent','map':str(a.map.resolve()),'map_sha256':g.scene_hash,'config':config,
            'initial_position':position,'initial_speed':180,'initial_frame':initial,'player_profile':profile,'actions':records,'final_frame':serialize(f)})
        print(json.dumps({k:v for k,v in report.items() if k not in ['player_profile','first_observed_contact']},indent=2),flush=True)
    finally:g.close()
if __name__=='__main__':main()
