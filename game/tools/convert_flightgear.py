"""Blender background converter for a resolved FlightGear exterior model graph.

Preserves named nodes and converts rotate/translate animations to runtime pivots.
Nasal, cockpit systems and shader/effect programs are never executed.
"""
import bpy
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from mathutils import Matrix, Vector
import xml.etree.ElementTree as ET
CONVERTER_SHA256 = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

if hasattr(sys.stdout, 'reconfigure'): sys.stdout.reconfigure(line_buffering=True)
recipe = json.loads(Path(sys.argv[sys.argv.index('--') + 1]).read_text(encoding='utf8'))
package = Path(recipe['package_root'])
out = Path(recipe['output'])
out.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, recipe['addon_root'])
import io_scene_ac3d
io_scene_ac3d.register()
# Upstream importer indexes polygon UVs through all surfaces, including line
# primitives. Use the polygon-only surface list so mixed legacy AC files load.
import io_scene_ac3d.import_ac3d as ac3d_import
import inspect, textwrap
method_source=textwrap.dedent(inspect.getsource(ac3d_import.AcObj.create_blender_object))
method_source=method_source.replace('surf = self.surf_list[i]', 'surf = self.surf_face_list[i]')
method_source=method_source.replace('if self.bl_obj:', 'if self.bl_obj:\n        self.bl_obj["fg_name"] = self.name', 1)
method_globals=dict(ac3d_import.__dict__)
exec(compile(method_source,'<bvr-ac3d-polygon-uv-fix>','exec'),method_globals)
ac3d_import.AcObj.create_blender_object=method_globals['create_blender_object']
bpy.ops.wm.read_factory_settings(use_empty=True)
all_animations, runtime_animations, skipped, meshes = [], [], [], []
properties = recipe.get('properties', {})
properties = {k.lstrip('/').replace('[0]', ''): v for k, v in properties.items()}
properties.update({'controls/gear/gear-down': 0, 'gear/gear-pos-norm': 0,
                   'surface-positions/gear-pos-norm': 0, 'controls/flight/flaps': 0,
                   'controls/flight/speedbrake': 0, 'canopy/position-norm': 0,
                   'sim/current-view/internal': 0})
properties.setdefault('sim/rendering/static-lod/detailed', 2000.)
review = recipe.get('visual_overrides', {})
properties.update(review.get('properties', {}))
for k in list(properties):
    if any(w in k.lower() for w in ['gear-pos-norm', 'gear/position-norm', 'canopy/position']):
        properties[k] = 0


def numeric(text, default=0):
    if text is None or not str(text).strip(): return float(default)
    return float(str(text).strip().replace(",", "."))


def prop(name):
    value = properties.get((name or '').lstrip('/').replace('[0]', ''), 0)
    try:
        return float(value or 0)
    except (ValueError, TypeError):
        return 0.


def condition(node):
    if node is None:
        return True
    children = list(node)
    if node.tag in {'condition', 'and'}:
        return all(condition(c) for c in children)
    if node.tag == 'or':
        return any(condition(c) for c in children)
    if node.tag == 'not':
        return not condition(children[0])
    if node.tag == 'property':
        return bool(prop(node.text))
    if node.tag in {'equals', 'not-equals', 'less-than', 'greater-than', 'less-than-equals', 'greater-than-equals'}:
        vals = [properties.get((c.text or '').lstrip('/').replace('[0]', ''), 0) if c.tag == 'property' else c.text for c in children]
        vals = [1 if str(v).lower() == 'true' else 0 if str(v).lower() == 'false' else v for v in vals]
        if len(vals) < 2:
            return True
        try:
            a, b = float(vals[0]), float(vals[1])
        except (TypeError, ValueError):
            a, b = str(vals[0]), str(vals[1])
        return {'equals': lambda: a == b, 'not-equals': lambda: a != b,
                'less-than': lambda: a < b, 'greater-than': lambda: a > b,
                'less-than-equals': lambda: a <= b, 'greater-than-equals': lambda: a >= b}[node.tag]()
    return True


