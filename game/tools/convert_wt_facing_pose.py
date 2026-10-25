"""Blender: source-facing tree geometry, original color/alpha and optional native payload.

The native payload supports camera facing in the matching renderer; wind and
packed source normals are not reconstructed. Static exports are diagnostics.
Run with Blender --background --python-exit-code 1 --python THIS -- ARGS.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys
import bpy

def sha(file):return hashlib.sha256(Path(file).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',type=Path,required=True);p.add_argument('--textures',type=Path,required=True)
    p.add_argument('--names',nargs='+',required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--native-facing',action='store_true',help='Encode original leaf offsets for the native CPU facing updater; requires the corresponding renderer interface')
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);models=json.loads(a.models.read_text());textures=json.loads(a.textures.read_text())
    imported={Path(t['source']).stem:t for t in textures['textures'] if t['status']=='decoded'}
    a.output.mkdir(parents=True,exist_ok=False);results=[]
    for name in a.names:
        if not re.fullmatch('[A-Za-z0-9_-]+',name):raise ValueError('Unsupported model name')
        row=next(r for r in models['models'] if r['name']==name and r['status']=='exported')
        if row.get('facing_leaf_pose',{}).get('pose')!='identity_source_axes_no_animation':raise ValueError('Expected explicit frozen source pose')
        for key in ('obj','mtl'):
            if sha(row[key])!=row[key+'_sha256']:raise ValueError('Changed source '+key)
        mapping={};current=None
        for line in Path(row['mtl']).read_text().splitlines():
            words=line.split()
            if words and words[0]=='newmtl':current=words[1]
            elif words and words[0]=='map_Kd':mapping[current]=Path(words[1]).stem
        used={}
        for material in row['materials']:
            texture=imported[mapping[material]]
            if sha(texture['png'])!=texture['png_sha256']:raise ValueError('Changed source texture')
            used[material]=texture
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.wm.obj_import(filepath=str(Path(row['obj']).resolve()),forward_axis='NEGATIVE_Z',up_axis='Y')
        meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
        if sum(len(p.vertices)-2 for o in meshes for p in o.data.polygons)!=row['triangles']:raise ValueError('Source triangle count changed')
        if a.native_facing:
            import numpy as np
            pose=row['facing_leaf_pose'];payload=np.load(pose['source_payload'])
            if sha(pose['source_payload'])!=pose['source_payload_sha256']:raise ValueError('Source leaf payload changed')
            centers=[];deltas=[]
            for key in payload.files:
                if key.endswith('_center_half4'):
                    c=payload[key][:,:3].astype(float);d=payload[key.replace('_center_half4','_offset_half4')][:,:3].astype(float)
                    d[:,2]*=-1;centers.extend(c.tolist());deltas.extend(d.tolist())
            centers=np.asarray(centers);deltas=np.asarray(deltas);frozen=centers+deltas
            for obj in meshes:
                # Bake the imported OBJ axis node, then keep the glTF node
                # identity so source-center reconstruction has one clear basis.
                bpy.ops.object.select_all(action='DESELECT');obj.select_set(True);bpy.context.view_layer.objects.active=obj
                bpy.ops.object.transform_apply(location=True,rotation=True,scale=True)
                uv=obj.data.uv_layers.new(name='BVR_FACING_DELTA_XY')
                colors=obj.data.color_attributes.new(name='BVR_FACING_HALF_Z',type='FLOAT_COLOR',domain='CORNER')
                obj.data.color_attributes.active_color=colors
                for poly in obj.data.polygons:
                    leaf=obj.data.materials[poly.material_index].name in ('trees_all_atlas','kh_gol_trees_all')
                    for loop_index in poly.loop_indices:
                        if not leaf:colors.data[loop_index].color=(1,1,1,1);continue
                        vertex=obj.data.vertices[obj.data.loops[loop_index].vertex_index]
                        # OBJ stores a reflected source Z. The explicit import
                        # basis maps source coordinates to Blender (X,Z,Y).
                        point=np.asarray([vertex.co.x,vertex.co.z,vertex.co.y])
                        distances=np.linalg.norm(frozen-point,axis=1);index=int(distances.argmin())
                        if distances[index]>.0001:raise ValueError('Source leaf corner could not be matched after axis conversion: '+str((list(vertex.co),point.tolist(),frozen[index].tolist(),float(distances[index]))))
                        dx,dy,dz=deltas[index];bits=struct.unpack('<H',struct.pack('<e',float(dz)))[0]
                        uv.data[loop_index].uv=(float(dx),1-float(dy))
                        colors.data[loop_index].color=((bits&255)/255,(bits>>8)/255,165/255,1)
        leaves=[]
        for mat in {m for o in meshes for m in o.data.materials}:
            texture=used[mat.name];leaf=mat.name in ('trees_all_atlas','kh_gol_trees_all')
            if not leaf and 'bark' not in mat.name:raise ValueError('Unsupported source material '+mat.name)
            mat.use_nodes=True;mat.node_tree.nodes.clear();nodes=mat.node_tree.nodes;links=mat.node_tree.links
            output=nodes.new('ShaderNodeOutputMaterial');bsdf=nodes.new('ShaderNodeBsdfPrincipled');links.new(bsdf.outputs['BSDF'],output.inputs['Surface'])
            bsdf.inputs['Roughness'].default_value=.9
            tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(texture['png'],check_existing=True);tex.image.colorspace_settings.name='sRGB';links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
            if leaf:
                links.new(tex.outputs['Alpha'],bsdf.inputs['Alpha']);mat.surface_render_method='DITHERED';mat.use_backface_culling=False;leaves.append(mat.name)
        target=a.output/(name+'-frozen-source.glb');bpy.ops.object.select_all(action='SELECT')
        color_options={'export_vertex_color':'NAME','export_vertex_color_name':'BVR_FACING_HALF_Z'} if a.native_facing else {}
        bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_animations=False,export_texcoords=True,export_normals=True,**color_options)
        raw=target.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size])
        for mat in doc['materials']:
            if mat['name'] in leaves:mat.update(alphaMode='MASK',alphaCutoff=127/255,doubleSided=True)
        payload=json.dumps(doc,separators=(',',':')).encode();payload+=b' '*(-len(payload)%4);rest=raw[20+size:]
        target.write_bytes(struct.pack('<III',0x46546c67,2,20+len(payload)+len(rest))+struct.pack('<II',len(payload),0x4e4f534a)+payload+rest)
        if a.native_facing:
            sidecar=target.with_suffix('.facing.json')
            sidecar.write_text(json.dumps({'schema_version':1,'encoding':'uv1_delta_xy_rg_half_z_v1','leaf_materials':leaves,
                'model_sha256':sha(target),'source_leaf_payload_sha256':row['facing_leaf_pose']['source_payload_sha256'],
                'scope':'Original source centers and offsets, camera facing with wind held at its no-animation basis. Runtime rejects rotated instances until a per-instance facing path is implemented.'},indent=2))
        results.append({'name':name,'file':str(target.resolve()),'sha256':sha(target),'triangles':row['triangles'],
            'source_obj_sha256':row['obj_sha256'],'source_bounds_y_up':row['source_bounds_y_up'],
            'source_images':[{'file':t['png'],'sha256':t['png_sha256']} for t in used.values()],
            'facing_leaf_pose':row['facing_leaf_pose']})
        if a.native_facing:results[-1].update(native_facing_sidecar=str(sidecar.resolve()),native_facing_sidecar_sha256=sha(sidecar))
        print('WT_FROZEN_SOURCE_GLB',name,sha(target),flush=True)
    report={'models':results,'converter_sha256':sha(__file__),'model_report_sha256':sha(a.models),'texture_report_sha256':sha(a.textures),
        'rendering_mode':'native_cpu_camera_facing_v1' if a.native_facing else 'static_identity_pose',
        'scope':'Original source corners and offsets, original diffuse RGB and source alpha. Native mode requires the corresponding renderer and upright unrotated uniform-scale placements. Wind, packed source normals, source tint and full shader equivalence remain unimplemented. Private authoring asset, not a finished map release.'}
    (a.output/'report.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__':main()
