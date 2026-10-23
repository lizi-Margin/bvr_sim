"""Blender background entry point. Recipe coordinates must be reviewed per aircraft."""
import bpy, sys, json, math, hashlib
from pathlib import Path
from mathutils import Matrix,Vector
recipe=Path(sys.argv[sys.argv.index('--')+1]).resolve()
r=json.loads(recipe.read_text(encoding='utf8'))
source=Path(r['source']).resolve();out=Path(r['output']).resolve();out.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,r['addon_root']);import io_scene_ac3d;io_scene_ac3d.register()
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.import_ac3d(filepath=str(source))
objects=list(bpy.context.scene.objects)
hidden=[]
for rootname in r.get('hide_roots',[]):
    for obj in objects:
        if obj.name==rootname:
            for node in [obj,*obj.children_recursive]:node.hide_set(True);hidden.append(node.name)
# FG body coordinates in these two reviewed models: -X nose, +Z up in Blender.
# Blender +Y nose becomes glTF -Z and Wicked +Z after its handedness conversion.
rotation=Matrix.Rotation(math.radians(r['blender_z_rotation_deg']),4,'Z')
for obj in objects:
    if obj.parent is None:obj.matrix_world=rotation@obj.matrix_world
missing=[]
for image in bpy.data.images:
    if image.source!='FILE':continue
    if not image.size[0]:
        choices=list(source.parent.rglob(Path(image.filepath).name))
        if choices:image.filepath=str(choices[0]);image.reload()
    if image.size[0]:image.pack()
    else:missing.append(image.filepath)
if missing:raise RuntimeError('Missing model textures: '+str(missing))
bpy.context.view_layer.update()
visible=[o for o in objects if o.type=='MESH' and not o.hide_get()]
points=[o.matrix_world@Vector(c) for o in visible for c in o.bound_box]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
span=[hi[i]-lo[i] for i in range(3)]
if not r['length_range_m'][0]<=span[1]<=r['length_range_m'][1]:
    for o in visible:
        ys=[(o.matrix_world@Vector(c)).y for c in o.bound_box]
        if min(ys)<lo[1]+.2 or max(ys)>hi[1]-.2:print('BOUND_EXTREME',o.name,min(ys),max(ys))
    raise RuntimeError('Aircraft length outside reviewed budget: '+str(span))
for obj in objects:obj.select_set(not obj.hide_get())
target=out/(r['id']+'.glb')
bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_extras=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
animations=[]
import xml.etree.ElementTree as ET
for xml in source.parent.glob('*.xml'):
    try:
        tree=ET.parse(xml)
        for node in tree.findall('.//animation'):
            animations.append({'file':xml.name,'type':node.findtext('type'),'objects':[x.text for x in node.findall('object-name')],'property':node.findtext('property'),'xml':ET.tostring(node,encoding='unicode')})
    except ET.ParseError:pass
metadata={'id':r['id'],'source':str(source),'source_url':r['source_url'],'license':r['license'],'source_sha256':sha(source),'glb_sha256':sha(target),'file':target.name,'bounds_blender':{'min':lo,'max':hi,'span':span},'units':'meters','runtime_axes':'+Z nose, +Y up, +X starboard (Wicked LH)','nodes':[o.name for o in visible],'hidden_static_flight_nodes':hidden,'faces':sum(len(o.data.polygons) for o in visible),'blender':bpy.app.version_string,'conversion_recipe':r,'animation_status':'XML preserved in animation_inventory.json; static flight pose only; no dynamic animation playback'}
(out/'manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
(out/'animation_inventory.json').write_text(json.dumps(animations,ensure_ascii=False,indent=2),encoding='utf8')
(out/'recipe.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
print('ASSET_REGISTERED',json.dumps({'id':r['id'],'file':str(target),'span':span,'faces':metadata['faces']}))
