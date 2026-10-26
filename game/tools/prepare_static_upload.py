"""Persist immutable grounded uploads with stable geometry addresses.

Requires the checked inline-ground fork. Dynamic objects use the original
update, and LOD, layout, entity compaction or upload-buffer changes invalidate.
"""
from pathlib import Path
import argparse,hashlib,json

def prepare(engine):
    engine=Path(engine);path=engine/'WickedEngine/wiScene.cpp';meta=json.loads((engine/'bvr-inline-ground-bounds.json').read_text())
    text=path.read_text();assert hashlib.sha256(path.read_bytes()).hexdigest()==meta['output_sha256']
    before=hashlib.sha256(path.read_bytes()).hexdigest()
    def replace(a,b):
        nonlocal text
        assert text.count(a)==1,a;text=text.replace(a,b,1)
    replace('std::array<float,4> sphere{};', '''std::array<float,4> sphere{};
        Entity cpu_mesh=INVALID_ENTITY;
        std::array<Entity,wi::graphics::GraphicsDevice::GetBufferCount()> gpu_meshes{};''')
    replace('std::vector<const BvrGroundedNode*> slots;', '''std::vector<BvrGroundedNode*> slots;
        std::array<wi::graphics::GPUBuffer,wi::graphics::GraphicsDevice::GetBufferCount()> uploads;
        uint64_t geometry_layout=0;
        bool keep_upload(const Scene& scene,size_t i,uint32_t frame) const {
            if(i>=slots.size()||i>=scene.objects.GetCount())return false;
            auto node=slots[i];return node&&node->entity==scene.objects.GetEntity(i)&&
                node->cpu_mesh==scene.objects[i].meshID&&node->gpu_meshes[frame]==scene.objects[i].meshID;
        }''')
    # Stable per-mesh prefix sums replace a scheduling-dependent atomic order.
    replace('geometryAllocator.store(0u);', '''geometryAllocator.store(0u);
            uint32_t bvr_geometry_offset=0;
            uint64_t bvr_layout=1469598103934665603ull;
            for(size_t i=0;i<meshes.GetCount();++i){
                auto& mesh=meshes[i];mesh.geometryOffset=bvr_geometry_offset;
                bvr_geometry_offset+=uint32_t(mesh.subsets.size());
                bvr_layout=(bvr_layout^uint64_t(meshes.GetEntity(i)))*1099511628211ull;
                bvr_layout=(bvr_layout^uint64_t(mesh.subsets.size()))*1099511628211ull;
            }
            geometryAllocator.store(bvr_geometry_offset);
            if(bvr_upload_data->geometry_layout!=bvr_layout){
                bvr_upload_data->geometry_layout=bvr_layout;
                for(auto& node:bvr_upload_data->entries){node.cpu_mesh=INVALID_ENTITY;node.gpu_meshes.fill(INVALID_ENTITY);}
            }''')
    replace('mesh.geometryOffset = geometryAllocator.fetch_add((uint32_t)mesh.subsets.size());','// Geometry prefix offsets were assigned deterministically before dispatch.')
    anchor='instanceArrayMapped = (ShaderMeshInstance*)instanceUploadBuffer[cpu_gpu_mapped_resource_index].mapped_data;'
    replace(anchor,anchor+'''
        auto& bvr_upload_slot=bvr_grounded_scenes[this];
        if(!bvr_upload_slot)bvr_upload_slot=std::make_shared<BvrGroundedScene>();
        auto bvr_upload_data=bvr_upload_slot;
        const auto bvr_upload_frame=cpu_gpu_mapped_resource_index;
        if(bvr_upload_data->uploads[bvr_upload_frame].internal_state.get()!=instanceUploadBuffer[bvr_upload_frame].internal_state.get()){
            bvr_upload_data->uploads[bvr_upload_frame]=instanceUploadBuffer[bvr_upload_frame];
            for(auto& node:bvr_upload_data->entries)node.gpu_meshes[bvr_upload_frame]=INVALID_ENTITY;
        }
''')
    replace('std::memcpy(instanceArrayMapped + i, &shader_mesh_instance_null, sizeof(shader_mesh_instance_null));', '''if(!bvr_upload_data->keep_upload(*this,i,bvr_upload_frame))
                        std::memcpy(instanceArrayMapped + i, &shader_mesh_instance_null, sizeof(shader_mesh_instance_null));''')
    replace('const BvrGroundedNode* bvr_ground=nullptr;','BvrGroundedNode* bvr_ground=nullptr;')
    anchor='AABB& aabb = aabb_objects[args.jobIndex];'
    replace(anchor,anchor+'''
            if(bvr_ground_data->keep_upload(*this,args.jobIndex,cpu_gpu_mapped_resource_index)){
                bvr_ground_data->applied[args.jobIndex]=1;
                object.occlusion.occlusionHistory=~0u;
                AABB& shared_bounds=parallel_bounds[args.groupID];
                shared_bounds=args.isFirstJobInGroup?aabb:AABB::Merge(shared_bounds,aabb);
                return;
            }
''')
    anchor='std::memcpy(instanceArrayMapped + args.jobIndex, &inst, sizeof(inst));'
    replace(anchor,'''if(bvr_ground){inst.transformPrev=inst.transform;matrix_objects_prev[args.jobIndex]=matrix_objects[args.jobIndex];}
                '''+anchor+'''
                if(bvr_ground){
                    bvr_ground->cpu_mesh=object.meshID;
                    bvr_ground->gpu_meshes[cpu_gpu_mapped_resource_index]=object.meshID;
                }
''')
    path.write_text(text,encoding='utf8')
    result={'input_sha256':before,'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':__doc__}
    (engine/'bvr-static-upload.json').write_text(json.dumps(result,indent=2))
    for name in ['bvr-inline-ground-bounds.json','bvr-static-scenery-cache.json']:
        marker=json.loads((engine/name).read_text());marker['inline_only_output_sha256']=meta['output_sha256'];marker['output_sha256']=result['output_sha256'];marker['static_upload_patch']='bvr-static-upload.json'
        (engine/name).write_text(json.dumps(marker,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--engine',type=Path,required=True);prepare(p.parse_args().engine)
