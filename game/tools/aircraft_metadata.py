"""Measure GLB geometry and generate per-engine attachment candidates.

Named nozzle geometry is preferred. Source FDM positions projected onto nearby
aft geometry are explicit estimates, with provenance, for manual visual review.
"""
from pathlib import Path
import json
import struct
import xml.etree.ElementTree as ET
import numpy as np

ROOT = Path(__file__).resolve().parents[2]


def geometry(path):
    raw = path.read_bytes()
    size = struct.unpack_from('<I', raw, 12)[0]
    doc = json.loads(raw[20:20 + size])
    start = 20 + size
    binary = raw[start + 8:]
    result = []
    def positions(index):
        a = doc['accessors'][index]
        v = doc['bufferViews'][a['bufferView']]
        if a['componentType'] != 5126 or a['type'] != 'VEC3':
            raise ValueError('Unsupported GLB POSITION encoding')
        return np.ndarray((a['count'], 3), dtype='<f4', buffer=binary,
                          offset=v.get('byteOffset', 0) + a.get('byteOffset', 0),
                          strides=(v.get('byteStride', 12), 4)).astype(np.float64)
    def visit(index, parent):
        n = doc['nodes'][index]
        if 'matrix' in n:
            matrix = np.array(n['matrix']).reshape(4, 4).T
        else:
            x, y, z, w = n.get('rotation', [0, 0, 0, 1])
            rot = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                            [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                            [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
            matrix = np.eye(4)
            matrix[:3, :3] = rot @ np.diag(n.get('scale', [1, 1, 1]))
            matrix[:3, 3] = n.get('translation', [0, 0, 0])
        world = parent @ matrix
        if 'mesh' in n:
            pieces = []
            for p in doc['meshes'][n['mesh']]['primitives']:
                xyz = positions(p['attributes']['POSITION'])
                xyz = xyz @ world[:3, :3].T + world[:3, 3]
                xyz[:, 2] *= -1  # Wicked's glTF handedness conversion
                pieces.append(xyz)
            if pieces:
                result.append((n.get('name', str(index)), np.concatenate(pieces)))
        for child in n.get('children', []):
            visit(child, world)
    for node in doc['scenes'][doc.get('scene', 0)]['nodes']:
        visit(node, np.eye(4))
    return result


def engine_positions(folder):
    root = ET.parse(folder / 'fdm.xml').getroot()
    if root.tag == 'airplane':
        return [(-float(j.get('y', '0')), float(j.get('z', '0')), float(j.get('x', '0'))) for j in root.findall('jet')]
    propulsion = root.find('propulsion')
    if propulsion is not None and propulsion.get('file'):
        name = propulsion.get('file')
        if not name.endswith('.xml'):
            name += '.xml'
        file = folder / name
        if file.exists():
            propulsion = ET.parse(file).getroot()
    result = []
    if propulsion is not None:
        for engine in propulsion.findall('engine'):
            location = engine.find('thruster/location')
            if location is None:
                location = engine.find('location')
            if location is None:
                continue
            factor = .0254 if location.get('unit', 'IN') == 'IN' else .3048 if location.get('unit') == 'FT' else 1
            x, y, z = [float(location.findtext(a, '0')) * factor for a in ['x', 'y', 'z']]
            result.append((y, z, -x))
    return result


def update(name):
    folder = ROOT / 'game/assets/registered' / name
    path = folder / 'manifest.json'
    if not path.exists():
        return
    m = json.loads(path.read_text(encoding='utf8'))
    parts = geometry(folder / m['file'])
    points = np.concatenate([p for _, p in parts])
    lo, hi = points.min(axis=0), points.max(axis=0)
    m['bounds_runtime'] = {'min': lo.tolist(), 'max': hi.tolist(), 'span': (hi-lo).tolist()}
    # Frame the exported surface geometry, excluding editor helper meshes with
    # no exported triangles. Blender and runtime differ only by axis order here.
    m.setdefault('source_reported_bounds_blender', m['bounds_blender'])
    b_lo, b_hi = lo[[0, 2, 1]], hi[[0, 2, 1]]
    m['bounds_blender'] = {'min': b_lo.tolist(), 'max': b_hi.tolist(), 'span': (b_hi-b_lo).tolist()}
    engines = engine_positions(ROOT / 'bvr_sim/resources/aircraft' / name)
    attachments = list(m.get('exhausts', []))
    if len(attachments) != len(engines) and engines:
        # FDM origin/structural coordinates can differ from the visual origin.
        # Preserve source lateral placement where plausible and project to the
        # local aft geometry; never describe this estimate as an exact nozzle.
        attachments = []
        for index, engine in enumerate(engines):
            x, y, z = engine
            if not lo[0] <= x <= hi[0]:
                x = float((lo[0] + hi[0])/2)
            if not lo[1] <= y <= hi[1]:
                y = float((lo[1] + hi[1])/2)
            radius = max(.12, min(.7, float((hi[0]-lo[0])*.025)))
            mask = (abs(points[:, 0]-x) < max(radius*1.5, .6)) & (abs(points[:, 1]-y) < max(radius*1.5, .6))
            subset = points[mask]
            aft = float(np.quantile(subset[:, 2], .01)) if len(subset) else float(lo[2])
            attachments.append({'engine_index': index, 'position': [x, y, aft], 'radius_m': radius,
                                'method': 'FDM engine position projected to nearby aft mesh; approximate attachment',
                                'source_engine_runtime': list(engine), 'requires_visual_review': True})
        m['exhaust_status'] = 'source engine count; geometry-projected approximate attachments'
    m['exhausts'] = attachments
    m['engine_count'] = len(engines)
    m['geometry_vertices_measured'] = len(points)
    path.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    return {'id': name, 'engines': len(engines), 'attachments': len(attachments), 'span': (hi-lo).tolist()}


if __name__ == '__main__':
    plan = json.loads((ROOT / 'game/aircraft_import.json').read_text(encoding='utf8'))
    rows = [update(a['id']) for a in plan['candidates'] if a['selection'] == 'selected']
    print(json.dumps(rows, indent=2))
