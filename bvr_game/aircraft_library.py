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
from .app import native, serialize, ROOT,FlightGame,DEFAULT_VISUAL_PROFILE,DEFAULT_WORLD_MAP
from .player_profiles import PlayerProfileStore
from .sortie_logs import SortieJournal,open_logs_directory


def catalog():
    return json.loads((ROOT / 'bvr_sim/resources/imported_aircraft_catalog.json').read_text(encoding='utf8'))['aircraft']


def renderer_for(row, visible=False, width=960, height=640,visual_profile=DEFAULT_VISUAL_PROFILE):
    config = json.loads((ROOT / 'game/runtime.json').read_text(encoding='utf8'))
    visual = row['appearance']
    file = ROOT / visual['file']
    if hashlib.sha256(file.read_bytes()).hexdigest() != visual['glb_sha256']:
        raise ValueError('Imported appearance hash changed: ' + row['id'])
    sys.path.insert(0, config['renderer_module'])
    dll = os.add_dll_directory(config['renderer_module']) if os.name == 'nt' else None
    module = importlib.import_module('bvr_game_render')
    args=[width,height,visible,config['engine_source'],config['shader_cache'],{row['simulation_model']:str(file)}]
    if getattr(module,'VISUAL_BETA',False) and Path(visual_profile).is_file():args.append(str(visual_profile))
    return module.Renderer(*args), dll


def player_test_flight(row,output,*,render=True,visible=True,width=1920,height=1080,
                       map_path=DEFAULT_WORLD_MAP,visual_profile=DEFAULT_VISUAL_PROFILE,start=True):
    """Prepare the ordinary client as an unarmed standalone player flight."""
    game=FlightGame(render=render,visible=visible,width=width,height=height,map_path=map_path,
        output=output,visual_profile=visual_profile)
    try:
        game.entry_point='aircraft_library.fly';game.select_aircraft(row['id'])
        game.config.mission='training';game.config.enemy_attacks=False
        game.config.missiles=game.config.bombs=0;game.quality='high';game.weapon='UNARMED'
        if game.renderer:game.renderer.set_quality('high')
        if start:
            altitude=max(1000.,min(19500.,row['validation'].get('initial_altitude_m',5000.)))
            altitude=max(altitude,game.sim.terrain().height(0,0)+500)
            speed=max(80.,min(800.,row['validation'].get('initial_speed_mps',250.)))
            game.start(start_position=[0,0,altitude],initial_speed=speed)
        return game
    except BaseException:
        game.close();raise


def fly_interactive(row,output,*,map_path=DEFAULT_WORLD_MAP,visual_profile=DEFAULT_VISUAL_PROFILE,
                    width=1920,height=1080,event_source=None,frame_dt=None,visible=True,max_client_frames=None):
    """Use the game's input/tick/camera/HUD path; optional typed events aid Agents."""
    if frame_dt is not None and (not math.isfinite(frame_dt) or frame_dt<=0 or frame_dt>.1):
        raise ValueError('Fixed client frame time must be in(0,0.1]seconds')
    if max_client_frames is not None and (not isinstance(max_client_frames,int) or max_client_frames<=0):
        raise ValueError('Maximum client frames must be a positive integer')
    game=player_test_flight(row,output,map_path=map_path,visual_profile=visual_profile,
        width=width,height=height,visible=visible)
    game.interactive=True;last=time.perf_counter();accumulator=0.;trajectory=[];last_sample=-1;index=0;processed=0
    try:
        while True:
            if max_client_frames is not None and processed>=max_client_frames:break
            now=time.perf_counter();dt=frame_dt if frame_dt is not None else min(now-last,.1);last=now
            event=event_source(game,index) if event_source else game.renderer.poll();index+=1
            # Standalone Escape closes the window; the game keeps its hangar flow.
            if event.quit or 27 in event.pressed:break
            running,accumulator=game.run_client_frame(event,dt,accumulator)
            if not running:break
            processed+=1
            frame=game.sim.frame()
            if frame.tick//50!=last_sample:trajectory.append(serialize(frame));last_sample=frame.tick//50
        frame=serialize(game.sim.frame());image=game.capture(row['id']+'-flight')
        # Retain the former standalone PNG name as well as normal capture metadata.
        import shutil
        shutil.copy2(image,Path(output)/(row['id']+'-flight.png'))
        report={'id':row['id'],'backend':row['fdm']['type'],'frame':frame,'trajectory':trajectory,'logs':game.log_paths(),
            'renderer_statistics':game.renderer.aircraft_statistics(),'shader_errors':game.renderer.shader_errors(),
            'capture':image,'entry':'aircraft_library.fly','player_flight_profile':game.player_profile,
            'map':str(game.map_path),'map_sha256':game.scene_hash,'visual_profile':game.visual_profile,
            'resolution':[game.width,game.height],'quality':game.quality,'client_frames':processed}
        (Path(output)/'flight.json').write_text(json.dumps(report,indent=2),encoding='utf8')
        return report
    except BaseException as error:
        game.finish_sortie('exception',repr(error));raise
    finally:game.close()


