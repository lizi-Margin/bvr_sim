"""Retain the previous failing own-state policy on AI and player entry points.

The legacy AI policy is copied literally from the preserved failed harness.
The player variant converts its heading/elevation request into an NWU direction;
it uses its own measured altitude, so it does not share an AI-generated tape.
"""
from pathlib import Path
import argparse,hashlib,json,math,os,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.app import FlightGame,native,serialize
from bvr_game.player_profiles import PlayerProfileStore
from bvr_game.content import sha,write_json
from bvr_game.playtest import digest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--profile-file',type=Path,required=True)
    p.add_argument('--historical-harness',type=Path,required=True)
    p.add_argument('--map',type=Path,default=ROOT/'game/maps/training.json');a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);os.environ['BVR_SORTIE_LOG_ROOT']=str(a.output/'sortie-logs')
    g=FlightGame(map_path=a.map,output=a.output/'client');g.profile_store=PlayerProfileStore(a.profile_file);g.player_profiles_frozen=True
    rows=[]
    try:
        for entry in ['legacy_ai','player_intent']:
            for model in ['F22','F16']:
                g.select_aircraft(model);g.config.mission='training';g.config.speed=300;g.start()
                initial=serialize(g.sim.frame());config=serialize(g.config);samples=[];actions=[]
                for i in range(15000):
                    command={'heading':.4 if (i//1500)%2==0 else -.4,
                        'pitch':max(-.05,min(.08,(8500-g.player().position[2])*.00005)),'throttle':.85}
                    if 100<=i<125:command.update(manual_pitch=True,pitch_input=-1,manual_roll=True,roll_input=-.4)
                    if 125<=i<150:command.update(manual_pitch=True,pitch_input=1,manual_roll=True,roll_input=.4)
                    if i%25==0:
                        if entry=='legacy_ai':g.command(**command);values=command
                        else:
                            az=command['heading'];el=command['pitch']
                            values={k:v for k,v in command.items() if k not in ['heading','pitch']}
                            values.update(direction=[math.cos(el)*math.cos(az),math.cos(el)*math.sin(az),math.sin(el)],mode='assisted')
                            g.submit_player(**values)
                        actions.append({'tick':g.sim.frame().tick,'request':values})
                    g.step();f=g.sim.frame();own=g.player(f)
                    if i%5==4 or not own.alive:samples.append({'time':f.sim_time,'tick':f.tick,'own':serialize(own),'controller':serialize(g.sim.player_flight_state())})
                    if i%25==24 or not own.alive:actions[-1].update(ticks=f.tick-actions[-1]['tick'],frame_sha256=digest(serialize(f)))
                    if not own.alive or f.result!='running':break
                name=entry+'-'+model;folder=a.output/name
                write_json(folder/'samples.json',samples)
                write_json(folder/'diagnostic-tape.json',{'entry':entry,'map':str(a.map.resolve()),'map_sha256':g.scene_hash,
                    'config':config,'initial_frame':initial,'player_profile':g.player_profile,'actions':actions,'final_frame':serialize(f)})
                # Also retain the existing evaluator's replay format, rather
                # than making a second replay engine for this diagnostic.
                standard_actions=[{'tick':x['tick'],'ticks':x['ticks'],'frame_sha256':x['frame_sha256'],
                    'command' if entry=='legacy_ai' else 'player_intent':x['request']} for x in actions]
                write_json(folder/'intent-tape.json',{'schema':2,'kind':'legacy_action' if entry=='legacy_ai' else 'player_intent',
                    'map':str(a.map.resolve()),'map_sha256':g.scene_hash,'config':config,
                    'initial_position':[config['player_north'],config['player_west'],config['altitude']],
                    'initial_speed':config['speed'],'initial_frame':initial,'player_profile':g.player_profile,
                    'actions':standard_actions,'final_frame':serialize(f)})
                row={'entry':entry,'model':model,'ticks':f.tick,'actual_seconds':f.sim_time,'alive':own.alive,'result':f.result,
                    'final_own':serialize(own),'minimum_height_m':min(x['own']['position'][2] for x in samples),
                    'maximum_height_m':max(x['own']['position'][2] for x in samples),'player_controller_active':g.sim.player_flight_state().active,
                    'tape':str(folder/'diagnostic-tape.json'),'samples':str(folder/'samples.json')}
                rows.append(row);write_json(a.output/'progress.json',{'cases':rows});print(name,row['ticks'],row['alive'],flush=True)
        write_json(a.output/'report.json',{'status':'diagnostic_not_acceptance','cases':rows,'core_sha256':sha(Path(native.__file__)),
            'profile_sha256':g.profile_store.file_sha256,'source_sha256':sha(Path(__file__)),
            'historical_harness':str(a.historical_harness),'historical_harness_sha256':sha(a.historical_harness),
            'scope':'Original 300s alternating heading/altitude feedback policy, same300m/s initial speed and two0.5s manual reversals; no shortened manoeuvre or relaxed survival gate. AI policy retains original typed command semantics. Player policy uses only own altitude and the same public heading/elevation requests. Failure is recorded, not erased.',
            'comparison_limit':'Separate controller paths produce different own-altitude feedback and hence different later input values. This is policy comparison, not equal-input frame parity; frozen AI/RL parity is checked separately.'})
    finally:g.close()


if __name__=='__main__':main()
