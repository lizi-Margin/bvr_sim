"""Put checked static-tree bounds and source-stream IDs in the normal scene upload.

This replaces the renderer's second CPU bounds walk and second GPU instance copy
for immutable grounded scenery. Matrices, geometry, materials and all unregistered
objects retain the ordinary engine update. Call registration again after edits.
"""
from pathlib import Path
import argparse,hashlib,json

GLOBAL=r'''
    struct BvrGroundedNode {
        Entity entity=INVALID_ENTITY;
        AABB bounds;
        std::array<uint32_t,2> stream{};
        std::array<float,4> sphere{};
    };
    struct BvrGroundedScene {
        std::vector<BvrGroundedNode> entries;
        std::unordered_map<Entity,size_t> indices;
        std::vector<const BvrGroundedNode*> slots;
        std::vector<uint8_t> applied;
    };
    static std::unordered_map<Scene*,std::shared_ptr<BvrGroundedScene>> bvr_grounded_scenes;
    void SetBvrStaticScenery(Scene& scene,const Entity*,size_t count) {
        if(count)throw std::runtime_error("Use checked grounded-node registration, not the discarded pose cache");
        bvr_grounded_scenes[&scene]=std::make_shared<BvrGroundedScene>();
    }
    void SetBvrStaticGroundBounds(Scene& scene,const Entity* entities,const float* boxes,
                                 const uint32_t* streams,const float* spheres,size_t count) {
        auto data=std::make_shared<BvrGroundedScene>();data->entries.resize(count);
        data->slots.resize(scene.objects.GetCount(),nullptr);
        for(size_t i=0;i<count;++i){
            auto& node=data->entries[i];node.entity=entities[i];
            node.bounds._min={boxes[i*6],boxes[i*6+1],boxes[i*6+2]};
            node.bounds._max={boxes[i*6+3],boxes[i*6+4],boxes[i*6+5]};
            node.stream={streams[i*2],streams[i*2+1]};
            node.sphere={spheres[i*4],spheres[i*4+1],spheres[i*4+2],spheres[i*4+3]};
            data->indices.emplace(node.entity,i);
            const auto index=scene.objects.GetIndex(node.entity);
            if(index==size_t(-1))throw std::runtime_error("Grounded object disappeared during registration");
            data->slots[index]=&node;
        }
        bvr_grounded_scenes[&scene]=std::move(data);
    }
    std::map<std::string,uint64_t> GetBvrStaticSceneryState(Scene& scene) {
        auto found=bvr_grounded_scenes.find(&scene);if(found==bvr_grounded_scenes.end())return {};
        uint64_t applied=0;for(auto value:found->second->applied)applied+=value;
        return {{"inline_ground_bounds",1},{"registered",found->second->entries.size()},{"applied_last_frame",applied}};
    }
'''

PRE=r'''
        auto& bvr_ground_slot=bvr_grounded_scenes[this];
        if(!bvr_ground_slot)bvr_ground_slot=std::make_shared<BvrGroundedScene>();
        auto bvr_ground_data=bvr_ground_slot;
        bvr_ground_data->slots.resize(objects.GetCount(),nullptr);
        bvr_ground_data->applied.assign(objects.GetCount(),0);
'''

LOOKUP=r'''
                const BvrGroundedNode* bvr_ground=nullptr;
                if(!bvr_ground_data->entries.empty()){
                    bvr_ground=bvr_ground_data->slots[args.jobIndex];
                    if(!bvr_ground||bvr_ground->entity!=entity){
                        auto found=bvr_ground_data->indices.find(entity);
                        bvr_ground=found==bvr_ground_data->indices.end()?nullptr:&bvr_ground_data->entries[found->second];
                        bvr_ground_data->slots[args.jobIndex]=bvr_ground;
                    }
                    if(bvr_ground)bvr_ground_data->applied[args.jobIndex]=1;
                }
'''

SPHERE=r'''
                if(bvr_ground){
                    object.center={bvr_ground->sphere[0],bvr_ground->sphere[1],bvr_ground->sphere[2]};
                    object.radius=bvr_ground->sphere[3];
                    object.occlusion.occlusionHistory=~0u;
                }
'''


def prepare(engine):
    engine=Path(engine).resolve();path=engine/'WickedEngine/wiScene.cpp'
    if not (engine/'bvr-wide-primitive.json').exists():raise ValueError('Use an owned prepared engine fork')
    text=path.read_text(encoding='utf8');before=hashlib.sha256(text.encode()).hexdigest()
    if 'SetBvrStaticScenery' in text:raise ValueError('Restore the checked parent scene source before preparing this candidate')
    text=text.replace('#include "wiScene.h"','#include "wiScene.h"\n#include <unordered_map>\n#include <map>\n#include <memory>',1)
    text=text.replace('namespace wi::scene\n{','namespace wi::scene\n{\n'+GLOBAL,1)
    start=text.index('void Scene::RunObjectUpdateSystem(');end=text.index('void Scene::RunCameraUpdateSystem(',start)
    section=text[start:end]
    anchor='auto bvr_materials=std::make_shared<wi::vector<BvrMeshMaterialState>>(meshes.GetCount());'
    if section.count(anchor)!=1:raise ValueError('Material-cache anchor changed')
    section=section.replace(anchor,PRE+'\n        '+anchor,1)
    section=section.replace('[&, bvr_materials, classify]','[&, bvr_materials, classify, bvr_ground_data]',1)
    anchor='const MeshComponent& mesh = meshes[object.mesh_index];'
    if section.count(anchor)!=1:raise ValueError('Mesh anchor changed')
    section=section.replace(anchor,anchor+'\n'+LOOKUP,1)
    anchor='aabb = mesh.aabb.transform(W);'
    if section.count(anchor)!=1:raise ValueError('Bounds anchor changed')
    section=section.replace(anchor,'aabb = bvr_ground ? bvr_ground->bounds : mesh.aabb.transform(W);',1)
    anchor='object.radius = aabb.getRadius();'
    if section.count(anchor)!=1:raise ValueError('Sphere anchor changed')
    section=section.replace(anchor,anchor+'\n'+SPHERE,1)
    anchor='std::memcpy(instanceArrayMapped + args.jobIndex, &inst, sizeof(inst));'
    if section.count(anchor)!=1:raise ValueError('Instance anchor changed')
    section=section.replace(anchor,'if(bvr_ground)std::memcpy(reinterpret_cast<uint8_t*>(&inst)+offsetof(ShaderMeshInstance,padding),bvr_ground->stream.data(),sizeof(uint32_t)*2);\n                '+anchor,1)
    path.write_text(text[:start]+section+text[end:],encoding='utf8')
    manifest={'schema_version':1,'api':'SetBvrStaticGroundBounds','input_sha256':before,
              'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'scope':__doc__}
    for name in ['bvr-static-scenery-cache.json','bvr-inline-ground-bounds.json']:
        (engine/name).write_text(json.dumps(manifest,indent=2),encoding='utf8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--engine',type=Path,required=True)
    prepare(parser.parse_args().engine)
