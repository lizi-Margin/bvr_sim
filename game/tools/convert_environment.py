"""Blender conversion of a downloaded GLTF with its provider manifest."""
import bpy,sys,json,hashlib
from pathlib import Path
from mathutils import Vector,Matrix
arguments=sys.argv[sys.argv.index('--')+1:];source,manifest,asset_id,out=arguments[:4]
policy=json.loads(Path(arguments[4]).read_text(encoding='utf8')) if len(arguments)>4 else {}
source=Path(source).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
origin=json.loads(Path(manifest).read_text(encoding='utf8'))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for item in origin.get('files',[]):
    file=(Path(manifest).parent/item['path']).resolve()
    if not file.is_relative_to(Path(manifest).parent.resolve()) or sha(file)!=item['sha256']:raise ValueError('Provider dependency hash mismatch: '+item['path'])
bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
if not meshes:raise RuntimeError('Asset contains no geometry')
if policy.get('select_object'):
    selected=[o for o in meshes if o.name==policy['select_object']]
    if len(selected)!=1:raise ValueError('Recipe must select one exact source object')
    for o in meshes:
        if o not in selected:bpy.data.objects.remove(o,do_unlink=True)
    meshes=selected
for image in bpy.data.images:
    if image.source=='FILE':
        if not image.size[0]:raise RuntimeError('Missing texture: '+image.filepath)
        image.pack()
bpy.context.view_layer.update()
points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
lo=[min(p[i] for p in points) for i in range(3)];hi=[max(p[i] for p in points) for i in range(3)]
if policy:
    scale=policy.get('height_m',hi[2]-lo[2])/(hi[2]-lo[2])
    if not .01<scale<150:raise ValueError('Invalid declared asset scale')
    transform=Matrix.Translation(Vector((-(lo[0]+hi[0])*scale/2,-(lo[1]+hi[1])*scale/2,-lo[2]*scale)))@Matrix.Scale(scale,4)
    for o in meshes:
        world=o.matrix_world.copy();o.parent=None;o.matrix_world=transform@world
    height=(hi[2]-lo[2])*scale
    lo=[-(hi[0]-lo[0])*scale/2,-(hi[1]-lo[1])*scale/2,0];hi=[-lo[0],-lo[1],height]
    bpy.context.view_layer.update()
sys.path.insert(0,str(Path(__file__).resolve().parent))
from vegetation_lod import triangles,reduce_meshes,impostors,alpha_mask_glb,make_cluster,source_foliage_cards
source_bounds=(list(lo),list(hi));backup=[];foliage_report=None
if policy.get('foliage_cards'):
    if not policy.get('cluster') or not policy.get('impostor'):raise ValueError('Foliage cards require the source grove/far-bake policy')
    for o in meshes:
        b=o.copy();b.data=o.data.copy();b.name=o.name+'_near_source_backup';b.hide_render=True
        bpy.context.scene.collection.objects.link(b);backup.append(b)
cluster_report=None
if policy.get('cluster'):
    meshes,bounds,cluster_report=make_cluster(meshes,policy['cluster']);lo,hi=bounds['min'],bounds['max']
far=None;impostor_report=None
if policy.get('impostor'):
    far,impostor_report=impostors(meshes,out,hi[2],max(hi[0]-lo[0],hi[1]-lo[1]),policy.get('impostor_resolution',512),policy.get('impostor_engine','BLENDER_EEVEE'))
if backup:
    for o in meshes:bpy.data.objects.remove(o,do_unlink=True)
    slo,shi=source_bounds
    hybrid,foliage_report=source_foliage_cards(backup,out/'near_foliage',shi[2],max(shi[0]-slo[0],shi[1]-slo[1]),policy['foliage_cards'],policy.get('impostor_engine','BLENDER_EEVEE'))
    meshes,_,hybrid_cluster=make_cluster(hybrid,policy['cluster'],cluster_report['source_base_anchor_blender'])
    # Transparent card bounds exceed visible foliage. Preserve the source
    # grove's origin/bounds/anchor metadata and exact full-source far LOD.
    delta=Vector(hybrid_cluster['recentering'])-Vector(cluster_report['recentering'])
    for o in meshes:o.location+=delta
    if triangles(meshes)>policy.get('near_triangle_budget',triangles(meshes)):raise ValueError('Hybrid near grove exceeds its declared budget')
else:reduce_meshes(meshes,policy.get('near_triangle_budget',triangles(meshes)))
if len(meshes)>1 and cluster_report:
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:o.hide_set(False);o.select_set(True)
    bpy.context.view_layer.objects.active=meshes[0];bpy.ops.object.join();meshes=[bpy.context.view_layer.objects.active]
def export(objects,file):
    bpy.ops.object.select_all(action='DESELECT')
    for o in objects:o.hide_set(False);o.hide_render=False;o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',export_extras=True,use_selection=True)
target=out/(asset_id+'.glb');export(meshes,target)
if foliage_report:alpha_mask_glb(target)
lods=[{'level':0,'file':target.name,'sha256':sha(target),'triangles':triangles(meshes)}]
if far:
    file=out/(asset_id+'_lod1.glb');export(far,file);alpha_mask_glb(file)
    lods.append({'level':1,'file':file.name,'sha256':sha(file),'triangles':triangles(far)})
r={'id':asset_id,'name':policy.get('name',asset_id),'tags':policy.get('tags',[]),'source':str(source),'source_url':origin['source_url'],'license':origin['license'],'source_sha256':sha(source),'glb_sha256':sha(target),'file':target.name,'bounds_blender':{'min':lo,'max':hi,'span':[hi[i]-lo[i] for i in range(3)]},'units':'meters','runtime_axes':'Wicked left-handed +Y up; NWU -> (-west,up,north)','nodes':[o.name for o in meshes],'faces':triangles(meshes),'triangles':triangles(meshes),'blender':bpy.app.version_string,'conversion_recipe':{'source':str(source),'provider_manifest':str(Path(manifest).resolve()),'policy':policy},'credit':origin.get('credit'),
    'source_files':origin.get('files',[]),'source_bundle_sha256':hashlib.sha256(json.dumps(origin.get('files',[]),sort_keys=True).encode()).hexdigest(),
    'license_evidence':[{'url':'https://polyhaven.com/license','provider_manifest_sha256':sha(manifest)}] if origin['source']=='polyhaven' else origin.get('license_evidence',[]),
    'distribution_allowed':origin['license']=='CC0-1.0','instancing_allowed':True,'physical_size_note':policy.get('physical_size_note','Source dimensions retained'),
    'lods':lods,'impostor':impostor_report,'cluster':cluster_report,'foliage_representation':foliage_report,'textures':[{'name':i.name,'width':i.size[0],'height':i.size[1]} for i in bpy.data.images if i.size[0]],
    'vertices':sum(len(o.data.vertices) for o in meshes),
    'materials':[{'name':m.name,'roughness':m.roughness} for m in {s.material for o in meshes+(far or []) for s in o.material_slots if s.material}],
    'recommended_use':policy.get('recommended_use','Instanced scenery; source-bounded normalized geometry and explicit LODs'),
    'recommended_density_per_km2':policy.get('recommended_density_per_km2',2000),
    'collision_type':'decorative vegetation' if policy.get('impostor') else 'source bounds'}
(out/'manifest.json').write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8')
print('REGISTERED',asset_id,'LOD_TRIANGLES',[x['triangles'] for x in lods])
