"""Blender-only adapter for verified WT oak LOD0 imports and source color/alpha.

Run Blender --background --python-exit-code 1 --python THIS_FILE -- --help.
This adapter supports the observed oak/bark material family, not arbitrary Dagor shaders.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,sys
import bpy

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--models',type=Path,required=True,help='import_wt_models.py report.json')
    p.add_argument('--textures',type=Path,required=True,help='Texture report containing tree_oak maps')
    p.add_argument('--bark-textures',type=Path,required=True,help='Texture report containing tree_tilia bark')
    p.add_argument('--model',required=True,help='Exact exported resource name, without _0 suffix')
    p.add_argument('--id',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:])
    if not re.fullmatch(r'[A-Za-z0-9_-]+',a.id):p.error('Asset ID must contain letters, digits, underscores or dashes')
    imported=json.loads(a.models.read_text(encoding='utf8'))
    row=next(r for r in imported['models'] if r['name']==a.model and r['status']=='exported' and r['lod']==0)
    source=Path(row['obj'])
    for key in ('obj','mtl'):
        if sha(row[key])!=row[key+'_sha256']:raise ValueError('Imported model changed: '+row[key])
    def texture(report,pack,name):
        data=json.loads(report.read_text(encoding='utf8'))
        row=next(r for r in data['textures'] if r['status']=='decoded' and Path(r['source']).parent.name==pack and Path(r['source']).stem==name)
        file=Path(row['png'])
        if sha(file)!=row['png_sha256']:raise ValueError('Imported texture changed: '+str(file))
        return file
    color=texture(a.textures,'tree_oak','tree_oak_branches_tex_d')
    alpha=texture(a.textures,'tree_oak','tree_oak_branches_tex_a')
    bark=texture(a.bark_textures,'tree_tilia','tilia_bark_a_tex_d')
    a.output.mkdir(parents=True,exist_ok=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.wm.obj_import(filepath=str(source.resolve()),forward_axis='NEGATIVE_Z',up_axis='Y')
    meshes=[o for o in bpy.context.scene.objects if o.type=='MESH']
    if sum(len(p.vertices)-2 for o in meshes for p in o.data.polygons)!=row['triangles']:raise ValueError('OBJ import changed source triangle count')
    materials={m for o in meshes for m in o.data.materials}
    for mat in materials:
        leaf=mat.name.startswith('tree_oak_branches')
        if not leaf and not mat.name.startswith('tilia_bark_a'):raise ValueError('Unsupported oak source material: '+mat.name)
        mat.use_nodes=True;mat.node_tree.nodes.clear();nodes=mat.node_tree.nodes;links=mat.node_tree.links
        output=nodes.new('ShaderNodeOutputMaterial');bsdf=nodes.new('ShaderNodeBsdfPrincipled')
        links.new(bsdf.outputs['BSDF'],output.inputs['Surface']);bsdf.inputs['Roughness'].default_value=.9;bsdf.inputs['Metallic'].default_value=0
        tex=nodes.new('ShaderNodeTexImage');tex.image=bpy.data.images.load(str(color if leaf else bark),check_existing=True)
        tex.image.colorspace_settings.name='sRGB';links.new(tex.outputs['Color'],bsdf.inputs['Base Color'])
        if leaf:
            mask=nodes.new('ShaderNodeTexImage');mask.image=bpy.data.images.load(str(alpha),check_existing=True)
            mask.image.colorspace_settings.name='Non-Color';links.new(mask.outputs['Color'],bsdf.inputs['Alpha'])
            mat.surface_render_method='DITHERED';mat.use_backface_culling=False
    bpy.context.view_layer.update();bpy.ops.object.select_all(action='SELECT');target=a.output/(a.id+'-source.glb')
    bpy.ops.export_scene.gltf(filepath=str(target),export_format='GLB',use_selection=True,export_animations=False,export_texcoords=True,export_normals=True)
    raw=target.read_bytes();size=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+size])
    for mat in doc['materials']:
        if mat['name'].startswith('tree_oak_branches'):mat.update(alphaMode='MASK',alphaCutoff=127/255,doubleSided=True)
    payload=json.dumps(doc,separators=(',',':')).encode();payload+=b' '*(-len(payload)%4);rest=raw[20+size:]
    target.write_bytes(struct.pack('<III',0x46546c67,2,20+len(payload)+len(rest))+struct.pack('<II',len(payload),0x4e4f534a)+payload+rest)
    conversion={'id':a.id,'source_obj':str(source),'source_obj_sha256':sha(source),'file':str(target.resolve()),'sha256':sha(target),
        'converter_sha256':sha(__file__),'model_import_report_sha256':sha(a.models),
        'triangles':row['triangles'],'object_local_dimensions_m':[{'name':o.name,'dimensions':list(o.dimensions)} for o in meshes],
        'source_native_normals':row.get('source_native_normals'),
        'scope':'Original LOD0 OBJ geometry at source scale/pivot, with axis conversion. '+
                ('Original packed source vertex normals restored by exact vertex indices. ' if row.get('source_native_normals') else 'DAE recomputes normals. ')+
                'Positions/UV retain OBJ rounding. Original diffuse RGB and dedicated alpha. Roughness0.9 approximation;tangent normal/PBR maps,wind,pivot deformation,dissolve and subsurface not reconstructed.'}
    provider={'source':'user-local-war-thunder','source_url':'local://WarThunder/'+Path(row['pack']).name,
        'license':'user-owned-local-War-Thunder-resource','distribution_allowed':False,
        'files':[{'path':target.name,'sha256':sha(target),'bytes':target.stat().st_size}],
        'source_model':row,'source_images':[{'file':str(f),'sha256':sha(f)} for f in (color,alpha,bark)],
        'provenance':conversion,'license_evidence':[]}
    (a.output/'conversion.json').write_text(json.dumps(conversion,indent=2),encoding='utf8')
    (a.output/'provider.json').write_text(json.dumps(provider,indent=2),encoding='utf8')
    print('WT_OAK_SOURCE_GLB',json.dumps(conversion),flush=True)

if __name__=='__main__':main()
