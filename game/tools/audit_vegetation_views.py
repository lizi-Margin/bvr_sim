"""Blender: compare a registered tree's crossed cards with its actual source.

Run with blender --background --python-exit-code 1 --python THIS_FILE --
--asset fir_grove_stream_a --output NEW_DIRECTORY. This is an unlit,
orthographic representation audit, not a Wicked/TAA or final-map review.
"""
import argparse,hashlib,json,math,sys
import numpy as np
from pathlib import Path
import bpy
from mathutils import Matrix,Vector

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE))
from vegetation_lod import impostors
from vegetation_bake_cache import reusable_bakes

sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()


def unlit(objects):
    """Preserve source RGB/opacity graphs; remove illumination from the audit."""
    copies={};weights=[]
    for obj in objects:
        for i,original in enumerate(list(obj.data.materials)):
            if original not in copies:
                material=original.copy();nodes=material.node_tree.nodes;links=material.node_tree.links
                bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');output=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
                emission=nodes.new('ShaderNodeEmission');transparent=nodes.new('ShaderNodeBsdfTransparent');mix=nodes.new('ShaderNodeMixShader')
                color=bsdf.inputs['Base Color'];alpha=bsdf.inputs['Alpha']
                if color.is_linked:links.new(color.links[0].from_socket,emission.inputs['Color'])
                else:emission.inputs['Color'].default_value=color.default_value
                weight=nodes.new('ShaderNodeMath');weight.operation='MULTIPLY';weight.inputs[1].default_value=1
                if alpha.is_linked:links.new(alpha.links[0].from_socket,weight.inputs[0])
                else:weight.inputs[0].default_value=alpha.default_value
                links.new(weight.outputs[0],mix.inputs[0]);links.new(transparent.outputs[0],mix.inputs[1]);links.new(emission.outputs[0],mix.inputs[2]);links.new(mix.outputs[0],output.inputs['Surface'])
                copies[original]=material;weights.append((material.name,weight))
            obj.data.materials[i]=copies[original]
    return weights


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--asset',required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--resolution',type=int,default=512)
    parser.add_argument('--aerial-source-manifest',type=Path,help='Audit an offline oblique-view bake with exact embedded-image validation; it need not be registered for gameplay')
    parser.add_argument('--depth-centroid',action='store_true',help='Also move each chosen plane along its viewing normal to the actual source twig-area centroid')
    a=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    if a.depth_centroid and not a.aerial_source_manifest:parser.error('--depth-centroid requires --aerial-source-manifest')
    if not a.asset.replace('_','').replace('-','').isalnum():raise ValueError('Invalid registered asset id')
    if not 128<=a.resolution<=2048:raise ValueError('Audit resolution outside128..2048')
    if a.output.exists():raise FileExistsError(a.output)
    manifest_path=ROOT/'game/assets/registered'/a.asset/'manifest.json';manifest=json.loads(manifest_path.read_text(encoding='utf8'));policy=manifest['conversion_recipe']['policy'];source=Path(manifest['source'])
    if sha(source)!=manifest['source_sha256']:raise ValueError('Source changed')
    for entry in manifest['source_files']:
        file=(source.parent/entry['path']).resolve()
        if not file.is_relative_to(source.parent.resolve()) or sha(file)!=entry['sha256']:raise ValueError('Source dependency changed')
    if not policy.get('individual_tree_impostors'):raise ValueError('Audit requires individual source-tree cards')
    # Validate the PNGs against the registered GLB embedded image bytes.
    reuse=reusable_bakes({'manifest':str(manifest_path),'sha256':sha(manifest_path)},sha(source),policy)
    additional=[];alternative=None
    if a.aerial_source_manifest:
        alternative=json.loads(a.aerial_source_manifest.read_text(encoding='utf8'));extra_policy=alternative['conversion_recipe']['policy']
        for key in ['select_object','height_m','impostor_resolution','impostor_normal_maps']:
            if extra_policy.get(key)!=policy.get(key):raise ValueError('Alternative bake source configuration differs: '+key)
        additional=extra_policy['impostor_aerial_views']
        reuse=reusable_bakes({'manifest':str(a.aerial_source_manifest),'sha256':sha(a.aerial_source_manifest)},sha(source),extra_policy)
    a.output.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True);bpy.ops.import_scene.gltf(filepath=str(source))
    objects=[o for o in bpy.context.scene.objects if o.type=='MESH'];selected=[o for o in objects if o.name==policy['select_object']]
    if len(selected)!=1:raise ValueError('Source selection changed')
    for obj in objects:
        if obj not in selected:bpy.data.objects.remove(obj,do_unlink=True)
    bpy.context.view_layer.update();points=[o.matrix_world@Vector(c) for o in selected for c in o.bound_box]
    low=[min(p[i] for p in points) for i in range(3)];high=[max(p[i] for p in points) for i in range(3)];scale=policy.get('height_m',high[2]-low[2])/(high[2]-low[2])
    transform=Matrix.Translation(Vector((-(low[0]+high[0])*scale/2,-(low[1]+high[1])*scale/2,-low[2]*scale)))@Matrix.Scale(scale,4)
    for obj in selected:obj.matrix_world=transform@obj.matrix_world
    height=(high[2]-low[2])*scale;width=max(high[0]-low[0],high[1]-low[1])*scale
    centroid=None
    if a.depth_centroid:
        total=0.;weighted=np.zeros(3)
        for obj in selected:
            mesh=obj.data;mesh.calc_loop_triangles();points=np.empty(len(mesh.vertices)*3,dtype=np.float64);mesh.vertices.foreach_get('co',points);points=points.reshape(-1,3);matrix=np.asarray(obj.matrix_world);points=points@matrix[:3,:3].T+matrix[:3,3]
            triangles=np.empty(len(mesh.loop_triangles)*3,dtype=np.int32);mesh.loop_triangles.foreach_get('vertices',triangles);triangles=triangles.reshape(-1,3);materials=np.empty(len(mesh.loop_triangles),dtype=np.int32);mesh.loop_triangles.foreach_get('material_index',materials)
            slots=[i for i,m in enumerate(mesh.materials) if m.name.split('.')[0]=='fir_tree_01_twig'];mask=np.isin(materials,slots)
            p=points[triangles[mask]];area=np.linalg.norm(np.cross(p[:,1]-p[:,0],p[:,2]-p[:,0]),axis=1)*.5;total+=area.sum();weighted+=(p.mean(axis=1)*area[:,None]).sum(axis=0)
        if total<=0:raise ValueError('No actual source twig surface area for depth-centroid diagnostic')
        centroid=Vector(weighted/total)
    cards,bake=impostors(selected,a.output/'registered-bake',height,width,policy['impostor_resolution'],'CYCLES',normal_maps=True,reuse_bake=reuse['far'],additional_views=additional)
    original_positions=[];centroid_positions=[]
    if centroid is not None:
        for obj in cards:
            positions=np.empty(len(obj.data.vertices)*3,dtype=np.float64);obj.data.vertices.foreach_get('co',positions);positions=positions.reshape(-1,3);shifted=positions.copy()
            for polygon in obj.data.polygons:
                name=obj.data.materials[polygon.material_index].name;index=int(name.split('source_impostor_')[1].split('.')[0]);normal=np.asarray(bake['view_directions_blender'][index]);ids=list(polygon.vertices);offset=float((np.asarray(centroid)-positions[ids[0]])@normal);shifted[ids]+=normal*offset
            original_positions.append(positions);centroid_positions.append(shifted)
    unlit(selected);weights=unlit(cards)
    scene=bpy.context.scene;scene.cycles.samples=32;scene.cycles.seed=731;scene.cycles.use_animated_seed=False;scene.render.threads_mode='FIXED';scene.render.threads=8
    scene.cycles.transparent_max_bounces=64;scene.render.resolution_x=scene.render.resolution_y=a.resolution
    data=bpy.data.cameras.new('representation_audit');camera=bpy.data.objects.new('representation_audit',data);scene.collection.objects.link(camera);scene.camera=camera;data.type='ORTHO';data.ortho_scale=max(height,width)*1.16
    target=Vector((0,0,height/2));distance=max(height,width)*3;rows=[]
    for azimuth,elevation in [(0,0),(30,15),(0,30),(30,45),(0,70),(0,90)]:
        az=math.radians(azimuth);el=math.radians(elevation);direction=Vector((math.sin(az)*math.cos(el),-math.cos(az)*math.cos(el),math.sin(el)))
        camera.location=target+direction*distance;camera.rotation_euler=(-direction).to_track_quat('-Z','Y').to_euler()
        directions=[Vector(v) for v in bake['view_directions_blender']]
        scores=[abs(v.dot(direction)) if i<3 else v.dot(direction) for i,v in enumerate(directions)]
        legacy_best=max(range(4),key=lambda i:scores[i]);aerial_best=max(range(len(scores)),key=lambda i:scores[i])
        modes=['source','legacy_facing','legacy_best','aerial_best'] if additional else ['source','cards','cards_facing']
        if centroid is not None:modes.append('aerial_centroid')
        for mode in modes:
            if centroid is not None:
                for obj,positions in zip(cards,centroid_positions if mode=='aerial_centroid' else original_positions):obj.data.vertices.foreach_set('co',positions.ravel());obj.data.update()
            for obj in selected:obj.hide_render=mode!='source'
            for obj in cards:obj.hide_render=mode=='source'
            for name,weight in weights:
                index=int(name.split('source_impostor_')[1].split('.')[0]);facing=abs(directions[index].dot(direction));u=max(0,min(1,(facing-.15)/.45))
                if mode in ['cards_facing','legacy_facing']:value=u*u*(3-2*u) if index<4 else 0
                elif mode=='legacy_best':value=float(index==legacy_best)
                elif mode in ['aerial_best','aerial_centroid']:value=float(index==aerial_best)
                else:value=1
                weight.inputs[1].default_value=value
            file=a.output/f'az{azimuth}-el{elevation}-{mode}.png';scene.render.filepath=str(file);bpy.ops.render.render(write_still=True)
            rows.append({'azimuth_degrees':azimuth,'elevation_degrees':elevation,'mode':mode,'file':str(file),'sha256':sha(file),'selected_view':legacy_best if mode=='legacy_best' else aerial_best if mode in ['aerial_best','aerial_centroid'] else None})
            report={'scope':'Same actual source tree, normalization, source RGB/opacity and orthographic camera; independent Cycles transparency. cards_facing applies the runtime smoothstep(.15,.6,abs(dot(card_normal,view))) per plane. No mip minification/TAA, shader, lighting, forest density or performance certification.',
                'asset':a.asset,'manifest_sha256':sha(manifest_path),'source_sha256':sha(source),'script_sha256':sha(__file__),'helper_sha256':sha(HERE/'vegetation_lod.py'),'blender':bpy.app.version_string,'resolution':a.resolution,'samples':32,'transparent_max_bounces':64,'source_dimensions_m':{'height':height,'width':width},'validated_reused_bake':reuse['far'],'captures':rows,
                'alternative_source_manifest':{'file':str(a.aerial_source_manifest),'sha256':sha(a.aerial_source_manifest)} if alternative else None,
                'source_twig_area_centroid_blender':list(centroid) if centroid is not None else None,
                'centroid_scope':'Area-weighted actual source twig triangles, not measured visible depth or a general depth map. Moving a plane only along its source-view normal preserves its original orthographic projection. This isolates mean-depth placement from source image changes.' if centroid is not None else None,
                'view_selection_scope':'Best-view tests show one static source-derived plane chosen by camera direction. No game sampler, source-yaw/stream integration, shadows, blending or temporal transition acceptance.' if additional else None}
            (a.output/'partial-report.json').write_text(json.dumps(report,indent=2))
            print('REPRESENTATION_AUDIT',azimuth,elevation,mode,flush=True)
    (a.output/'report.json').write_text(json.dumps(report,indent=2));print('REPRESENTATION_AUDIT_COMPLETE',flush=True)


if __name__=='__main__':main()