def preview(row, output, visible=False, properties=None,*,visual_profile=DEFAULT_VISUAL_PROFILE,width=960,height=640):
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
        renderer, dll = renderer_for(row, visible,width,height,visual_profile)
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


def fly(row, output, seconds=10, render=False, interactive=False,**player_options):
    if interactive:return fly_interactive(row,output,**player_options)
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
        journal.start(serialize(config),{'entry':'aircraft_library.fly','aircraft_id':row['id'],'fdm':row['fdm'],'appearance':row['appearance'],'player_flight_profile':profile})
        if render:
            renderer, dll = renderer_for(row,False,player_options.get('width',960),player_options.get('height',640),
                player_options.get('visual_profile',DEFAULT_VISUAL_PROFILE))
            renderer.presentation(False)
        throttle, trajectory = .7, []
        ticks = 0
        while ticks < round(seconds / config.dt):
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
            session.submit(command);journal.record('command',serialize(command),frame.tick)
            session.step(1);journal.record('step',{'ticks':1,'exact':False},frame.tick)
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
    p.add_argument('--hidden',action='store_true',help='Keep the native preview/test-flight window hidden')
    p.add_argument('--max-client-frames',type=int,help='Bound an interactive fly run for Agent/CLI inspection; default runs until Escape/close')
    p.add_argument('--map',type=Path,default=DEFAULT_WORLD_MAP,help='World map for interactive player test flight; noninteractive fly retains its legacy diagnostic environment')
    p.add_argument('--visual-profile',type=Path,default=DEFAULT_VISUAL_PROFILE)
    p.add_argument('--width',type=int,default=1920);p.add_argument('--height',type=int,default=1080)
    args = p.parse_args()
    if not args.interactive and args.map!=DEFAULT_WORLD_MAP:p.error('--map requires --interactive')
    if args.max_client_frames is not None and (args.action!='fly' or not args.interactive or args.max_client_frames<=0):p.error('--max-client-frames requires interactive fly and a positive count')
    rows = catalog()
    if args.action == 'list':
        return print(json.dumps([{'id': r['id'], 'name': r['display_name'], 'backend': r['fdm']['type'],
                                  'test_flight_ready': r['available_for_test_flight'], 'reason': r['unavailable_reason']} for r in rows], indent=2))
    row = next((r for r in rows if r['id'] == args.id), None)
    if row is None and args.action=='fly' and args.interactive:
        from .aircraft import aircraft
        try:row=aircraft(args.id,require_available=True)
        except ValueError as error:p.error(str(error))
    if row is None:
        p.error('Unknown imported aircraft ID: ' + str(args.id))
    report = preview(row,args.output,args.interactive and not args.hidden,visual_profile=args.visual_profile,width=args.width,height=args.height) if args.action == 'preview' else fly(row, args.output, args.seconds, args.render, args.interactive,
        map_path=args.map,visual_profile=args.visual_profile,width=args.width,height=args.height,visible=not args.hidden,max_client_frames=args.max_client_frames)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
