"""Cache single-LOD mesh material classifications once per engine scene update.

Per-object transforms, previous matrices, GPU data, visibility, LOD and physical
simulation stay live. Multi-LOD meshes use their selected-LOD classification.
"""
from pathlib import Path
import argparse,hashlib,json,shutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def prepare(engine):
    engine=Path(engine).resolve();file=engine/'WickedEngine/wiScene.cpp';marker=engine/'bvr-scene-material-cache.json'
    if marker.exists():
        data=json.loads(marker.read_text(encoding='utf8'))
        if sha(file)!=data['output_sha256']:raise ValueError('Prepared scene source changed')
        return data
    text=file.read_text(encoding='utf8');start=text.index('\tvoid Scene::RunObjectUpdateSystem(');end=text.index('\tvoid Scene::RunCameraUpdateSystem(',start)
    section=text[start:end];begin=section.index('\t\t\t\tunion SortBits');stop=section.index('\t\t\t\tobject.sort_bits = sort_bits.value;',begin)+len('\t\t\t\tobject.sort_bits = sort_bits.value;')
    union=section[begin:section.index('\t\t\t\tsort_bits.bits.tessellation',begin)]
    union=union.replace('} sort_bits;','};')
    helper=union+'''
        struct BvrMeshMaterialState {
            uint32_t sort=0,filter=0;
            bool reflection=false,blend=false,valid=false;
        };
        auto classify=[this](const MeshComponent& mesh,uint32_t lod){
            BvrMeshMaterialState state;
            SortBits sort_bits={};
            sort_bits.bits.tessellation=mesh.GetTessellationFactor()>0;
            sort_bits.bits.doublesided=mesh.IsDoubleSided();
            uint32_t first=0,last=0;mesh.GetLODSubsetRange(lod,first,last);
            for(uint32_t i=first;i<last;++i){
                const auto* material=materials.GetComponent(mesh.subsets[i].materialID);
                if(!material)continue;
                state.filter|=material->GetFilterMask();
                state.reflection|=material->HasPlanarReflection();
                state.blend|=material->GetMeshBlend()>0;
                sort_bits.bits.shadertype|=1<<material->shaderType;
                sort_bits.bits.blendmode|=1<<material->GetBlendMode();
                sort_bits.bits.doublesided|=material->IsDoubleSided();
                sort_bits.bits.alphatest|=material->IsAlphaTestEnabled();
                const int shader=material->GetCustomShaderID();
                if(shader>=0)sort_bits.bits.customshader|=1u<<(uint32_t(shader)&7u);
            }
            state.sort=sort_bits.value;state.valid=true;return state;
        };
        // Owned by the dispatch closure because scene jobs outlive this method.
        // Rebuilt after material-update dependencies every frame, so material
        // edits, resource compaction and map changes never use stale entries.
        auto bvr_materials=std::make_shared<wi::vector<BvrMeshMaterialState>>(meshes.GetCount());
        for(size_t i=0;i<meshes.GetCount();++i)if(meshes[i].GetLODCount()==1)(*bvr_materials)[i]=classify(meshes[i],0);
'''
    anchor='\t\twi::jobsystem::Dispatch(ctx, (uint32_t)objects.GetCount(), small_subtask_groupsize, [&](wi::jobsystem::JobArgs args) {'
    if section.count(anchor)!=1:raise ValueError('Object dispatch anchor changed')
    replacement='''
                uint32_t first_subset=0,last_subset=0;
                mesh.GetLODSubsetRange(object.lod,first_subset,last_subset);
                const auto cached=(*bvr_materials)[object.mesh_index];
                const auto state=cached.valid?cached:classify(mesh,object.lod);
                SortBits sort_bits={};sort_bits.value=state.sort;
                sort_bits.bits.sort_priority=object.sort_priority;
                object.sort_bits=sort_bits.value;
                object.filterMaskDynamic=state.filter;
                object.SetRequestPlanarReflection(state.reflection);
                object.mesh_blend_required=state.blend;'''
    section=section[:begin]+replacement+section[stop:]
    # classify contains only a Scene pointer; capture its value for async jobs.
    section=section.replace(anchor,helper+anchor.replace('[&]','[&, bvr_materials, classify]'))
    output=text[:start]+section+text[end:];backup=file.with_suffix('.cpp.before-bvr-material-cache');shutil.copy2(file,backup)
    file.write_text(output,encoding='utf8');data={'schema_version':1,'source':str(file),'backup':str(backup),'source_sha256':sha(backup),'output_sha256':sha(file),'tool_sha256':sha(__file__),
        'scope':'Per-frame per-mesh material masks/sort classification for single-LOD meshes; selected-LOD fallback otherwise. Zero-initialize sort bits. Object-specific priority, transforms, visibility and GPU writes remain per object. Build and rendered verification still required.'}
    marker.write_text(json.dumps(data,indent=2),encoding='utf8');return data

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True);a=p.parse_args();print(json.dumps(prepare(a.engine),indent=2))
