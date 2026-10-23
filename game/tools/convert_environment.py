"""Blender conversion of a downloaded GLTF with its provider manifest."""
import bpy,sys,json,hashlib
from pathlib import Path
from mathutils import Vector
source,manifest,asset_id,out=sys.argv[sys.argv.index('--')+1:]
source=Path(source).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
origin=json.loads(Path(manifest).read_text(encoding='utf8'))
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise RuntimeError('Asset contains no geometry')
for image in bpy.data.images:
    if image.source=='FILE':
        if not image.size[0]:raise RuntimeError('Missing texture: '+image.filepath)
        image.pack()
bpy.context.view_layer.update()
points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
target=out/(asset_id+'.glb');bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',export_extras=True)
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
r={'id':asset_id,'source':str(source),'source_url':origin['source_url'],'license':origin['license'],'source_sha256':sha(source),'glb_sha256':sha(target),'file':target.name,'bounds_blender':{'min':lo,'max':hi,'span':[hi[i]-lo[i] for i in range(3)]},'units':'meters','runtime_axes':'glTF RH imported by Wicked LH conversion','nodes':[o.name for o in meshes],'faces':sum(len(o.data.polygons) for o in meshes),'blender':bpy.app.version_string,'conversion_recipe':{'source':str(source),'provider_manifest':str(Path(manifest).resolve())},'credit':origin.get('credit')}
(out/'manifest.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
