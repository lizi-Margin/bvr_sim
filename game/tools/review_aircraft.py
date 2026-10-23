"""Render every imported GLB through the actual Wicked/DX12 aircraft path.

Workers bound GPU resource lifetime. Contact sheets are generated from captured
GPU frames; inspect them before claiming visual acceptance.
"""
import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def worker(rows, output):
    from bvr_game.app import native
    config = json.loads((ROOT / 'game/runtime.json').read_text(encoding='utf8'))
    sys.path.insert(0, config['renderer_module'])
    dll = os.add_dll_directory(config['renderer_module']) if os.name == 'nt' else None
    module = importlib.import_module('bvr_game_render')
    models = {r['id']: str(ROOT / r['appearance']['file']) for r in rows}
    renderer = module.Renderer(900, 600, False, config['engine_source'], config['shader_cache'], models)
    session = native.GameSession(str(output / 'review-session.log'))
    setup = native.GameConfig()
    setup.mission = 'training'
    setup.missiles = setup.bombs = 0
    setup.enemy_attacks = False
    reports = []
    try:
        session.reset(setup)
        session.set_paused(True)
        renderer.presentation(True)
        for row in rows:
            name = row['id']
            renderer.preview_aircraft(name, {}, 0.)
            b = row['appearance']['bounds']
            lo, hi = b['min'], b['max']
            center = [(lo[0]+hi[0])/2, 2.1+max(0,-lo[2])+(lo[2]+hi[2])/2, (lo[1]+hi[1])/2]
            distance = max(b['span'])*1.1
            eye = [center[0]+distance*.75, center[1]+distance*.42, center[2]+distance]
            renderer.camera(eye, center, .85)
            text = module.HudText()
            text.x = text.y = 15
            text.size = 22
            text.text = name
            text.color = 0xffeeeeee
            for _ in range(10):
                renderer.render(session.frame(), [text], [])
            image = output / (name + '.png')
            renderer.capture(str(image))
            report = {'id': name, 'image': str(image), 'statistics': renderer.aircraft_statistics(),
                      'import_counts': renderer.aircraft_import_counts(), 'shader_errors': renderer.shader_errors()}
            reports.append(report)
            (output / (name + '.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
            print(name, renderer.shader_errors(), flush=True)
        assert renderer.shader_errors() == 0
        assert all(n == 1 for n in renderer.aircraft_import_counts().values())
        return reports
    finally:
        renderer.close()
        session.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker', nargs='*')
    p.add_argument('--only', nargs='*')
    p.add_argument('--output', type=Path, default=ROOT / 'game/captures/aircraft-library/gallery')
    args = p.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = json.loads((ROOT / 'bvr_sim/resources/imported_aircraft_catalog.json').read_text(encoding='utf8'))['aircraft']
    rows = [r for r in rows if 'file' in r['appearance']]
    if args.worker is not None:
        return worker([r for r in rows if r['id'] in args.worker], args.output)
    if args.only:
        rows = [r for r in rows if r['id'] in args.only]
    from PIL import Image, ImageDraw
    for index in range(0, len(rows), 9):
        group = rows[index:index+9]
        log = args.output / ('batch-' + str(index//9) + '.log')
        with log.open('w', encoding='utf8') as stream:
            code = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--output', str(args.output),
                                   '--worker', *[r['id'] for r in group]], stdout=stream, stderr=subprocess.STDOUT).returncode
        if code:
            raise RuntimeError('GPU review failed; see ' + str(log))
        sheet = Image.new('RGB', (1200, 840), '#22303c')
        for tile, row in enumerate(group):
            image = Image.open(args.output / (row['id'] + '.png')).convert('RGB')
            image.thumbnail((400, 267))
            x, y = tile%3*400, tile//3*280
            sheet.paste(image, (x, y))
            ImageDraw.Draw(sheet).text((x+5, y+262), row['id'], fill='white')
        sheet.save(args.output / f'contact-{index//9:02d}.jpg', quality=92)
        print('REVIEWED', index, len(group), flush=True)


if __name__ == '__main__':
    main()
