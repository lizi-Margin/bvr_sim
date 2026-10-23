"""Blender batch normalizer: real source geometry, explicit scale, two LODs, provenance."""
import bpy,sys,json,hashlib,math
from pathlib import Path
from mathutils import Matrix,Vector
spec_path=Path(sys.argv[sys.argv.index('--')+1]);specs=json.loads(spec_path.read_text(encoding='utf8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def stats(objects):
    bpy.context.view_layer.update();meshes=[o for o in objects if o.type=='MESH']
    points=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
    lo=[min(v[i] for v in points) for i in range(3)];hi=[max(v[i] for v in points) for i in range(3)]
    return {'bounds':{'min':lo,'max':hi,'span':[hi[i]-lo[i] for i in range(3)]},'vertices':sum(len(o.data.vertices) for o in meshes),'triangles':sum(sum(len(p.vertices)-2 for p in o.data.polygons) for o in meshes)}
for spec in specs:
    source=Path(spec['source']);out=Path(spec['output']);out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
    objects=list(bpy.context.scene.objects);raw=stats(objects)
    if not raw['triangles']:raise RuntimeError('Empty source asset: '+str(source))
    scale=spec['height_m']/raw['bounds']['span'][2]
    scales=[v/s for v,s in zip(spec['dimensions_m'],raw['bounds']['span'])] if spec.get('dimensions_m') else [scale]*3
    if not all(.01<s<150 for s in scales):raise RuntimeError('Implausible explicit scale')
    offset=Vector((-(raw['bounds']['min'][0]+raw['bounds']['max'][0])*.5*scales[0],-(raw['bounds']['min'][1]+raw['bounds']['max'][1])*.5*scales[1],-raw['bounds']['min'][2]*scales[2]))
    for o in objects:
        if o.parent is None:o.matrix_world=Matrix.Diagonal(Vector((*scales,1)))@o.matrix_world;o.location+=offset
    for material in bpy.data.materials:
        if not material.use_nodes:continue
        bsdf=material.node_tree.nodes.get('Principled BSDF')
        if not bsdf:continue
        bsdf.inputs['Metallic'].default_value=spec['material_policy']['metallic']
        bsdf.inputs['Roughness'].default_value=spec['material_policy']['roughness']
        material.metallic=spec['material_policy']['metallic'];material.roughness=spec['material_policy']['roughness']
        foliage=('leaf' in material.name.lower() or 'leav' in material.name.lower() or spec['id']=='bush')
        if foliage and spec['material_policy'].get('temperate_foliage'):
            bsdf.inputs['Base Color'].default_value=(.055,.23,.025,1)
    textures=[]
    for image in bpy.data.images:
        if image.source=='FILE':
            if not image.size[0]:raise RuntimeError('Missing asset texture: '+image.filepath)
            image.pack();textures.append({'name':image.name,'width':image.size[0],'height':image.size[1]})
    base=stats(objects);lods=[]
    for level in [0,1]:
        if level:
            for o in objects:
                if o.type!='MESH':continue
                bpy.context.view_layer.objects.active=o;o.select_set(True)
                # Preserve UV/materials and silhouette at the coarse viewing distance.
                if len(o.data.polygons)>20:
                    mod=o.modifiers.new('distance_LOD','DECIMATE');mod.ratio=.22
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                o.select_set(False)
        file=out/(spec['id']+('' if level==0 else '_lod1')+'.glb')
        bpy.ops.export_scene.gltf(filepath=str(file),export_format='GLB',export_extras=True)
        lods.append({'level':level,'file':file.name,'sha256':sha(file),**stats(objects)})
    provider=json.loads(Path(spec['provider_manifest']).read_text(encoding='utf8'))
    if provider['license']!='CC0-1.0' or not provider['distribution_allowed']:raise RuntimeError('Uncleared provider license')
    m={'id':spec['id'],'name':spec['name'],'tags':spec['tags'],'source_url':provider['source_url'],'download_url':provider['download_url'],'license':provider['license'],'license_evidence':provider['license_evidence'],'original_file_sha256':sha(source),'source_sha256':sha(source),'source_archive_sha256':provider['archive_sha256'],'glb_sha256':lods[0]['sha256'],'file':lods[0]['file'],'blender':bpy.app.version_string,'conversion_recipe':spec,'units':'meters','physical_size_note':'Generic stylized source geometry with explicit height and optional width/depth calibration; dimensions and aspect ratios are engineering approximations, not surveyed real buildings/species.','original_axes':'glTF right-handed +Y up','runtime_axes':'Wicked left-handed +Y up; NWU -> (-west,up,north)','bounds_blender':base['bounds'],'vertices':base['vertices'],'faces':base['triangles'],'triangles':base['triangles'],'materials':[{'name':m.name,'roughness':m.roughness} for m in bpy.data.materials],'textures':textures,'lods':lods,'recommended_use':spec['use'],'recommended_density_per_km2':spec['density'],'collision_type':spec['collision'],'instancing_allowed':True,'distribution_allowed':True,'nodes':[o.name for o in objects if o.type=='MESH']}
    (out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf8')
    print('REGISTERED',spec['id'],base['triangles'],lods[1]['triangles'])
