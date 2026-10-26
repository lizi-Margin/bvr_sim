"""Watch a local Agent fly an armed patrol, with replayable inputs and GPU evidence.

python -m bvr_game.autoplay --aircraft F16 --seed 101 --speed 4
The policy uses only copied own state, radar contacts and cockpit warnings.
Escape or closing the window stops the sortie; Space pauses/resumes it.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import math
from pathlib import Path
import subprocess
import time

from .app import ROOT, serialize
from .content import write_json
from .playtest import LocalCombatPilot, ResidentPlaytest, POLICY_SHA


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError('Expected a finite positive number')
    return number


def play(output, model='F16', seed=101, speed=4., render=True, visible=True,
         video=False, seconds=600., shot_interval=55., map_path=None):
    if not all(math.isfinite(v) and v > 0 for v in (speed, seconds, shot_interval)):
        raise ValueError('Speed and duration must be finite and positive')
    if video and not render:
        raise ValueError('Video requires rendering')
    # Keep every attempt, including failures and user cancellations.
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    host = ResidentPlaytest(output, render, map_path=map_path, visible=visible)
    game = host.game
    encoder = None
    frames = 0
    captures = []
    phases = []
    seen = set()
    events = []
    reason = 'duration_limit'
    paused = False
    started = time.perf_counter()
    try:
        game.entry_point = 'autoplay'
        observation = host.reset(seed, model)
        pilot = LocalCombatPilot(seed, shot_interval=shot_interval)
        if render:
            original_hud = game.hud
            def agent_hud():
                texts, lines = original_hud()
                for text in texts:
                    if text.text.startswith(('P / PAUSE','PAUSED  |')):
                        text.text = 'AGENT PAUSED / SPACE resume' if paused else 'AGENT / '+pilot.phase.upper()
                    elif text.text.startswith('V weapon'):
                        text.text = f'AGENT  |  {speed:g}x requested  |  SPACE pause / ESC stop'
                return texts, lines
            game.hud = agent_hud
            for _ in range(30):
                game.renderer.poll()
                game.draw(0)
            captures.append(game.capture('start'))
        if video:
            import imageio_ffmpeg
            encoder = subprocess.Popen([
                imageio_ffmpeg.get_ffmpeg_exe(), '-y', '-loglevel', 'error',
                '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '1920x1080',
                '-r', '10', '-i', '-', '-c:v', 'libx264', '-preset', 'fast',
                '-crf', '23', '-pix_fmt', 'yuv420p', str(output/'autoplay.mp4')],
                stdin=subprocess.PIPE)
        next_decision = 0
        deadline = time.perf_counter()
        with (output/'decisions.jsonl').open('w', encoding='utf8') as decisions:
            while observation.mission['result'] == 'running' and observation.time < seconds:
                if render:
                    event = game.renderer.poll()
                    if event.quit or 27 in event.pressed:
                        reason = 'user_cancelled'
                        break
                    if 32 in event.pressed:
                        paused = not paused
                        host.pause(paused)
                    if paused:
                        game.draw(0)
                        time.sleep(.02)
                        deadline = time.perf_counter()
                        continue
                if observation.tick >= next_decision:
                    command = pilot.command(observation)
                    game.command(**command)
                    decisions.write(json.dumps({'observation': asdict(observation),
                                                'command': command, 'phase': pilot.phase})+'\n')
                    if not phases or phases[-1]['phase'] != pilot.phase:
                        change = {'time': observation.time, 'phase': pilot.phase}
                        phases.append(change)
                        print(json.dumps(change), flush=True)
                    next_decision = observation.tick+25
                ticks = min(5, next_decision-observation.tick,
                            max(1, math.ceil((seconds-observation.time)/game.config.dt)))
                before = observation.tick
                observation = host.step(ticks, draw=False)
                dt = (observation.tick-before)*game.config.dt
                if dt <= 0:
                    raise RuntimeError('Running simulation did not advance')
                if render:
                    game.draw(dt)
                if encoder:
                    encoder.stdin.write(game.renderer.capture_rgb())
                    frames += 1
                new_events = []
                for event in serialize(game.sim.frame().events):
                    key = (event['tick'], event['kind'], event['actor'], event['target'])
                    if key not in seen:
                        seen.add(key)
                        events.append(event)
                        new_events.append(event)
                if render and any(e['actor'] == 'player' and e['kind'] == 'missile_launched' for e in new_events):
                    captures.append(game.capture('launch'))
                if render and any(e['kind'] == 'aircraft_destroyed' for e in new_events):
                    captures.append(game.capture('aircraft_destroyed'))
                if render and visible:
                    deadline += dt/speed
                    time.sleep(max(0, min(.1, deadline-time.perf_counter())))
                    deadline = max(deadline, time.perf_counter()-.1)
        if observation.mission['result'] != 'running':
            reason = 'mission_'+observation.mission['result']
        if render:
            for _ in range(5):game.draw(0)
            captures.append(game.capture('result'))
        game.finish_sortie(reason)
        report = {'aircraft': model, 'seed': seed, 'result': observation.mission['result'],
                  'stop_reason': reason, 'sim_seconds': observation.time,
                  'kills': observation.mission['kills'], 'survived': observation.own['alive'],
                  'missiles_left': observation.missiles, 'policy_sha256': POLICY_SHA,
                  'shot_interval_seconds': shot_interval, 'weapon_counts': observation.weapon_counts,
                  'scenario_sha256': host.spec_sha, 'core_sha256': host.core_sha,
                  'map': str(game.map_path), 'map_sha256': game.scene_hash, 'observation_scope': 'own state, radar, RWR/MWS, public mission',
                  'phases': phases, 'events': events, 'captures': captures, 'logs': game.log_paths(),
                  'shader_errors': game.renderer.shader_errors() if render else None,
                  'video': str(output/'autoplay.mp4') if video else None,
                  'video_frames': frames, 'video_fps': 10, 'video_playback_speed': 1,
                  'elapsed_wall_seconds': time.perf_counter()-started}
        if encoder:
            encoder.stdin.close()
            code = encoder.wait(timeout=60)
            encoder = None
            if code:raise RuntimeError('Video encoding failed: '+str(code))
        write_json(output/'report.json', report)
        print(json.dumps({k:report[k] for k in ('aircraft','seed','result','kills','survived','stop_reason','logs')}), flush=True)
        return report
    except BaseException as error:
        game.finish_sortie('exception', repr(error))
        write_json(output/'exception.json', {'error':repr(error), 'diagnostics':host.diagnostics()})
        raise
    finally:
        if encoder:
            encoder.stdin.close()
            try:encoder.wait(timeout=30)
            except subprocess.TimeoutExpired:encoder.kill();encoder.wait()
        host.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--aircraft', choices=['F16','F22'], default='F16')
    parser.add_argument('--seed', type=int, default=101)
    parser.add_argument('--speed', type=positive, default=4.)
    parser.add_argument('--seconds', type=positive, default=600.)
    parser.add_argument('--shot-interval', type=positive, default=55., help='Minimum seconds between confirmed launches')
    maps=parser.add_mutually_exclusive_group()
    maps.add_argument('--map',type=Path,help='Explicit baked map file')
    maps.add_argument('--map-version',help='Published version ID from game/maps/catalog.json')
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--hidden', action='store_true')
    parser.add_argument('--video', action='store_true')
    parser.add_argument('--output', type=Path,
                        default=ROOT/'game/captures'/('autoplay-'+time.strftime('%Y%m%d-%H%M%S')))
    args = parser.parse_args()
    if args.headless and args.video:parser.error('--video requires rendering')
    if args.map_version:
        from .map_library import MapLibrary
        args.map=Path(MapLibrary().resolve(args.map_version)['map'])
    play(args.output, args.aircraft, args.seed, args.speed, not args.headless,
         not args.hidden, args.video, args.seconds, args.shot_interval,args.map)


if __name__ == '__main__':
    main()
