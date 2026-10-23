"""Inspect, preview and fly the imported FlightGear library with typed APIs.

Examples:
  python -m bvr_game.aircraft_library list
  python -m bvr_game.aircraft_library preview FG-737-800
  python -m bvr_game.aircraft_library fly FG-A-10 --render --interactive
"""
import argparse
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import sys
import time
from .app import native, serialize, ROOT
from .presentation import curve,safe_aim,mouse_pitch,mouse_roll_rate
from .sortie_logs import SortieJournal,open_logs_directory


def catalog():
    return json.loads((ROOT / 'bvr_sim/resources/imported_aircraft_catalog.json').read_text(encoding='utf8'))['aircraft']


def renderer_for(row, visible=False, width=960, height=640):
    config = json.loads((ROOT / 'game/runtime.json').read_text(encoding='utf8'))
    visual = row['appearance']
    file = ROOT / visual['file']
    if hashlib.sha256(file.read_bytes()).hexdigest() != visual['glb_sha256']:
        raise ValueError('Imported appearance hash changed: ' + row['id'])
    sys.path.insert(0, config['renderer_module'])
    dll = os.add_dll_directory(config['renderer_module']) if os.name == 'nt' else None
    module = importlib.import_module('bvr_game_render')
    return module.Renderer(width, height, visible, config['engine_source'], config['shader_cache'],
                           {row['simulation_model']: str(file)}), dll


