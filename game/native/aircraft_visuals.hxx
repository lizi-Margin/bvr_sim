#pragma once
#include "json.hpp" // nlohmann, supplied by Wicked Engine Editor include path
#include <fstream>
#include <sstream>
// Presentation-only FlightGear hierarchy, source animation pivots and nozzle
// attachments. Inputs are immutable values from the typed simulation snapshot.
class AircraftVisuals {
    using Entity=wi::ecs::Entity;
    using Transform=wi::scene::TransformComponent;
    struct Motion {
        Entity entity;
        std::string property, type;
        DirectX::XMFLOAT3 axis;
        Transform rest;
        double factor=1,offset=0,initial=0,min=-1e12,max=1e12;
        std::vector<std::pair<double,double>> table;
    };
    struct Instance { std::string uid; std::vector<Motion> motions; std::vector<Entity> exhausts; };
    struct Node { Entity original,parent=wi::ecs::INVALID_ENTITY,mesh=wi::ecs::INVALID_ENTITY; std::string name; Transform transform; DirectX::XMFLOAT4 color{1,1,1,1}; };
    struct Prototype { std::vector<Node> nodes; nlohmann::json metadata; };
    wi::scene::Scene& scene;
    std::map<std::string,Prototype> prototypes;
    std::map<std::string,uint64_t> import_counts;
    std::map<Entity,Instance> instances;
    uint64_t updates=0;
    uint64_t corrected_surfaces=0,nozzle_meshes=0;
    nlohmann::json material_profile;
    void apply_materials(wi::scene::Scene& loaded,const std::string& file){
        if(material_profile.is_null())return;
        auto id=std::filesystem::path(file).parent_path().filename().string();
        if(id!="F22"&&id!="F16")return;
        for(size_t i=0;i<loaded.materials.GetCount();++i){
            auto e=loaded.materials.GetEntity(i);auto& m=loaded.materials[i];
            auto n=loaded.names.GetComponent(e);std::string name=n?n->name:"";
            bool glass=id=="F22"?name=="Default":name=="glassOutsideMat"||name=="glassInsideMat";
            if(glass){
                m.SetBaseColor({.62f,.70f,.76f,material_profile.value("canopy_alpha",.48f)});
                m.SetRoughness(material_profile.value("canopy_roughness",.09f));m.SetMetalness(0);m.SetReflectance(.04f);
                m.SetTransmissionAmount(material_profile.value("canopy_transmission",.12f));m.refraction=.02f;
                m.shaderType=wi::scene::MaterialComponent::SHADERTYPE_PBR_CLEARCOAT;
                m.SetClearcoatFactor(1);m.SetClearcoatRoughness(.08f);m.SetCastShadow(false);
                m.userBlendMode=wi::enums::BLENDMODE_ALPHA;
            }else{
                auto c=m.baseColor;float factor=material_profile.value("paint_factor",.72f);
                m.SetBaseColor({c.x*factor,c.y*factor,c.z*factor,c.w});m.SetRoughness(material_profile.value("paint_roughness",.64f));
                m.SetMetalness(0);m.SetReflectance(.04f);
                if(name.find("engine")!=std::string::npos||name.find("Nozzle")!=std::string::npos){m.SetMetalness(.7f);m.SetRoughness(.35f);}
                if(material_profile.value("source_surface_corrections",false)){
                    if(id=="F22"&&name=="ac3dmat1.007"){
                        // Source atlas contains pure-white RAM borders. Bound
                        // their diffuse reflectance in the shader, retaining
                        // positions, normals, UVs, markings and source images.
                        m.userdata.x=0x42565250u;
                        ++corrected_surfaces;
                    }
                    if(id=="F16"&&name=="emissiveMat.001"){
                        // Verified InternalFlame node: z=3.262m, inside the
                        // nozzle at z=4.34..4.62m in source glTF. The .000
                        // material belongs to navigation lights and is kept.
                        m.SetEmissiveColor({0,0,0,0});m.SetBaseColor({.075f,.07f,.065f,1});
                        m.SetMetalness(.55f);m.SetRoughness(.48f);
                        ++corrected_surfaces;
                    }
                }
            }
            m.SetDirty();
        }
        if(id=="F22"&&material_profile.value("source_surface_corrections",false)){
            std::map<Entity,Entity> nozzle_materials;
            for(size_t i=0;i<loaded.meshes.GetCount();++i){
                auto entity=loaded.meshes.GetEntity(i);auto n=loaded.names.GetComponent(entity);
                std::string name=n?n->name:"";
                if(name.find("F119")==std::string::npos&&name.find("vector")==std::string::npos&&name.find("reheat")==std::string::npos)continue;
                ++nozzle_meshes;
                for(auto& subset:loaded.meshes[i].subsets){
                    auto found=nozzle_materials.find(subset.materialID);
                    if(found==nozzle_materials.end()){
                        auto source=loaded.materials.GetComponent(subset.materialID);if(!source)continue;
                        auto copy=*source;auto e=loaded.Entity_CreateMaterial("F22_nozzle_source_atlas");
                        auto m=loaded.materials.GetComponent(e);*m=copy;m->userdata.x=0;
                        m->SetMetalness(.65f);m->SetRoughness(.38f);m->SetBaseColor({.5f,.48f,.46f,1});m->SetDirty();
                        found=nozzle_materials.emplace(subset.materialID,e).first;
                    }
                    subset.materialID=found->second;
                }
            }
        }
    }
    static double number(const nlohmann::json& v) {
        return v.get<double>();
    }
    static double field(const nlohmann::json& v,const std::string& key,double fallback) {
        return v.contains(key)?number(v.at(key)):fallback;
    }
    static std::string canonical(std::string s){
        if(!s.empty()&&s.front()=='/')s.erase(0,1);
        for(size_t i;(i=s.find("[0]"))!=std::string::npos;)s.erase(i,3);
        return s;
    }
public:
    explicit AircraftVisuals(wi::scene::Scene& s):scene(s){}
    void set_material_profile(const nlohmann::json& profile){material_profile=profile;}
    Entity instantiate(const std::string& uid,const std::string& file) {
        using namespace DirectX;
        auto found=prototypes.find(file);
        if(found==prototypes.end()){
            wi::scene::Scene loaded;
            ImportModel_GLTF(file,loaded);
            apply_materials(loaded,file);
            if(loaded.objects.GetCount()==0)throw std::runtime_error("Empty aircraft: "+file);
            loaded.Update(0);
            Prototype proto;
            for(size_t i=0;i<loaded.transforms.GetCount();++i){
                Node node;node.original=loaded.transforms.GetEntity(i);node.transform=loaded.transforms[i];
                if(auto h=loaded.hierarchy.GetComponent(node.original))node.parent=h->parentID;
                if(auto n=loaded.names.GetComponent(node.original))node.name=n->name;
                if(auto o=loaded.objects.GetComponent(node.original)){node.mesh=o->meshID;node.color=o->color;}
                proto.nodes.push_back(node);
            }
            auto manifest=std::filesystem::path(file).parent_path()/"manifest.json";
            if(std::filesystem::is_regular_file(manifest)){
                std::ifstream stream(manifest);stream>>proto.metadata;
            }
            // Cache only mesh/material resources in the shared scene. Every
            // live aircraft gets its own transforms and object instances.
            loaded.objects.Clear();loaded.transforms.Clear();loaded.hierarchy.Clear();loaded.layers.Clear();loaded.names.Clear();
            scene.Merge(loaded);
            found=prototypes.emplace(file,std::move(proto)).first;++import_counts[file];
        }
        const auto& proto=found->second;
        auto root=scene.Entity_CreateTransform(uid);scene.layers.Create(root).layerMask=1;
        std::map<Entity,Entity> remap;std::map<std::string,Entity> named;
        for(const auto& node:proto.nodes){
            auto e=scene.Entity_CreateTransform(uid+"_"+node.name);remap[node.original]=e;named[node.name]=e;
            *scene.transforms.GetComponent(e)=node.transform;
            scene.layers.Create(e).layerMask=~0u;
            if(node.mesh!=wi::ecs::INVALID_ENTITY){
                auto& o=scene.objects.Create(e);o.meshID=node.mesh;o.color=node.color;o.draw_distance=600000;
            }
        }
        for(const auto& node:proto.nodes){
            auto parent=remap.find(node.parent);
            scene.Component_Attach(remap.at(node.original),parent==remap.end()?root:parent->second,true);
        }
        const auto& data=proto.metadata;
        Instance item;item.uid=uid;
        if(!data.is_null()){
            if(data.contains("animations"))for(const auto& a:data.at("animations")){
                auto it=named.find(a.at("node").get<std::string>());if(it==named.end())continue;
                auto transform=scene.transforms.GetComponent(it->second);if(!transform)continue;
                Motion m;m.entity=it->second;m.rest=*transform;
                m.property=canonical(a.at("property").get<std::string>());m.type=a.at("type").get<std::string>();
                const auto& axis=a.at("axis_blender");
                // Blender -> glTF (x,z,-y), then Wicked reflects z. Axial
                // vectors gain the reflection determinant for rotations.
                float sign=m.type=="rotate"?-1.f:1.f;
                m.axis={float(number(axis.at(0)))*sign,float(number(axis.at(2)))*sign,float(number(axis.at(1)))*sign};
                m.factor=field(a,"factor",1);m.offset=field(a,"offset",0);m.initial=field(a,"initial_value",0);
                m.min=field(a,"min",-1e12);m.max=field(a,"max",1e12);
                if(a.contains("interpolation"))for(const auto& p:a.at("interpolation"))
                    m.table.push_back({number(p.at(0)),number(p.at(1))});
                std::sort(m.table.begin(),m.table.end());item.motions.push_back(std::move(m));
            }
            if(data.contains("exhausts"))for(const auto& a:data.at("exhausts")){
                const auto& p=a.at("position");float radius=float(field(a,"radius_m",.2));
                auto e=scene.Entity_CreateSphere(uid+"_engine_glow",1,10,8);
                auto t=scene.transforms.GetComponent(e);t->Scale(XMFLOAT3(radius,radius,radius*1.6f));
                t->Translate(XMFLOAT3(float(number(p.at(0))),float(number(p.at(1))),float(number(p.at(2)))-radius*.35f));
                t->UpdateTransform();scene.Component_Attach(e,root,true);
                auto mat=scene.materials.GetComponent(e);mat->SetCastShadow(false);
                mat->SetBaseColor({1,.25f,.02f,1});mat->SetEmissiveColor({1,.2f,.01f,0});
                item.exhausts.push_back(e);
            }
        }
        instances[root]=std::move(item);return root;
    }
    void update(Entity root,const std::map<std::string,double>& properties,double throttle,bool studio){
        using namespace DirectX;
        auto it=instances.find(root);if(it==instances.end())return;
        std::map<std::string,double> values;
        for(const auto& [key,value]:properties)values[canonical(key)]=value;
        for(const auto& m:it->second.motions){
            auto value=values.find(m.property);
            // Missing FlightGear/Nasal outputs retain the declared flight pose.
            if(value==values.end())continue;
            double x=value->second,y=x*m.factor+m.offset;
            if(!m.table.empty()){
                y=m.table.front().second;
                if(x>=m.table.back().first)y=m.table.back().second;
                else for(size_t i=1;i<m.table.size();++i)if(x<m.table[i].first){
                    auto [x0,y0]=m.table[i-1];auto [x1,y1]=m.table[i];
                    y=x<x0?y0:y0+(y1-y0)*(x-x0)/(x1-x0);break;
                }
            }
            y=std::clamp(y,m.min,m.max)-m.initial;
            auto t=scene.transforms.GetComponent(m.entity);if(!t)continue;*t=m.rest;
            if(m.type=="rotate"){
                auto q=XMQuaternionRotationAxis(XMLoadFloat3(&m.axis),float(y*3.141592653589793/180));
                XMStoreFloat4(&t->rotation_local,XMQuaternionMultiply(XMLoadFloat4(&m.rest.rotation_local),q));
            }else{
                t->translation_local.x+=m.axis.x*float(y);t->translation_local.y+=m.axis.y*float(y);t->translation_local.z+=m.axis.z*float(y);
            }
            t->SetDirty();++updates;
        }
        for(auto e:it->second.exhausts){
            float intensity=studio?0.f:float(std::clamp((throttle-.35)/.65,0.,1.));
            if(auto obj=scene.objects.GetComponent(e))obj->SetRenderable(intensity>.02f);
            if(auto mat=scene.materials.GetComponent(e))mat->SetEmissiveColor({1,.25f,.03f,intensity*4});
        }
    }
    void remove(Entity root){instances.erase(root);}
    void clear(){instances.clear();updates=0;}
    const std::map<std::string,uint64_t>& imports() const { return import_counts; }
    std::map<std::string,uint64_t> stats() const {
        uint64_t animations=0,exhausts=0;
        for(const auto& [_,a]:instances){animations+=a.motions.size();exhausts+=a.exhausts.size();}
        return {{"cached_models",prototypes.size()},{"mesh_resources",scene.meshes.GetCount()},{"material_resources",scene.materials.GetCount()},{"instances",instances.size()},{"animations",animations},{"property_updates",updates},{"exhausts",exhausts},{"corrected_source_materials",corrected_surfaces},{"separate_nozzle_meshes",nozzle_meshes}};
    }
};
