"""Publish a reviewable import-library index from actual files and validation.

This library is separate from the five aircraft approved for ordinary missions.
Imported civil/prototype aircraft have no invented radar or weapon loadouts.
"""
from pathlib import Path
import hashlib
import json
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build():
    plan = json.loads((ROOT / 'game/aircraft_import.json').read_text(encoding='utf8'))
    validations = {}
    for file in ['fdm-validation.json', 'fdm-retry.json', 'fdm-final.json',
                 'fdm-round7.json', 'fdm-compat-retry.json', 'fdm-airborne-retry.json',
                 'fdm-current.json']:
        path = ROOT / 'runs/aircraft-import' / file
        if path.exists():
            for row in json.loads(path.read_text(encoding='utf8'))['results']:
                validations[row['id']] = row
    rows = []
    for item in plan['candidates']:
        if item['selection'] != 'selected':
            continue
        name = item['id']
        sim = ROOT / 'bvr_sim/resources/aircraft' / name
        asset = ROOT / 'game/assets/registered' / name
        metadata = asset / 'manifest.json'
        fdm = sim / 'fdm.xml'
        problems = []
        visual = {'asset_id': name}
        validation = validations.get(name, {'status': 'not_run'})
        if not metadata.exists():
            problems.append('Mesh conversion incomplete')
        else:
            manifest = json.loads(metadata.read_text(encoding='utf8'))
            glb = asset / manifest['file']
            if not glb.exists() or sha(glb) != manifest['glb_sha256']:
                problems.append('GLB missing or hash mismatch')
            visual.update(file=str(glb.relative_to(ROOT)), manifest=str(metadata.relative_to(ROOT)),
                          glb_sha256=manifest['glb_sha256'], bounds=manifest['bounds_blender'],
                          units=manifest['units'], runtime_axes=manifest['runtime_axes'],
                          animation_count=len(manifest.get('animations', [])), exhausts=manifest.get('exhausts', []),
                          missing_textures=manifest.get('missing_textures', []),
                          skipped_source_features=manifest.get('skipped', []))
        if validation['status'] != 'passed':
            problems.append('Standalone FDM: ' + validation['status'] + ': ' + validation.get('error', 'requires tuning'))
        backend = 'yasim' if ET.parse(fdm).getroot().tag == 'airplane' else 'jsbsim'
        row = {'id': name, 'display_name': item['selected_variant']['name'], 'simulation_model': name,
               'fdm': {'type': backend, 'file': str(fdm.relative_to(ROOT / 'bvr_sim/resources')), 'sha256': sha(fdm)},
               'appearance': visual, 'radar': {'profile': 'none'}, 'legal_loadouts': [{'id': 'clean', 'missiles': 0, 'bombs': 0}],
               'default_loadout': 'clean', 'max_missiles': 0, 'max_bombs': 0,
               'available_for_test_flight': not problems, 'unavailable_reason': '; '.join(problems),
               'validation': validation, 'source_archive': item['archive'], 'selection_reason': item['reason'],
               'host_limitations': ['Source Nasal/electrical/hydraulic/FCS scripts are not executed.',
                                    'Generic host assist/control aliases require per-aircraft tuning.',
                                    'Only tested conditions are validated; this is not a certified flight envelope.']}
        rows.append(row)
    target = ROOT / 'bvr_sim/resources/imported_aircraft_catalog.json'
    target.write_text(json.dumps({'schema_version': 1, 'ordinary_mission_catalog': 'aircraft_catalog.json',
                                  'aircraft': rows}, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'catalog': str(target), 'aircraft': len(rows),
                      'meshes': sum('file' in r['appearance'] for r in rows),
                      'test_flight_ready': sum(r['available_for_test_flight'] for r in rows)}, indent=2))
    return rows


if __name__ == '__main__':
    build()
