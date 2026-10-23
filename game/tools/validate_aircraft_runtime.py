"""Check imported-aircraft rendered/headless parity, controls and cache lifetime."""
import argparse
import json
import math
from pathlib import Path
import sys
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from bvr_game.aircraft_library import catalog, fly, renderer_for
from bvr_game.app import native


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--only', nargs='*', default=['FG-A-10', 'FG-SU-37', 'FG-737-800'])
    p.add_argument('--output', type=Path, default=ROOT/'runs/aircraft-import/runtime-validation')
    p.add_argument('--worker', choices=['flight', 'cache'])
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = {r['id']: r for r in catalog()}
    if not args.worker:
        # Wicked owns process-wide GPU state. One renderer lifetime per worker
        # avoids reinitializing the engine's global device after shutdown.
        for name in args.only:
            subprocess.run([sys.executable, __file__, '--worker', 'flight', '--only', name,
                            '--output', str(args.output)], check=True, timeout=120)
        subprocess.run([sys.executable, __file__, '--worker', 'cache', '--output', str(args.output)],
                       check=True, timeout=120)
        report = json.loads((args.output/'report.json').read_text(encoding='utf8'))
        report['flights'] = [json.loads((args.output/(name+'-parity.json')).read_text(encoding='utf8')) for name in args.only]
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        return print(json.dumps(report, indent=2))
    reports = []
    for name in args.only if args.worker == 'flight' else []:
        row = rows[name]
        headless = fly(row, args.output/name/'headless', seconds=2.)
        rendered = fly(row, args.output/name/'rendered', seconds=2., render=True)
        assert headless['frame'] == rendered['frame'], name + ': final frame differs'
        assert headless['trajectory'] == rendered['trajectory'], name + ': trajectory differs'
        assert rendered['shader_errors'] == 0
        player = next(e for e in rendered['frame']['entities'] if e['uid'] == 'player')
        assert player['alive']
        reports.append({'id': name, 'backend': row['fdm']['type'], 'exact_parity': True,
                        'statistics': rendered['renderer_statistics']})
    if args.worker == 'flight':
        (args.output/(name+'-parity.json')).write_text(json.dumps(reports[0], indent=2), encoding='utf8')
        return

    row = rows['FG-A-10']
    session = native.GameSession(str(args.output/'cache-session.log'))
    config = native.GameConfig()
    config.mission = 'training'
    config.missiles = config.bombs = 0
    config.enemy_attacks = False
    renderer = None
    try:
        session.reset(config)
        session.set_paused(True)
        renderer, dll = renderer_for(row)
        renderer.presentation(True)
        renderer.camera([22, 12, 26], [0, 4, 0], .85)
        samples = []
        for repeat in range(5):
            fdm = native.YASimFDM(.02, str(ROOT/'bvr_sim/resources/aircraft/FG-A-10/fdm.xml'))
            fdm.reset([0, 0, 5000], [200, 0, 0])
            for _ in range(30):
                fdm.step(aileron=-.5 if repeat in (0, 3) else .5, elevator=0., throttle=.7)
            assert not fdm.terminated
            renderer.preview_aircraft(row['id'], fdm.visual_properties(), .95 if repeat == 2 else 0.)
            for _ in range(8):
                renderer.render(session.frame(), [], [])
            renderer.capture(str(args.output/f'control-pose-{repeat}.png'))
            stats = renderer.aircraft_statistics()
            assert stats['property_updates'] > 0
            samples.append(stats)
        resources = [(s['mesh_resources'], s['material_resources']) for s in samples]
        assert len(set(resources)) == 1, resources
        assert list(renderer.aircraft_import_counts().values()) == [1]
        from PIL import Image, ImageChops
        difference = ImageChops.difference(Image.open(args.output/'control-pose-0.png').convert('RGB'),
                                          Image.open(args.output/'control-pose-1.png').convert('RGB'))
        assert difference.getbbox(), 'Opposite control-surface poses are identical'
        glow_difference = ImageChops.difference(Image.open(args.output/'control-pose-1.png').convert('RGB'),
                                               Image.open(args.output/'control-pose-2.png').convert('RGB'))
        assert glow_difference.getbbox(), 'Idle/full engine glow poses are identical'
        report = {'flights': reports, 'cache_samples': samples,
                  'import_counts': renderer.aircraft_import_counts(),
                  'shader_errors': renderer.shader_errors(), 'control_pose_pixels_changed': True,
                  'engine_glow_pixels_changed': True}
        (args.output/'report.json').write_text(json.dumps(report, indent=2), encoding='utf8')
        print(json.dumps(report, indent=2))
    finally:
        if renderer:
            renderer.close()
        session.close()


if __name__ == '__main__':
    main()