def empty(name, parent=None):
    o = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(o)
    o.parent = parent
    return o


def offsets(node):
    if node is None:
        return Matrix.Identity(4)
    def value(key):
        return float(node.findtext(key, '0') or '0')
    # FG XML model coordinates and imported AC3D: +X aft,+Y right,+Z up.
    t = Matrix.Translation(Vector((value('x-m'), value('y-m'), value('z-m'))))
    # Same ordered rotations as SimGear SGReaderWriterXML (pitch, roll, heading).
    return t @ Matrix.Rotation(math.radians(value('heading-deg')), 4, 'Z') @ Matrix.Rotation(math.radians(value('roll-deg')), 4, 'X') @ Matrix.Rotation(math.radians(value('pitch-deg')), 4, 'Y')


def vector(node, default=(0, 0, 0)):
    if node is None:
        return Vector(default)
    return Vector([numeric(node.findtext(k, node.findtext(k + '-m', str(v))),v) for k, v in zip(['x', 'y', 'z'], default)])


def object_world(obj):
    # matrix_local is dependency-graph evaluated and can remain stale after
    # creating/reparenting pivots. RNA basis/inverse fields are immediate.
    local = obj.matrix_parent_inverse @ obj.matrix_basis
    return object_world(obj.parent) @ local if obj.parent else obj.matrix_basis.copy()


def animate(xml, objects, parent):
    a = ET.fromstring('<root>'+xml+'</root>')[0]
    typ = a.findtext('type', 'none')
    names = [n.text for n in a.findall('object-name')]
    matches = [o for o in objects if o.get('fg_name', o.name) in names]
    entry = {'xml': xml, 'type': typ, 'objects': names, 'matched': [o.name for o in matches]}
    all_animations.append(entry)
    if typ in {'select', 'range'}:
        visible = condition(a.find('condition'))
        if typ == 'range':
            low = prop(a.findtext('min-property')) if a.find('min-property') is not None else numeric(a.findtext('min-m'), 0)
            high = prop(a.findtext('max-property')) if a.find('max-property') is not None else numeric(a.findtext('max-m'), 1e12)
            visible = visible and low <= 10. <= high
        if not visible:
            for o in matches:
                o.hide_render = True
                for c in o.children_recursive:
                    c.hide_render = True
        return
    if not condition(a.find('condition')):
        return
    if typ not in {'rotate', 'translate'}:
        if typ not in {'none', 'material', 'pick', 'shader', 'blend', 'textranslate', 'texrotate', 'alpha-test'}:
            skipped.append({'type': typ, 'reason': 'unsupported animation type'})
        return
    if not matches:
        return
    center = vector(a.find('center'))
    axis_node = a.find('axis')
    axis = vector(axis_node, (0, 0, 1))
    if axis_node is not None and axis_node.find('x1-m') is not None:
        center = Vector([float(axis_node.findtext(k+'1-m', '0')) for k in ['x','y','z']])
        axis = Vector([float(axis_node.findtext(k+'2-m', '0')) for k in ['x','y','z']]) - center
    if axis.length < 1e-9:
        return
    axis.normalize()
    table = [[numeric(n.findtext('ind', '0')), numeric(n.findtext('dep', '0'))] for n in a.findall('interpolation/entry')]
    factor_node = a.find('factor')
    if factor_node is not None and len(factor_node):
        skipped.append({'xml': xml, 'reason': 'property/expression factor retained, not baked'})
        return
    factor = float(a.findtext('factor', '1') or '1')
    offset = float(a.findtext('offset-deg' if typ == 'rotate' else 'offset-m', '0') or '0')
    for obj in matches:
        if obj.hide_render:
            continue
        previous_pivot = obj.parent if obj.parent and obj.parent.name.startswith('fg_anim_') else None
        pivot = empty(f'fg_anim_{len(runtime_animations):05d}', previous_pivot or parent)
        pivot.location = center - Vector(previous_pivot.get('fg_center', (0,0,0))) if previous_pivot else center
        pivot['fg_center'] = list(center)
        # Coordinates in animation XML are in the enclosing model's frame.
        old = object_world(obj)
        obj.parent = pivot
        obj.matrix_parent_inverse = Matrix.Identity(4)
        obj.matrix_basis = object_world(pivot).inverted_safe() @ old
        record = {'node': pivot.name, 'type': typ, 'property': a.findtext('property', '').lstrip('/'),
                  'axis_blender': list(axis), 'center_blender': list(center), 'factor': factor,
                  'offset': offset, 'interpolation': table,
                  'min': float(a.findtext('min-deg' if typ == 'rotate' else 'min-m', '-1e12') or '-1e12'),
                  'max': float(a.findtext('max-deg' if typ == 'rotate' else 'max-m', '1e12') or '1e12'),
                  'initial_value': 0,
                  'condition_xml': ET.tostring(a.find('condition'), encoding='unicode') if a.find('condition') is not None else ''}
        value = prop(record['property'])
        if table:
            table.sort()
            value = table[0][1] if value <= table[0][0] else table[-1][1] if value >= table[-1][0] else next(y0+(y1-y0)*(value-x0)/(x1-x0) for (x0,y0),(x1,y1) in zip(table,table[1:]) if x0<=value<x1)
        else:
            value = value * factor + offset
        value = max(record['min'], min(record['max'], value))
        record['initial_value'] = value
        if typ == 'rotate':
            pivot.rotation_mode = 'AXIS_ANGLE'
            pivot.rotation_axis_angle = (math.radians(value), *axis)
        else:
            pivot.location += axis * value
        runtime_animations.append(record)


