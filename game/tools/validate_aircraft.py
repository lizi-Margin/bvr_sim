"""Validate imported FDMs directly, without GameSession or a renderer.

Each source model runs in a separate process so invalid third-party data cannot
hide failures in later aircraft. Reports include actual trajectories and errors.
"""
import argparse
import json
import math
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def worker(name, seconds, output):
    sys.path.insert(0, str(ROOT / 'bvr_sim/build/Release'))
    import bvr_sim_cpp as native
    folder = ROOT / 'bvr_sim/resources/aircraft' / name
    tree = ET.parse(folder / 'fdm.xml').getroot()
    data = {'id': name, 'backend': 'yasim' if tree.tag == 'airplane' else 'jsbsim'}
    try:
        speed, altitude = 200., 5000.
        altitude_reason = 'Host airborne validation condition'
        if tree.tag == 'airplane':
            cruise = tree.find('cruise')
            if cruise is not None:
                speed = float(cruise.get('speed-kt', cruise.get('speed', '389')).split()[0]) * .514444
                if 'speed-kmh' in cruise.attrib:
                    speed = float(cruise.get('speed-kmh')) / 3.6
                altitude = float(cruise.get('alt-ft',cruise.get('alt','16404')).split()[0]) * .3048
                if 'alt-m' in cruise.attrib: altitude=float(cruise.get('alt-m').split()[0])
            # YASim cruise is a solver reference, sometimes at sea level. It
            # does not specify a safe spawn height above the host ground.
            if altitude < 1000.:
                altitude = 5000.
                altitude_reason = 'Source cruise altitude below 1000 m; use airborne 5000 m'
            else:
                altitude_reason = 'Source cruise solver altitude'
            fdm = native.YASimFDM(.02, str(folder / 'fdm.xml'))
        else:
            fdm = native.JSBSimFDM(.02, name)
        fdm.reset([0, 0, altitude], [speed, 0, 0])
        trace = [{'time': 0, 'position': fdm.position, 'velocity': fdm.velocity, 'rpy': fdm.rpy}]
        for i in range(round(seconds / .02)):
            fdm.advance(0, 0, .7)
            if (i + 1) % 50 == 0 or fdm.terminated:
                trace.append({'time': (i + 1) * .02, 'position': fdm.position, 'velocity': fdm.velocity, 'rpy': fdm.rpy})
            if fdm.terminated:
                break
        finite = all(math.isfinite(x) for p in trace for k in ['position', 'velocity', 'rpy'] for x in p[k])
        data.update(status='passed' if finite and not fdm.terminated else 'unstable',
                    initial_speed_mps=speed, initial_altitude_m=altitude,
                    initial_altitude_reason=altitude_reason, trace=trace,
                    final_terminated=fdm.terminated, visual_property_count=len(fdm.visual_properties()))
    except Exception as exc:
        data.update(status='error', error=type(exc).__name__ + ': ' + str(exc))
    output.write_text(json.dumps(data, indent=2), encoding='utf8')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--worker')
    p.add_argument('--only', nargs='*', default=[])
    p.add_argument('--seconds', type=float, default=10)
    p.add_argument('--output', type=Path, default=ROOT / 'runs/aircraft-import/fdm-validation.json')
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.worker:
        return worker(args.worker, args.seconds, args.output)
    plan = json.loads((ROOT / 'game/aircraft_import.json').read_text(encoding='utf8'))
    results = []
    for item in plan['candidates']:
        if item['selection'] != 'selected' or (args.only and item['id'] not in args.only):
            continue
        out = args.output.parent / 'fdm' / (item['id'] + '.json')
        out.parent.mkdir(parents=True, exist_ok=True)
        log = out.with_suffix('.log')
        with log.open('w', encoding='utf8') as stream:
            try:
                code = subprocess.run([sys.executable, str(Path(__file__).resolve()), '--worker', item['id'],
                                       '--seconds', str(args.seconds), '--output', str(out)],
                                      stdout=stream, stderr=subprocess.STDOUT, timeout=90).returncode
            except subprocess.TimeoutExpired:
                code = 'timeout'
        result = json.loads(out.read_text()) if code == 0 and out.exists() else {'id': item['id'], 'status': 'process_error', 'returncode': code}
        results.append(result)
        args.output.write_text(json.dumps({'results': results}, indent=2), encoding='utf8')
        print(result['id'], result['status'], result.get('error', ''), flush=True)


if __name__ == '__main__':
    main()
