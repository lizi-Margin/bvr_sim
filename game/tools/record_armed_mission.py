"""Record real legacy-pilot missions for complete-frame headless/DX12 replay.

This is an armed mission regression, not a player Instructor or hardware-input
acceptance test. CombatPilot uses radar contacts, the launch envelope, own state,
owned missile status and warning flags. StrikePilot uses own state, core CCIP and
the map's public target. Complete frames are evaluator diagnostics only.
"""
from pathlib import Path
import argparse
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvr_game.app import FlightGame, native, serialize
from bvr_game.content import sha, write_json
from bvr_game.pilots import CombatPilot, StrikePilot
from bvr_game.playtest import digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--map', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--mission', choices=['air', 'strike', 'combined'], required=True)
    parser.add_argument('--aircraft', choices=['F22', 'F16'], default='F16')
    parser.add_argument('--seed', type=int, default=2201,
                        help='Development regression seed; not heldout')
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--altitude', type=float,
                        help='Explicit scenario spawn altitude in metres; map defaults remain unchanged')
    parser.add_argument('--enemy-range', type=float,
                        help='Explicit scenario initial enemy separation in metres')
    args = parser.parse_args()
    if not 0 < args.seconds <= 1800:
        parser.error('--seconds must be in (0, 1800]')
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ['BVR_SORTIE_LOG_ROOT'] = str((args.output / 'sortie-logs').resolve())
    game = FlightGame(map_path=args.map, output=args.output / 'client')
    records, samples, events, seen = [], [], [], set()
    try:
        game.select_aircraft(args.aircraft)
        game.config.mission = args.mission
        game.config.seed = args.seed
        game.config.enemy_attacks = True
        game.config.enemy_evasion = True
        if args.enemy_range is not None:
            game.config.enemy_range = args.enemy_range
        game.player_profiles_frozen = True
        start = None
        if args.altitude is not None:
            start = list(game.map['mission']['strike_start' if args.mission == 'strike' else 'player_start'])
            start[2] = args.altitude
        game.start(start_position=start)
        initial = serialize(game.sim.frame())
        config = serialize(game.config)
        profile = game.player_profile
        spawn = [game.config.player_north, game.config.player_west, game.config.altitude]
        combat = CombatPilot()
        strike = StrikePilot(game.map['ground_target']['position'])
        while game.sim.frame().result == 'running' and game.sim.frame().sim_time < args.seconds:
            frame = game.sim.frame()
            pilot = strike if args.mission == 'strike' or frame.air_kills else combat
            command = pilot.command(frame, game.player(frame))
            game.weapon = 'Mk-82' if pilot is strike else 'AIM-120C7'
            game.command(**command)
            next_frame = game.step(5)
            value = serialize(next_frame)
            records.append({'tick': frame.tick, 'ticks': next_frame.tick - frame.tick,
                            'command': command, 'frame_sha256': digest(value),
                            'selected_weapon': game.weapon,
                            'phase': 'strike' if pilot is strike else 'combat'})
            for event in value['events']:
                key = (event['tick'], event['kind'], event['actor'], event['target'], event['weapon'])
                if key not in seen:
                    seen.add(key)
                    events.append(event)
            if len(records) % 50 == 0 or next_frame.result != 'running':
                samples.append(value)
            if len(records) % 300 == 0:
                print(args.mission, next_frame.tick, next_frame.result,
                      'air', next_frame.air_kills, 'ground', next_frame.ground_kills, flush=True)
        final = serialize(game.sim.frame())
        report = {'status': 'passed' if final['result'] == 'succeeded' else 'failed',
                  'mission': args.mission, 'aircraft': args.aircraft,
                  'seed': args.seed, 'seed_scope': 'reused development regression',
                  'scenario_overrides': {'altitude_m': args.altitude, 'enemy_range_m': args.enemy_range},
                  'enemy_attacks': config['enemy_attacks'], 'enemy_evasion': config['enemy_evasion'],
                  'core_sha256': sha(Path(native.__file__)), 'map_sha256': game.scene_hash,
                  'tool_sha256': sha(Path(__file__)),
                  'pilot_sha256': sha(ROOT / 'bvr_game/pilots.py'),
                  'config': config, 'final_frame': final, 'events': events,
                  'complete_frame_endpoints': len(records), 'endpoint_interval_s': .1,
                  'logs': game.log_paths(),
                  'scope': __doc__}
        write_json(args.output / 'input-tape.json',
                   {'schema_version': 2, 'kind': 'legacy_ai',
                    'map': str(game.map_path), 'map_sha256': game.scene_hash,
                    'config': config, 'initial_position': spawn,
                    'initial_speed': config['speed'], 'initial_frame': initial,
                    'player_profile': profile, 'actions': records, 'final_frame': final})
        write_json(args.output / 'samples.json', samples)
        write_json(args.output / 'report.json', report)
        print(json.dumps({key: report[key] for key in ['status', 'mission', 'aircraft',
                                                     'complete_frame_endpoints']}), flush=True)
        if report['status'] != 'passed':
            raise RuntimeError('Armed mission failed; input tape and report retained')
    finally:
        game.close()


if __name__ == '__main__':
    main()