def load(graph, parent=None):
    file = graph['file']
    if any(file.startswith(prefix) for prefix in review.get('exclude_paths', [])):
        skipped.append({'file': file, 'reason': 'reviewed exterior-only exclusion; see visual_overrides'})
        return []
    # Keep exterior, engine and control-surface geometry. Instrument/cockpit
    # systems need FlightGear's UI host and are explicitly outside this import.
    if re.search(r'/(Cockpit|Flightdeck|Cabins?|Interior|Instruments|Panels?|Lights?|Armament|Weapons|Stores|Payloads|Ordnance|ext-stores|Service|Ground|Pushback|Shadow|Effects)(/|[-_.])|ground-fuelling|generic-trailer|/Effects/.*(flame|effect[.]ac|effect2[.]ac)', file, re.I):
        skipped.append({'file': file, 'reason': 'interior instrumentation'})
        return []
    if graph.get('placement_xml'):
        placement = ET.fromstring('<root>'+graph['placement_xml']+'</root>')[0]
        if not condition(placement.find('condition')):
            skipped.append({'file': file, 'reason': 'submodel condition false in flight pose'})
            return []
    group = empty('fg_model_' + str(len(meshes)) + '_' + Path(file).stem, parent)
    own_offsets = ET.Element('offsets')
    for key, value in graph.get('offsets', {}).items():
        ET.SubElement(own_offsets, key).text = str(value)
    group['fg_name'] = graph.get('object_name', group.name)
    # Assign local basis directly. Blender's matrix_local setter/readback can
    # compensate an unevaluated parent matrix, duplicating parent offsets.
    group.matrix_parent_inverse = Matrix.Identity(4)
    group.matrix_basis = offsets(own_offsets)
    if graph.get('placement_xml'):
        group.matrix_basis = offsets(ET.fromstring('<root>'+graph['placement_xml']+'</root>')[0].find('offsets')) @ group.matrix_basis
    source = graph.get('mesh', file if not file.lower().endswith('.xml') else '')
    imported = []
    if source and re.search(r'/Effects/.*(flame|effect[.]ac|effect2[.]ac)|ground-fuelling|generic-trailer', source, re.I):
        skipped.append({'file': source, 'reason': 'FlightGear effect or ground equipment geometry'})
        source = ''
    if source:
        before = set(bpy.context.scene.objects)
        full = package / source
        if full.suffix.lower() == '.ac':
            bpy.ops.import_scene.import_ac3d(filepath=str(full))
        elif full.suffix.lower() == '.3ds':
            sys.path.insert(0,str(Path(__file__).resolve().parent))
            from fg_3ds import import_mesh
            import_mesh(full)
            skipped.append({'file':source,'reason':'3DS geometry/UV imported; legacy material colors approximated'})
        elif full.suffix.lower() in {'.osgt','.osgx','.osg','.xml'}:
            skipped.append({'file':source,'reason':'FlightGear effect program; attachment metadata used instead'})
        elif full.suffix.lower() in {'.gltf', '.glb'}:
            bpy.ops.import_scene.gltf(filepath=str(full))
        else:
            raise ValueError('Unsupported mesh format: ' + source)
        imported = [o for o in bpy.context.scene.objects if o not in before]
        for obj in imported:
            # AC3D names can legitimately end in .001/.004. Stripping that
            # suffix makes gear animations accidentally rotate the fuselage.
            if 'fg_name' not in obj:
                obj['fg_name'] = obj.name
            if obj.parent not in imported:
                obj.parent = group
        meshes.append(source)
    for child in graph.get('children', []):
        imported.extend(load(child, group))
    bpy.context.view_layer.update()
    for xml in graph.get('animations', []):
        try:
            animate(xml, imported, group)
        except (ValueError, ET.ParseError) as exc:
            skipped.append({'xml':xml,'reason':'invalid source animation: '+str(exc)})
    return imported + [group]


