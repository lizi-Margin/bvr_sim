"""Blender CPU renders of registered aircraft geometry for the hangar carousel.

blender --background --python game/tools/render_menu_thumbnails.py -- SOURCES.json OUTPUT
SOURCES is exported from aircraft_catalog(include_library=True); no new geometry.
"""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils import Vector
args=sys.argv[sys.argv.index('--')+1:];source=Path(args[0]);output=Path(args[1]);output.mkdir(parents=True,exist_ok=True)
rows=json.loads(source.read_text(encoding='utf8'));results=[]
for row in rows:
    asset=Path(row['appearance']['file']);target=output/(row['id']+'.png');digest=hashlib.sha256(asset.read_bytes()).hexdigest()
    meta=target.with_suffix('.json')
    if target.exists() and meta.exists() and json.loads(meta.read_text())['source_sha256']==digest:continue
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.import_scene.gltf(filepath=str(asset))
        objects=[o for o in bpy.context.scene.objects if o.type=='MESH']
        points=[o.matrix_world@Vector(p) for o in objects for p in o.bound_box]
        lo=Vector([min(p[i] for p in points) for i in range(3)]);hi=Vector([max(p[i] for p in points) for i in range(3)])
        center=(lo+hi)/2;size=max(hi-lo)
        scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8
        scene.render.resolution_x=376;scene.render.resolution_y=120;scene.render.resolution_percentage=100
        scene.render.film_transparent=True;scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGBA'
        scene.world=bpy.data.worlds.new('thumbnail_world');scene.world.use_nodes=True
        scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.32,.37,.42,1)
        scene.world.node_tree.nodes['Background'].inputs[1].default_value=.6
        camera_data=bpy.data.cameras.new('catalog_camera');camera=bpy.data.objects.new('catalog_camera',camera_data);scene.collection.objects.link(camera)
        camera.location=center+Vector((.9,-1.3,.9))*size;camera.rotation_euler=(center-camera.location).to_track_quat('-Z','Y').to_euler();camera_data.type='ORTHO'
        inv=camera.rotation_euler.to_matrix().transposed();projected=[inv@(p-center) for p in points]
        dx=max(p.x for p in projected)-min(p.x for p in projected);dy=max(p.y for p in projected)-min(p.y for p in projected)
        camera_data.ortho_scale=max(dx,dy*376/120)*1.08;camera_data.clip_end=max(1000,size*10);scene.camera=camera
        for offset,energy in [((1,-1,2),100),((-1,0,1),70)]:
            data=bpy.data.lights.new('catalog_softbox','AREA');data.energy=energy*size*size;data.shape='DISK';data.size=size*2
            light=bpy.data.objects.new('catalog_softbox',data);scene.collection.objects.link(light);light.location=center+Vector(offset)*size
            light.rotation_euler=(center-light.location).to_track_quat('-Z','Y').to_euler()
        scene.view_settings.view_transform='AgX';scene.render.filepath=str(target)
        bpy.ops.render.render(write_still=True)
        result={'aircraft':row['id'],'source':str(asset),'source_sha256':digest,'file':str(target),
                'png_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'renderer':'Blender Cycles CPU8samples',
                'scope':'Actual registered geometry/material render; thumbnail only, no FDM or source asset change.'}
        meta.write_text(json.dumps(result,indent=2),encoding='utf8');results.append(result)
        print('THUMBNAIL_READY',row['id'],flush=True)
    except Exception as error:
        result={'aircraft':row['id'],'error':repr(error)};results.append(result);print('THUMBNAIL_FAILED',result,flush=True)
    for images in [bpy.data.images,bpy.data.meshes,bpy.data.materials]:
        for item in list(images):
            if item.users==0:images.remove(item)
(output/'build-report.json').write_text(json.dumps(results,indent=2),encoding='utf8')
