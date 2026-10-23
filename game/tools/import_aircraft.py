"""Reproducible FlightGear ZIP inventory and batch importer (no FlightGear runtime).

scan preserves every candidate and the family selection reasons. prepare extracts
selected packages, resolved FDM XML, model graphs, animation XML and provenance.
convert runs the Blender converter and registers only successful GLBs.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import posixpath
import re
import subprocess
import sys
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PLAN = ROOT / 'game/aircraft_import.json'
FAMILIES = [
    ['737-800', '737NG', '737-100', '737-200', '737-300'],
    ['747-8i', '747-400', '747-200', '747'],
    ['dc8-73', 'dc8-63'], ['DC-10-30', 'DC-10'],
    ['MirageIII', 'MirageIIIE'], ['mirage2000', 'Mirage-2000'],
    ['harrier', 'Harrier-GR3', 'Harrier-GR1'], ['Jaguar', 'Jaguar-GR1'],
    ['Lockheed-SR71', 'SR71-BlackBird'], ['Lockheed-NF104A', 'Lockheed-NF104'],
    ['Northrop-T38-Talon', 'T38'], ['G91-R', 'Fiat-G91'],
    ['ME-262', 'ME-262HGIII'], ['Lockheed-P-2-Neptune', 'Loockheed-P-2-Neptune'],
    ['Nord-2502', 'Noratlas'], ['tu154b', 'tu154'], ['Citation-Bravo', 'Citation'],
]
# Jet engines also occur in template files inside cars, rotorcraft and rockets.
EXCLUDE = {'4cv', 'jeep', 'pushback', 'snowplow', 'R22', 'Curtiss-Wright-X-19',
           'an24b', 'MQ-9', 'OV10', 'PC-21', 'PC-9M', 'SkyCar', 'Bell-X1', 'SpaceShip-One', 'jetman', 'SpaceShuttle', 'shuttle'}
IDS = {'Lockheed-Martin-FA-22A-Raptor': 'FG-F22', 'f16': 'FG-F16',
       'F-15': 'FG-F15C', 'f18': 'FG-F18-CAF', 'McDonnell-F-4-Phantom': 'FG-F4'}
PREFERRED_SETS = {'T-4': 'T-4/T-4-yasim-set.xml', 'T-50': 'T-50/T-50-yasim-set.xml'}


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def merge(base, override):
    """PropertyList include semantics: children keyed by (tag,n), last value wins."""
    for node in override:
        key = (node.tag, node.get('n', '0'))
        old = next((c for c in base if (c.tag, c.get('n', '0')) == key), None)
        if old is None:
            base.append(copy.deepcopy(node))
        elif len(node):
            merge(old, node)
        else:
            old.text = node.text
            old.attrib.update(node.attrib)
    return base


def xml_fragment(node):
    node = copy.deepcopy(node)
    node.tail = None
    return ET.tostring(node, encoding="unicode")


def property_defaults(tree):
    values = {}
    def walk(node, path=''):
        for child in node:
            name = child.tag + ('[' + child.get('n') + ']' if child.get('n', '0') != '0' else '')
            key = path + '/' + name if path else name
            if len(child):
                walk(child, key)
            elif child.text and child.text.strip():
                text = child.text.strip()
                if text.casefold() in {'true', 'false'}:
                    values[key] = text.casefold() == 'true'
                else:
                    try:
                        values[key] = float(text)
                    except ValueError:
                        values[key] = text
    walk(tree)
    return values


def normalize_yasim(tree):
    repairs = []
    for surface in tree.iter():
        wired = {n.get('control') for n in surface.findall('control-input')}
        for node in list(surface.findall('control-speed')):
            if node.get('control') == 'INCIDENCE' and 'INCIDENCE' not in wired:
                # An unwired rate limiter creates an always-zero output in
                # upstream ControlMap, overwriting the solver's tail trim.
                # Remove only that orphan controller; retain aerodynamic data.
                surface.remove(node)
                repairs.append('Removed unwired INCIDENCE control-speed on ' + surface.tag +
                               ': zero-input output prevented solver tail trim; aerodynamic parameters unchanged')
    return repairs


def prepare_jsbsim(pkg, variant, out):
    """Bundle only transitive JSBSim dependencies; retain source XML separately."""
    todo, seen, missing, records = [variant['fdm']], set(), [], []
    declared = {}
    external = set()
    while todo:
        name = todo.pop()
        if name in seen:
            continue
        seen.add(name)
        tree = pkg.xml(name)
        for node in tree.iter():
            if node.tag == 'property' and node.text and node.get('value'):
                try: declared[node.text.strip()] = float(node.get('value'))
                except ValueError: pass
            if node.tag in {'property','p'} and node.text and not len(node):
                value = node.text.strip()
                # Only property references in equations are host inputs. Named
                # declarations with values are loaded by JSBSim itself.
                if re.fullmatch(r'-?/?[A-Za-z_][\w./\[\]-]*',value):
                    external.add(value.lstrip('-'))
            if node.tag in {'input','output','test','independentVar','independentVar2D'}:
                text=' '.join(node.itertext())
                external.update(re.findall(r'/?[A-Za-z_][\w.-]*(?:\[\d+\])?(?:/[A-Za-z_][\w.-]*(?:\[\d+\])?)*', text))
            for key,value in node.attrib.items():
                if key == 'value' and ('/' in value or value == 'sim-time-sec'):
                    external.add(value.lstrip('-'))
            if 'file' not in node.attrib:
                continue
            ref = node.get('file')
            if not ref:
                continue
            filename = ref if ref.lower().endswith('.xml') else ref + '.xml'
            try:
                dep = pkg.resolve(filename, name)
            except FileNotFoundError:
                choices = [n for n in pkg.names.values() if n.rsplit('/', 1)[-1].casefold() == filename.rsplit('/', 1)[-1].casefold()]
                dep = sorted(choices, key=lambda n: ('/Models/' in n, n))[0] if choices else None
            group = 'Engines' if node.tag in {'engine', 'thruster'} else 'Systems'
            if dep:
                dependency_tree=pkg.xml(dep)
                label_repairs=[]
                for element in dependency_tree.iter():
                    label=element.get('name','')
                    if ' ' in label and ('[' in label or ']' in label):
                        repaired=label.replace('[','_').replace(']','')
                        element.set('name',repaired)
                        label_repairs.append({'original':label,'normalized':repaired})
                content=ET.tostring(dependency_tree,encoding='utf-8',xml_declaration=True)
                todo.append(dep)
            else:
                shared = ROOT / 'bvr_sim/resources/jsbsim/engine' / filename
                if not shared.is_file():
                    missing.append({'from': name, 'ref': ref})
                    continue
                content = shared.read_bytes()
            for target in [out / filename, out / group / Path(filename).name]:
                if not target.resolve().is_relative_to(out.resolve()):
                    raise ValueError('Unsafe dependency path: ' + filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
            records.append({'from': name, 'reference': ref, 'source': dep or 'core shared engine', 'label_repairs': label_repairs if dep else []})
    dump(out / 'dependencies.json', {'files': records, 'missing': missing})
    dump(out / 'jsbsim_initial_properties.json', declared)
    return sorted(s for s in external if re.fullmatch(r'/?[A-Za-z_][\w.-]*(?:\[\d+\])?(?:/[A-Za-z_][\w.-]*(?:\[\d+\])?)*',s))


class Package:
    def __init__(self, path):
        self.path = path
        self.zip = zipfile.ZipFile(path)
        self.names = {n.casefold(): n for n in self.zip.namelist()}

    def resolve(self, ref, parent=''):
        ref = ref.replace('\\', '/').lstrip('/')
        if ref.startswith('Aircraft/'):
            ref = ref[len('Aircraft/'):]
        candidates = [posixpath.normpath(posixpath.join(posixpath.dirname(parent), ref)),
                      ref, self.path.stem + '/' + ref]
        for name in candidates:
            found = self.names.get(name.casefold())
            if found:
                return found
        raise FileNotFoundError(f'{self.path.name}: {ref} (from {parent})')

    def xml(self, name, chain=()):
        if name in chain:
            raise ValueError('XML include cycle: ' + name)
        node = ET.fromstring(self.zip.read(name))
        inc = node.attrib.pop('include', None)
        if inc:
            try:
                node = merge(self.xml(self.resolve(inc, name), (*chain, name)), node)
            except FileNotFoundError:
                if 'Generic/' not in inc:
                    raise
        # Includes within sim/model/etc are important for inherited set files.
        for child in list(node):
            if child.tag not in {"sim", "model"} and child.get('omit-node') not in {'y','yes','true'}:
                continue
            inc = child.attrib.pop('include', None)
            if inc:
                try:
                    included = self.xml(self.resolve(inc, name), (*chain, name))
                except FileNotFoundError:
                    # Optional shared FlightGear people/UI are not FDM dependencies.
                    if 'Generic/' not in inc:
                        raise
                    continue
                if child.get('omit-node') in {'y','yes','true'}:
                    index=list(node).index(child);node.remove(child)
                    for offset,part in enumerate(list(included)):node.insert(index+offset,copy.deepcopy(part))
                else:
                    child[:] = list(merge(included, child))
        return node

    def variants(self):
        result = []
        for name in sorted(self.names.values()):
            if not name.endswith('-set.xml') or name.count('/') != 1:
                continue
            try:
                tree = self.xml(name)
                sim = tree.find('sim')
                if sim is None:
                    continue
                fdm_type = sim.findtext('flight-model', '')
                aero = sim.findtext('aero', '')
                fdm = self.resolve(aero + '.xml', name)
                fdm_tree = self.xml(fdm)
                jets = len(fdm_tree.findall('.//jet'))
                if fdm_tree.tag == 'fdm_config':
                    for engine in fdm_tree.findall('.//propulsion/engine'):
                        engine_file = (engine.get('file', '') + '.xml').casefold()
                        candidates = [n for n in self.names.values() if n.rsplit('/',1)[-1].casefold() == engine_file]
                        for engine_path in candidates:
                            try:
                                if self.xml(engine_path).tag.lower() in {'turbine_engine', 'fg_turbine'}:
                                    jets += 1
                                    break
                            except (ValueError, ET.ParseError):
                                pass
                tags = [n.text for n in sim.findall('tags/tag')]
                if not jets and 'jet' not in tags:
                    continue
                result.append({'set': name, 'name': sim.findtext('description', self.path.stem),
                               'fdm_type': fdm_type, 'fdm': fdm, 'jets': jets,
                               'model': self.resolve(sim.findtext('model/path', ''), name),
                               'tags': tags,
                               'model_rating': int(sim.findtext('rating/model', '0')),
                               'fdm_rating': int(sim.findtext('rating/FDM', '0')),
                               'variant_of': sim.findtext('variant-of', '')})
            except (FileNotFoundError, ET.ParseError, ValueError) as exc:
                result.append({'set': name, 'error': str(exc)})
        return result

    def graph(self, name, visited=None):
        """Keep exterior and nested submodels with transforms, not just the first AC."""
        if visited is None:
            visited = set()
        if name in visited:
            raise ValueError('Model cycle: ' + name)
        if not name.lower().endswith('.xml'):
            return {'file': name}
        tree = self.xml(name)
        node = {'file': name, 'offsets': {}, 'children': []}
        for axis in ['x-m', 'y-m', 'z-m', 'roll-deg', 'pitch-deg', 'heading-deg']:
            node['offsets'][axis] = float(tree.findtext('offsets/' + axis, '0'))
        direct = tree.findtext('path')
        if direct:
            node['mesh'] = self.resolve(direct, name)
        node['animations'] = [xml_fragment(a) for a in tree.findall('animation')]
        for child in tree.findall('model'):
            path = child.findtext('path')
            if not path:
                continue
            try:
                sub = self.graph(self.resolve(path, name), visited | {name})
                sub['placement_xml'] = xml_fragment(child)
                sub['object_name'] = child.findtext('name', '')
                node['children'].append(sub)
            except FileNotFoundError as exc:
                node.setdefault('missing_optional_submodels', []).append(str(exc))
        return node


def scan(source, plan):
    metadata = {p.findtext('dir'): p for p in ET.parse(source / 'catalog.xml').getroot().findall('package')}
    candidates, excluded = [], []
    for path in sorted(source.glob('*.zip')):
        if path.stem in EXCLUDE:
            excluded.append({'archive': path.name, 'reason': 'ground vehicle, rotorcraft, rocket or jet pack'})
            continue
        pkg = Package(path)
        variants = pkg.variants()
        good = [v for v in variants if 'error' not in v]
        meta = metadata.get(path.stem)
        tags = [n.text for n in meta.findall('tag')] if meta is not None else []
        if not good and 'jet' not in tags:
            pkg.zip.close()
            continue
        # Prefer a richly modelled base variant; deterministic lexical tie break.
        good.sort(key=lambda v: (-v['model_rating'], -v['fdm_rating'], bool(v['variant_of']), v['set']))
        preferred = PREFERRED_SETS.get(path.stem)
        if preferred:
            good.sort(key=lambda v: v['set'] != preferred)
        item = {'id': IDS.get(path.stem, 'FG-' + path.stem), 'archive': path.name,
                'bytes': path.stat().st_size, 'tags': tags,
                'variants': variants, 'selected_variant': good[0] if good else None,
                'selection': 'selected' if good else 'unresolved', 'reason': 'one representative per package'}
        candidates.append(item)
        if preferred and good and good[0]['set'] == preferred:
            item['reason'] = 'shared exterior model; select the package YASim FDM variant for the standalone host'
        pkg.zip.close()
    by_name = {Path(p['archive']).stem: p for p in candidates}
    for family in FAMILIES:
        available = [by_name[k] for k in family if k in by_name and by_name[k]['selected_variant']]
        if not available:
            continue
        # Explicit preferred package order. Retain rating evidence for review.
        winner = available[0]
        winner['reason'] = 'family representative; preferred package order with model/FDM rating evidence'
        winner['family'] = family
        for other in available[1:]:
            other.update(selection='family_duplicate', representative=winner['id'], family=family)
    data = {'schema': 1, 'source': str(source.resolve()), 'candidates': candidates, 'excluded': excluded}
    dump(plan, data)
    print(json.dumps({'plan': str(plan), 'selected': sum(p['selection'] == 'selected' for p in candidates),
                      'unresolved': [p['archive'] for p in candidates if p['selection'] == 'unresolved'],
                      'duplicates': sum(p['selection'] == 'family_duplicate' for p in candidates)}, indent=2))


def prepare(data, only=()):
    cache = ROOT / 'game/assets/cache/aircraft-2024'
    fdms = ROOT / 'bvr_sim/resources/aircraft'
    for item in data['candidates']:
        if item['selection'] != 'selected' or (only and item['id'] not in only):
            continue
        pkg = Package(Path(data['source']) / item['archive'])
        dest = cache / item['id']
        dest.mkdir(parents=True, exist_ok=True)
        # Every path is validated before extraction. Never write into the source.
        for member in pkg.zip.infolist():
            target = (dest / member.filename).resolve()
            if not target.is_relative_to(dest.resolve()):
                raise ValueError('Unsafe ZIP path: ' + member.filename)
        pkg.zip.extractall(dest)
        variant = item['selected_variant']
        tree = pkg.xml(variant['fdm'])
        out = fdms / item['id']
        out.mkdir(parents=True, exist_ok=True)
        normalizations = []
        if tree.tag == 'airplane':
            normalizations = normalize_yasim(tree)
            if normalizations:
                (out / 'source-fdm.xml').write_bytes(pkg.zip.read(variant['fdm']))
        if tree.tag == 'fdm_config':
            header = tree.find('fileheader')
            if header is not None and any(not header.findtext(k) for k in ['description','author','filecreationdate','version']):
                (out / 'source-fdm.xml').write_bytes(pkg.zip.read(variant['fdm']))
                tree.remove(header)
                normalizations.append('Omitted incomplete optional fileheader for strict standalone JSBSim; original retained in source-fdm.xml')
        dump(out / 'normalizations.json', normalizations)
        ET.ElementTree(tree).write(out / 'fdm.xml', encoding='utf-8', xml_declaration=True)
        defaults = property_defaults(pkg.xml(variant['set']))
        defaults.setdefault('sim/aircraft', Path(variant['set']).name.removesuffix('-set.xml'))
        external = prepare_jsbsim(pkg, variant, out) if variant['fdm_type'] in {'jsb', 'jsbsim'} else []
        dump(out / 'host_properties.json', {'defaults': {k: int(v) if isinstance(v, bool) else v for k, v in defaults.items() if isinstance(v, (int, float, bool))},
                                           'external_inputs': external,
                                           'policy': 'source numeric defaults; undeclared external FlightGear inputs start at zero; Nasal is not executed'})
        graph = pkg.graph(variant['model'])
        recipe = {'id': item['id'], 'package_root': str(dest.resolve()), 'model_graph': graph,
                  'source_archive': str(pkg.path.resolve()), 'source_archive_sha256': hashlib.sha256(pkg.path.read_bytes()).hexdigest(),
                  'fdm_type': variant['fdm_type'], 'fdm_source': variant['fdm'],
                  'source_url': 'https://us1mirror.flightgear.org/fgaddon/Aircraft-2024/' + item['archive'],
                  'name': variant['name'], 'tags': variant['tags'] or item['tags'],
                  'properties': defaults,
                  'output': str((ROOT / 'game/assets/registered' / item['id']).resolve()),
                  'addon_root': str((ROOT.parent / 'work/third_party/Blender-AC3D').resolve())}
        # Source notices remain available with the runtime FDM, as well as in extracted packages.
        notices = [n for n in pkg.names.values() if re.search(r'(^|/)(copying|licen[cs]e|copyright|authors|readme)([. /_-]|$)', n, re.I)
                   and pkg.zip.getinfo(n).file_size < 300000]
        for n in notices:
            if n.endswith('/'):
                continue
            p = out / 'notices' / n
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(pkg.zip.read(n))
        dump(out / 'source.json', {**variant, 'archive': item['archive'], 'archive_sha256': recipe['source_archive_sha256'],
                                   'license': 'FlightGear catalog GPL; see original per-file/package notices',
                                   'source_url': 'https://us1mirror.flightgear.org/fgaddon/Aircraft-2024/' + item['archive']})
        dump(dest / 'recipe.json', recipe)
        print('PREPARED', item['id'], variant['fdm_type'], flush=True)
        pkg.zip.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['scan', 'prepare', 'convert'])
    p.add_argument('--source', type=Path, default=Path('D:/Aircraft-2024'))
    p.add_argument('--plan', type=Path, default=DEFAULT_PLAN)
    p.add_argument('--only', nargs='*', default=[])
    p.add_argument('--exclude', nargs='*', default=[])
    p.add_argument('--resume', action='store_true')
    p.add_argument('--blender', default=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe')
    args = p.parse_args()
    if args.action == 'scan':
        return scan(args.source, args.plan)
    data = json.loads(args.plan.read_text(encoding='utf8'))
    for item in data['candidates']:
        if item['id'] in args.exclude:
            item['selection'] = 'excluded_for_this_run'
    if args.action == 'prepare':
        return prepare(data, args.only)
    result_path = ROOT / 'runs/aircraft-import/conversion-results.json'
    results = json.loads(result_path.read_text(encoding='utf8')) if result_path.exists() else []
    def record_result(result):
        results[:] = [r for r in results if r['id'] != result['id']]
        results.append(result)
        dump(result_path, results)
    runtime_path = ROOT / 'game/runtime.json'
    runtime = json.loads(runtime_path.read_text(encoding='utf8'))
    for item in data['candidates']:
        if item['selection'] != 'selected' or (args.only and item['id'] not in args.only):
            continue
        recipe = ROOT / 'game/assets/cache/aircraft-2024' / item['id'] / 'recipe.json'
        recipe_data = json.loads(recipe.read_text(encoding='utf8'))
        pkg = Package(Path(data['source']) / item['archive'])
        recipe_data['model_graph'] = pkg.graph(item['selected_variant']['model'])
        recipe_data['fdm_type'] = item['selected_variant']['fdm_type']
        recipe_data['fdm_source'] = item['selected_variant']['fdm']
        recipe_data['properties'] = property_defaults(pkg.xml(item['selected_variant']['set']))
        recipe_data['properties'].setdefault('sim/aircraft', Path(item['selected_variant']['set']).name.removesuffix('-set.xml'))
        overrides_path = ROOT / 'game/aircraft_visual_overrides.json'
        overrides = json.loads(overrides_path.read_text(encoding='utf8')) if overrides_path.exists() else {}
        recipe_data['visual_overrides'] = overrides.get(item['id'], {})
        pkg.zip.close()
        dump(recipe, recipe_data)
        converter_hash = hashlib.sha256((ROOT/'game/tools/convert_flightgear.py').read_bytes()).hexdigest()
        manifest_path=ROOT/'game/assets/registered'/item['id']/'manifest.json'
        if args.resume and manifest_path.exists():
            manifest=json.loads(manifest_path.read_text(encoding='utf8'))
            glb=manifest_path.parent/manifest['file']
            if glb.is_file() and hashlib.sha256(glb.read_bytes()).hexdigest()==manifest['glb_sha256'] and manifest.get('converter_sha256')==converter_hash and manifest.get('conversion_recipe')==recipe_data:
                record_result({'id':item['id'],'returncode':0,'resumed':True});continue
        log = ROOT / 'runs/aircraft-import' / (item['id'] + '-convert.log')
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open('w', encoding='utf8') as stream:
            code = subprocess.run([args.blender, '--background', '--python-exit-code', '1', '--python',
                                   str(ROOT / 'game/tools/convert_flightgear.py'), '--', str(recipe)],
                                  stdout=stream, stderr=subprocess.STDOUT).returncode
        record_result({'id': item['id'], 'returncode': code, 'log': str(log)})
        if code == 0:
            runtime = json.loads(runtime_path.read_text(encoding='utf8'))
            runtime.setdefault('imported_models', {})[item['id']] = str((ROOT / 'game/assets/registered' / item['id'] / (item['id'] + '.glb')).resolve())
            dump(runtime_path, runtime)
        dump(ROOT / 'runs/aircraft-import/conversion-results.json', results)
        print('CONVERTED' if code == 0 else 'FAILED', item['id'], flush=True)


if __name__ == '__main__':
    main()