root = empty('aircraft_' + recipe['id'])
load(recipe['model_graph'], root)
root.matrix_world = Matrix.Rotation(math.radians(-90), 4, 'Z')
bpy.context.view_layer.update()
# Nozzle positions are measured in converted geometry, in runtime LH axes.
nozzle_candidates = []
for obj in bpy.context.scene.objects:
    if obj.type == 'MESH' and not obj.hide_render and re.search(r'nozzle|exhaust|internalflame', obj.get('fg_name', obj.name), re.I):
        pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        mn = [min(p[i] for p in pts) for i in range(3)]
        mx = [max(p[i] for p in pts) for i in range(3)]
        if mx[0]-mn[0] < 6 and mx[1]-mn[1] < 8:
            nozzle_candidates.append({'position': [(mn[0]+mx[0])/2, (mn[2]+mx[2])/2, mn[1]], 'radius_m': min(1.5,max(.08,(mx[0]-mn[0])/2)), 'source_node': obj.name, 'method': 'aft plane of named nozzle/exhaust geometry'})
exhausts = []
for candidate in sorted(nozzle_candidates,key=lambda c:c['position'][2]):
    if not any(abs(c['position'][0]-candidate['position'][0])<.6 for c in exhausts):
        exhausts.append(candidate)
missing = []
file_index = {}
for p in package.rglob('*'):
    if p.is_file():
        file_index.setdefault(p.name.casefold(), p)
for image in bpy.data.images:
    if image.source != 'FILE':
        continue
    if not image.size[0]:
        candidate = file_index.get(Path(image.filepath).name.casefold())
        if candidate:
            image.filepath = str(candidate)
            try:
                image.reload()
            except RuntimeError:
                pass
    if image.size[0]:
        image.pack()
    else:
        missing.append(image.filepath)
# A missing optional texture must be reported. Preserve source material colors
# rather than exporting Blender's magenta error texture.
for material in bpy.data.materials:
    if material.use_nodes:
        for node in list(material.node_tree.nodes):
            if node.type == 'TEX_IMAGE' and node.image and not node.image.size[0]:
                material.node_tree.nodes.remove(node)
