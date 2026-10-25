"""Prepare an independent indexed-raster engine/shader fork with direct64-bit IDs.

The upstream checkout, running clients and their shader caches are never edited.
Compute visibility shading,mesh shaders and path tracing are outside this mode.
"""
from pathlib import Path
import argparse,hashlib,json,re,shutil,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json,sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True)
    p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);engine=out/'engine';shader=out/'shader-source'
    profile=json.loads(a.profile.read_text(encoding='utf8'));original=Path(profile['shader_source'])
    def ignored(directory,names):
        skip={'.git','.github','.vs','build','Build'}
        if Path(directory).resolve()==a.engine.resolve():skip|={'Content','Samples'}
        return set(names)&skip
    shutil.copytree(a.engine,engine,ignore=ignored);shutil.copytree(original,shader)
    changes=[]
    def patch(file,old,new,count=1):
        text=file.read_text(encoding='utf8');found=text.count(old)
        if found!=count:raise ValueError(f'Patch anchor changed:{file.name}:{old[:60]!r}:{found}!={count}')
        file.write_text(text.replace(old,new),encoding='utf8');changes.append({'file':str(file.relative_to(out)),'anchor':old[:80],'count':count})
    patch(engine/'WickedEngine/wiRenderer.h','format_idbuffer = wi::graphics::Format::R32_UINT','format_idbuffer = wi::graphics::Format::R32G32_UINT')
    scene=engine/'WickedEngine/wiScene.cpp';text=scene.read_text(encoding='utf8')
    matches=list(re.finditer(r'meshletAllocator\.fetch_add\([^;]+?\)',text))
    if len(matches)!=3:raise ValueError('Unexpected global meshlet allocation sites')
    text=re.sub(r'meshletAllocator\.fetch_add\([^;]+?\)','0u /* direct64-bit raster IDs need no global meshlet lookup */',text)
    scene.write_text(text,encoding='utf8');changes.append({'file':str(scene.relative_to(out)),'meshlet_allocation_sites_disabled':3})
    patch(scene,'desc.size = desc.stride * meshletCount * 2;','desc.size = uint64_t(desc.stride) * meshletCount * 2;')
    patch(engine/'WickedEngine/wiRenderer.cpp','PushBarrier(GPUBarrier::Buffer(&vis.scene->meshletBuffer, ResourceState::SHADER_RESOURCE, ResourceState::UNORDERED_ACCESS));',
          'if (vis.scene->meshletBuffer.IsValid()) PushBarrier(GPUBarrier::Buffer(&vis.scene->meshletBuffer, ResourceState::SHADER_RESOURCE, ResourceState::UNORDERED_ACCESS));')
    globals=shader/'globals.hlsli'
    # The existing uint4 SRV table works in SM6.0 too. R32G32_UINT suppliesxy;
    # readers explicitly retain only those two components. No new root binding.
    patch(globals,'#define texture_primitiveID bindless_textures_uint[','#define texture_primitiveID bindless_textures_uint4[')
    patch(globals,'\tinline void unpack2(uint2 value)','\tinline void unpack(uint2 value) { unpack2(value); }\n\tinline void unpack2(uint2 value)')
    # The direct ID retains primitiveIndex32,instanceIndex24,subsetIndex8.
    obj=shader/'objectHF.hlsli'
    patch(obj,'uint GetPrimitiveID()','uint2 GetPrimitiveID()')
    patch(obj,'return prim.pack(GetInstance(), GetMesh());','return prim.pack2();')
    patch(obj,'uint primitiveID : PRIMITIVEID;','nointerpolation uint2 primitiveID : PRIMITIVEID;')
    patch(obj,'uint main(PixelInput input APPEND_COVERAGE_OUTPUT) : SV_Target','uint2 main(PixelInput input APPEND_COVERAGE_OUTPUT) : SV_Target')
    for name in ['hairparticleHF.hlsli','impostorHF.hlsli']:
        file=shader/name;text=file.read_text(encoding='utf8');text,n=re.subn(r'\buint(\s+primitiveID\s*:)',r'uint2\1',text)
        if n!=1:raise ValueError('Unexpected particle primitive varying')
        file.write_text(text,encoding='utf8')
    patch(shader/'hairparticleVS.hlsl','prim.pack(inst, geometry)','prim.pack2()')
    patch(shader/'impostorVS.hlsl','prim.pack()','prim.pack2()')
    for name in ['hairparticlePS_prepass.hlsl','impostorPS_prepass.hlsl']:
        patch(shader/name,'uint main(','uint2 main(')
    # Uniform tile records remain unchanged. Only all-sky tiles use that path;
    # every geometry tile uses the existing divergent list with full IDs.
    analyze=shader/'visibility_analyzeCS.hlsl'
    for before,after,n in [('Texture2DMS<uint>','Texture2DMS<uint2>',1),('Texture2D<uint>','Texture2D<uint2>',2),
        ('groupshared uint group_primitiveID','groupshared uint2 group_primitiveID',1),
        ('uint primitiveID =','uint2 primitiveID =',2),
        ('(primitiveID == group_primitiveID)','(all(primitiveID == 0) && all(group_primitiveID == 0))',1),
        ('tile.primitiveID = group_primitiveID;','tile.primitiveID = 0; // uniform list contains sky only',1)]:patch(analyze,before,after,n)
    for name in ['visibility_resolveCS.hlsl','visibility_surfaceCS.hlsl','visibility_shadeCS.hlsl','visibility_velocityCS.hlsl']:
        file=shader/name;text=file.read_text(encoding='utf8')
        text=text.replace('#define PRIMITIVEID_FROM_MESHLET_OPTIMIZED','// Direct IDs load the actual geometry material,not a meshlet lookup.')
        text=re.sub(r'const uint primitiveID = (primitive_tile\.primitiveID|tile\.shaderType_or_primitiveID);',
                    'const uint2 primitiveID = 0; // geometry never enters uniform list',text)
        text=text.replace('const uint primitiveID =','const uint2 primitiveID =')
        text=text.replace('primitiveID != 0','any(primitiveID != 0)').replace('primitiveID == 0','all(primitiveID == 0)')
        file.write_text(text,encoding='utf8')
    for name in ['mesh_blend_prepareCS.hlsl','mesh_blend_expandCS.hlsl','rtaoCS.hlsl','surfel_coverageCS.hlsl']:
        file=shader/name;text=file.read_text(encoding='utf8')
        text=text.replace('uint primitiveID = texture_primitiveID','uint2 primitiveID = texture_primitiveID')
        text=text.replace('primitiveID == 0','all(primitiveID == 0)').replace('primitiveID != 0','any(primitiveID != 0)')
        file.write_text(text,encoding='utf8')
    # Fresh cache prevents a legacy32-bit producer being mixed with64-bit readers.
    shutil.copyfile(ROOT/'game/shaders/bvrGroundHF.hlsli',shader/'bvrGroundHF.hlsli')
    cache=out/'shader-cache';cache.mkdir()
    profile.update(shader_source=str(shader),shader_cache=str(cache),wide_primitive_id_raster=True)
    write_json(out/'visual-profile.json',profile)
    modified=['wiRenderer.h','wiRenderer.cpp','wiScene.cpp']
    manifest={'schema_version':1,'mode':'direct64_indexed_raster','engine_revision':subprocess.check_output(['git','-C',str(a.engine),'rev-parse','HEAD'],text=True).strip(),
        'source_engine':str(a.engine.resolve()),'source_profile_sha256':sha(a.profile),'tool_sha256':sha(__file__),
        'engine_changes':[{'file':name,'source_sha256':sha(a.engine/'WickedEngine'/name),'sha256':sha(engine/'WickedEngine'/name)} for name in modified],
        'shader_files':[{'file':str(file.relative_to(shader)),'sha256':sha(file)} for file in sorted(shader.rglob('*')) if file.is_file()],
        'patches':changes,'scope':'Independent source fork. All indexed geometry retained. Direct primitive IDs avoid global meshlet lookup. Compute visibility shading,mesh shaders,path tracing and Vulkan are not enabled in this mode.'}
    write_json(engine/'bvr-wide-primitive.json',manifest);write_json(out/'preparation.json',manifest)
    from game.tools.prepare_runtime_diagnostics import prepare_engine
    prepare_engine(engine)
    print('WIDE_PRIMITIVE_SOURCES_PREPARED',out,flush=True)
if __name__=='__main__':main()
