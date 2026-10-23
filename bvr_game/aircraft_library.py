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
from .presentation import ChaseCamera
from .player_profiles import PlayerProfileStore
from .player_input import PlayerInputAdapter,native_intent,unit
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
        profiles=PlayerProfileStore();profile=profiles.apply(session,native,row['id'])
        adapter=PlayerInputAdapter(profile);chase=ChaseCamera(profile['camera'])
        chase.scale=max(row['appearance']['bounds']['span'])/19
        camera_params={};free=False;zoom=False;exact=False;viewport=[960,640];aim=[480,320]
        journal.start(serialize(config),{'entry':'aircraft_library.fly','aircraft_id':row['id'],'fdm':row['fdm'],'appearance':row['appearance'],'player_flight_profile':profile})
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
                    if getattr(event,'width',0)>0:viewport=[event.width,event.height]
                    throttle = max(0, min(1, throttle + event.wheel*.05))
                    throttle = adapter.throttle(throttle,event,config.dt)
                    free=67 in held;zoom=2 in held;aim=[event.x,event.y]
                    if 80 in event.pressed:
                        session.set_paused(not frame.paused);journal.record('pause',not frame.paused,frame.tick)
                    exact=190 in event.pressed
                    if 116 in event.pressed:adapter.mode='raw_manual' if adapter.mode=='assisted' else 'assisted'
                    if 117 in event.pressed:
                        if not session.frame().paused:print('Pause with P before reloading player profiles',file=sys.stderr)
                        else:
                            candidate=PlayerProfileStore(profiles.path);profile=candidate.apply(session,native,row['id']);profiles=candidate
                            adapter.profile=profile;chase.settings=profile['camera'];journal.record('player_profile_reload',profile,frame.tick)
                    if not camera_params:
                        n,w,h=player.position;d=unit(player.velocity)
                        camera_params={'eye':[-w,h,n],'target':[-w-d[1]*1000,h+d[2]*1000,n+d[0]*1000],'fov':profile['camera']['normal_fov'],'up':[0,1,0]}
                    values=adapter.update(event,config.dt,player,camera_params,*viewport,
                        hold_direction=free or max(map(abs,chase.free))>.01)
                    intent=native_intent(native,{**values,'throttle':throttle})
                    session.submit_player(intent);journal.record('player_intent',serialize(intent),frame.tick)
            if not interactive:session.submit(command);journal.record('command',serialize(command),frame.tick)
            if exact:session.step_exact(1)
            else:session.step(1)
            journal.record('step',{'ticks':1,'exact':exact},frame.tick)
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
                if interactive:
                    eye,target,fov,up=chase.update(p,config.dt,free,aim,*viewport,zoom)
                    camera_params={'eye':eye,'target':target,'fov':fov,'up':up}
                    renderer.camera(eye,target,fov);renderer.camera_up(up)
                else:renderer.camera(eye, target, .85)
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