for o in bpy.context.scene.objects:
    if o.get('fg_name',o.name) in review.get('hide_nodes', []) or re.search(r'flame|afterburner|halo|contrail|smoke|vapor|vortex|shadow|light.?cone|cone[-_ ]?texture|^cone$|parachut|dragchute|brake.?chute|^LIT-|GPUcart|fuel-truck|chocks|extinguisher', o.get('fg_name',o.name), re.I):
        o.hide_render = True
        for child in o.children_recursive:
            child.hide_render = True
visible = [o for o in bpy.context.scene.objects if o.type == 'MESH' and len(o.data.polygons) and not o.hide_render]
if not visible:
    raise ValueError('No exterior geometry in model graph')
points = [o.matrix_world @ Vector(c) for o in visible for c in o.bound_box]
lo = [min(p[i] for p in points) for i in range(3)]
hi = [max(p[i] for p in points) for i in range(3)]
for o in bpy.context.scene.objects:
    # AC3D's editor-only hidden flag is not FlightGear's runtime visibility.
    # Hidden viewport objects cannot be selected by Blender's GLB exporter.
    o.hide_set(False)
    o.select_set(not o.hide_render)
target = out / (recipe['id'] + '.glb')
bpy.ops.export_scene.gltf(filepath=str(target), export_format='GLB', use_selection=True,
                          export_extras=True, export_animations=False)
manifest = {'id': recipe['id'], 'name': recipe['name'], 'file': target.name,
            'converter_sha256': CONVERTER_SHA256,
            'glb_sha256': hashlib.sha256(target.read_bytes()).hexdigest(),
            'source_archive': recipe['source_archive'], 'source_archive_sha256': recipe['source_archive_sha256'],
            'license': 'FlightGear GPL; source package and FDM notices retained',
            'source_url': recipe.get('source_url', ''),
            'meshes': meshes, 'faces': sum(len(o.data.polygons) for o in visible),
            'bounds_blender': {'min': lo, 'max': hi, 'span': [hi[i] - lo[i] for i in range(3)]},
            'runtime_axes': '+Z nose,+Y up,+X starboard (Wicked LH)', 'units': 'metres',
            'exhausts': exhausts, 'exhaust_status': 'geometry measured' if exhausts else 'no named nozzle geometry found; needs reviewed attachment positions',
            'animations': runtime_animations, 'animation_xml_count': len(all_animations),
            'missing_textures': missing, 'skipped': skipped, 'blender': bpy.app.version_string,
            'animation_status': 'rotate/translate pivots imported; runtime drives supported snapshot properties; other XML retained',
            'nodes': [o.name for o in visible],
            'node_bounds': [{'name':o.name, 'min':[min((o.matrix_world@Vector(c))[i] for c in o.bound_box) for i in range(3)], 'max':[max((o.matrix_world@Vector(c))[i] for c in o.bound_box) for i in range(3)]} for o in visible],
            'conversion_recipe': recipe}
for name, data in [('manifest.json', manifest), ('animation_inventory.json', all_animations)]:
    (out / name).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf8')
print('FLIGHTGEAR_CONVERTED', recipe['id'], len(visible), len(runtime_animations), len(missing), flush=True)

if recipe.get('preview'):
    scene=bpy.context.scene
    scene.render.engine='BLENDER_WORKBENCH'
    scene.display.shading.light='STUDIO'
    scene.display.shading.color_type='TEXTURE'
    scene.display.shading.show_shadows=True
    scene.display.shading.show_cavity=True
    scene.display.shading.background_type='WORLD'
    if scene.world is None: scene.world=bpy.data.worlds.new('review_world')
    scene.world.color=(.22,.25,.3)
    camera=bpy.data.objects.new('review_camera',bpy.data.cameras.new('review_camera'))
    scene.collection.objects.link(camera)
    focus=Vector((0,0,0));camera.location=(26,35,17)
    camera.rotation_euler=(focus-camera.location).to_track_quat('-Z','Y').to_euler()
    camera.data.lens=42;scene.camera=camera
    scene.render.resolution_x=1100;scene.render.resolution_y=800;scene.render.resolution_percentage=100
    scene.render.filepath=str(out/'preview.png');bpy.ops.render.render(write_still=True)