def preview(row, output, visible=False, properties=None):
    output.mkdir(parents=True, exist_ok=True)
    session = native.GameSession(str(output / 'preview.log'))
    config = native.GameConfig()
    config.mission = 'training'
    config.missiles = config.bombs = 0
    config.enemy_attacks = False
    renderer = None
    try:
        session.reset(config)
        session.set_paused(True)
        renderer, dll = renderer_for(row, visible)
        renderer.presentation(True)
        renderer.preview_aircraft(row['simulation_model'], properties or {}, 0.)
        bounds = row['appearance']['bounds']
        lo, hi, span = bounds['min'], bounds['max'], bounds['span']
        center = [(lo[0]+hi[0])/2, 2.1+max(0,-lo[2])+(lo[2]+hi[2])/2, (lo[1]+hi[1])/2]
        distance = max(span)*1.1
        eye = [center[0]+distance*.75, center[1]+distance*.42, center[2]+distance]
        renderer.camera(eye, center, .85)
        for _ in range(12):
            renderer.render(session.frame(), [], [])
        image = output / (row['id'] + '.png')
        renderer.capture(str(image))
        report = {'id': row['id'], 'image': str(image), 'camera': {'eye': eye, 'target': center},
                  'statistics': renderer.aircraft_statistics(), 'imports': renderer.aircraft_import_counts(),
                  'shader_errors': renderer.shader_errors(), 'preview_properties': properties or {},
                  'appearance': row['appearance']}
        (output / (row['id'] + '.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
        return report
    finally:
        if renderer:
            renderer.close()
        session.close()


def fly(row, output, seconds=10, render=False, interactive=False):
    if not row['available_for_test_flight']:
        raise ValueError(row['unavailable_reason'])
    output.mkdir(parents=True, exist_ok=True)
    session = native.GameSession(str(output / 'flight.log'))
    journal=SortieJournal(session,os.environ.get('BVR_SORTIE_LOG_ROOT',ROOT/'game/logs/sorties'))
    renderer = None
    try:
        config = native.GameConfig()
        config.library_aircraft = True
        config.player_model = row['simulation_model']
        config.mission = 'training'
        config.fdm = 'auto'
        config.missiles = config.bombs = 0
        config.enemy_attacks = False
        config.speed = max(80., min(800., row['validation'].get('initial_speed_mps', 200.)))
        config.altitude = max(1000., min(19500., row['validation'].get('initial_altitude_m', 5000.)))
        config.player_north = config.player_west = 0
        session.reset(config)
        journal.start(serialize(config),{'entry':'aircraft_library.fly','aircraft_id':row['id'],'fdm':row['fdm'],'appearance':row['appearance']})
        if render or interactive:
            renderer, dll = renderer_for(row, interactive)
            renderer.presentation(False)
        throttle, trajectory = .7, []
        ticks = 0
        while interactive or ticks < round(seconds / config.dt):
            start = time.perf_counter()
            frame = session.frame()
            player = next(e for e in frame.entities if e.uid == 'player')
            command = native.PilotCommand()
            command.heading = player.orientation[2]
            command.throttle = throttle
            if renderer:
                event = renderer.poll()
                if event.quit or 27 in event.pressed:
                    break
                if 120 in event.pressed:
                    open_logs_directory(journal.paths());continue
                if interactive:
                    held = set(event.held)
                    throttle = max(0, min(1, throttle + event.wheel*.05))
                    command.throttle = throttle
                    aim=safe_aim(event.x,event.y,960,640);dx=(aim[0]/960-.5)*2
                    command.heading -= curve(dx)
                    command.pitch = mouse_pitch(aim[1],640)
                    command.manual_pitch=87 in held or 83 in held
                    command.pitch_input=int(83 in held)-int(87 in held)
                    command.manual_roll = 65 in held or 68 in held
                    command.roll_input = int(68 in held)-int(65 in held)
                    if row['fdm']['type']=='yasim':command.roll_rate=mouse_roll_rate(aim[0],960)
                    elif not command.manual_roll and abs(dx)<=.035 and (command.manual_pitch or abs(command.pitch)>.05):
                        command.manual_roll=True;command.roll_input=0.
            session.submit(command);journal.record('command',serialize(command),frame.tick)
            session.step(1)
            journal.record('step',{'ticks':1,'exact':False},frame.tick)
            frame = session.frame()
            if ticks % 50 == 0:
                trajectory.append(serialize(frame))
            if renderer:
                p = next(e for e in frame.entities if e.uid == 'player')
                position = [-p.position[1], p.position[2], p.position[0]]
                forward = [-math.sin(p.orientation[2]), 0, math.cos(p.orientation[2])]
                distance = max(row['appearance']['bounds']['span'])*2.2
                eye = [position[i]-forward[i]*distance+(distance*.35 if i == 1 else 0) for i in range(3)]
                target = [position[i]+forward[i]*distance*.2 for i in range(3)]
                renderer.camera(eye, target, .85)
                renderer.render(frame, [], [])
            ticks += 1
            if not player.alive:
                break
            if interactive:
                time.sleep(max(0, config.dt-(time.perf_counter()-start)))
        final = serialize(session.frame())
        if renderer:
            renderer.capture(str(output / (row['id'] + '-flight.png')))
        report = {'id': row['id'], 'backend': row['fdm']['type'], 'frame': final, 'trajectory': trajectory,'logs':journal.paths(),
                  'renderer_statistics': renderer.aircraft_statistics() if renderer else None,
                  'shader_errors': renderer.shader_errors() if renderer else None}
        (output / 'flight.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        return report
    finally:
        if journal.current:journal.finish('closed' if sys.exc_info()[0] is None else 'exception',serialize(session.frame()),repr(sys.exc_info()[1]) if sys.exc_info()[0] else None)
        if renderer:
            renderer.close()
        session.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['list', 'preview', 'fly'])
    p.add_argument('id', nargs='?')
    p.add_argument('--output', type=Path, default=ROOT / 'game/captures/aircraft-library')
    p.add_argument('--seconds', type=float, default=10)
    p.add_argument('--render', action='store_true')
    p.add_argument('--interactive', action='store_true')
    args = p.parse_args()
    rows = catalog()
    if args.action == 'list':
        return print(json.dumps([{'id': r['id'], 'name': r['display_name'], 'backend': r['fdm']['type'],
                                  'test_flight_ready': r['available_for_test_flight'], 'reason': r['unavailable_reason']} for r in rows], indent=2))
    row = next((r for r in rows if r['id'] == args.id), None)
    if row is None:
        p.error('Unknown imported aircraft ID: ' + str(args.id))
    report = preview(row, args.output, args.interactive) if args.action == 'preview' else fly(row, args.output, args.seconds, args.render, args.interactive)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
