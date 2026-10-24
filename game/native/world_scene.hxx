#pragma once
// Renderer-owned presentation data. No simulation object can be changed through this API.
#include <unordered_set>
#include <set>
#include <map>
#include <bit>
#include <fstream>
#include "json.hpp"
#include "ground_atlas.hxx"
struct ScenePlacement {
    std::string id, model, chunk, category, target_uid;
    std::array<double, 3> position{};
    std::array<float, 3> up_normal{0,1,0};
    std::vector<std::array<double,2>> ground_stems;
    float yaw = 0, scale = 1, lod_distance = 1700, cull_distance = 35000;
};
struct SceneMaterial {
    std::string id, base_color, normal, roughness_map;
    std::string detail_color,detail_normal,detail_roughness;
    float detail_tile_m=3,detail_mean_linear=.2f,detail_strength=0;
    std::array<float, 4> color{1, 1, 1, 1};
    float tile_m = 2, roughness = .9f;
    float uv_origin_north=0,uv_origin_west=0;
    bool water = false,world_uv=false;
};
struct SceneSurface {
    std::string id, material;
    std::vector<std::array<float, 3>> vertices;
    std::vector<uint32_t> indices;
    bool drivable = true;
};
struct SceneStats {
    uint64_t unique_models = 0, imported_glbs = 0, mesh_resources = 0, material_resources = 0;
    uint64_t instances = 0, visible_instances = 0, visible_objects = 0, visible_triangles = 0,
             visible_mesh_subset_groups = 0;
    std::map<std::string, uint64_t> import_counts, chunk_instances;
    std::map<std::string, uint64_t> visible_chunks;
    std::array<uint64_t, 2> visible_lods{0, 0};
};
struct SourceCardMaterialState {
    std::string name, normal_resource;
    std::string albedo_resource;
    uint32_t albedo_format=0, albedo_mip_levels=0;
    bool explicit_mips=false;
    uint32_t normal_format=0, width=0, height=0, mip_levels=0;
    bool rgb_preserved=false;
};
struct GroundVertexState {
    uint32_t subset=0, vertex_index=0;
    bool source_tree_active=true;
    std::array<float,2> uv_anchor{};
    std::array<float,3> world_position{}, world_base{}, bounds_min{}, bounds_max{};
    std::array<float,3> surface_position{}, previous_position{};
    std::array<float,4> gpu_instance_sphere{};
};
class WorldScene {
    struct Part {
        wi::ecs::Entity mesh;
        DirectX::XMFLOAT4X4 transform;
        DirectX::XMFLOAT4 color;
    };
    struct Prototype {
        std::vector<Part> parts;
        nlohmann::json ground_spec;
        nlohmann::json ground_cluster;
        wi::graphics::GPUBuffer ground_parameters;
    };
    struct Instance {
        ScenePlacement spec;
        wi::ecs::Entity root;
        std::vector<wi::ecs::Entity> children;
        int lod = -1;
        bool shown = true;
        bool has_lod = false;
        std::optional<wi::primitive::AABB> ground_bounds;
        uint32_t ground_tree_offset_plus1=0;
    };
    struct TerrainMesh {
        wi::ecs::Entity entity;
        double n, w, spacing;
        int columns, rows;
    };
    struct SurfaceMesh {
        wi::ecs::Entity entity;
        std::array<double, 4> bounds;
    };
    wi::scene::Scene &scene;
    GroundAtlas ground_atlas_;
    GroundBoundsUpdater ground_bounds_updater;
    float detail_tile_m_=3;
    const std::unordered_map<std::string, std::string> &model_files;
    std::map<std::string, Prototype> prototypes;
    std::map<std::string, uint64_t> import_counts;
    std::vector<Instance> instances;
    std::unordered_map<wi::ecs::Entity, size_t> child_instances;
    std::vector<wi::ecs::Entity> world_geometry;
    std::vector<TerrainMesh> terrain_meshes;
    std::vector<SurfaceMesh> contact_meshes;
    std::map<std::string, wi::ecs::Entity> materials;
    std::set<std::string> world_uv_materials;
    nlohmann::json material_profile;
    Prototype &prototype(const std::string &model) {
        auto found = prototypes.find(model);
        if (found != prototypes.end())
            return found->second;
        auto file = model_files.find(model);
        if (file == model_files.end() || !std::filesystem::exists(file->second))
            throw std::runtime_error("Missing registered model/LOD: " + model);
        wi::scene::Scene loaded;
        ImportModel_GLTF(file->second, loaded);
        auto base_model=model.substr(0,model.find("::"));
        nlohmann::json ground_spec;
        nlohmann::json ground_cluster;
        wi::graphics::GPUBuffer ground_parameters;
        const auto manifest_path=std::filesystem::path(file->second).parent_path()/"manifest.json";
        if(std::filesystem::exists(manifest_path)){
            std::ifstream manifest_stream(manifest_path);nlohmann::json manifest;manifest_stream>>manifest;
            if(manifest.contains("cluster") && manifest["cluster"].is_object()){
                ground_spec=manifest["cluster"].value("ground_conform",nlohmann::json());
                if(!ground_spec.is_null())ground_cluster=manifest["cluster"];
            }
            if(!ground_spec.is_null()){
                if(!material_profile.value("source_tree_grounding",false))throw std::runtime_error("Source grove requires the shared ground deformation shader");
                // Mesh-shader cluster bounds and ray tracing geometry are not
                // deformed by the current raster implementation. Fail closed.
                if(wi::renderer::IsMeshShaderAllowed())throw std::runtime_error("Ground-conforming source groves require the indexed raster path");
                const auto minimum=ground_spec.at("min_local_xz").get<std::array<float,2>>();
                const auto span=ground_spec.at("span_local_xz").get<std::array<float,2>>();
                std::vector<std::array<float,2>> anchors;
                if(ground_spec.value("anchor_encoding","")=="source_tree_index_uv1"){
                    const auto center=ground_cluster.at("recentering").get<std::array<float,3>>();
                    for(const auto& pose:ground_cluster.at("poses_before_recentering")){
                        const auto a=pose.at("base_anchor").get<std::array<float,3>>();anchors.push_back({a[0]-center[0],a[1]-center[1]});
                    }
                    if(anchors.size()!=ground_spec.at("source_tree_count").get<size_t>())throw std::runtime_error("Source-tree index table count mismatch");
                }
                ground_parameters=ground_atlas_.parameters({minimum[0],minimum[1],span[0],span[1]},anchors);
                const auto srv=wi::graphics::GetDevice()->GetDescriptorIndex(&ground_parameters,wi::graphics::SubresourceType::SRV);
                for(size_t i=0;i<loaded.materials.GetCount();++i){auto& m=loaded.materials[i];m.userdata.z=uint32_t(srv)+1;m.userdata.w=0x47524e44u;m.SetDirty();}
            }
            const auto& impostor=manifest.value("impostor",nlohmann::json::object());
            if(impostor.is_object()&&impostor.value("view_facing_alpha",false)){
                const auto& source_bake=impostor.value("source_tree_bake",impostor);
                const bool declared_source_normals=source_bake.is_object()&&source_bake.contains("normal_views")&&
                    source_bake.at("normal_views").is_array()&&!source_bake.at("normal_views").empty();
                for(size_t i=0;i<loaded.materials.GetCount();++i){
                    auto n=loaded.names.GetComponent(loaded.materials.GetEntity(i));
                    if(n&&n->name.starts_with("source_impostor_")){
                        auto& m=loaded.materials[i];m.userdata.x=0x42565256u;m.SetDirty();
                        const bool explicit_mips=manifest.contains("source_card_mips");
                        if(explicit_mips){
                            if(!material_profile.value("source_card_full_rgb_normals",false))throw std::runtime_error("Explicit source-card mip normals require full RGB decoding");
                            const auto& slots=manifest.at("source_card_mips").at("materials_by_lod_file").at(std::filesystem::path(file->second).filename().string()).at(n->name);
                            for(auto [name,index]:std::array<std::pair<const char*,int>,2>{{{"base_color",wi::scene::MaterialComponent::BASECOLORMAP},{"normal",wi::scene::MaterialComponent::NORMALMAP}}}){
                                const auto& entry=slots.at(name);const auto path=std::filesystem::path(file->second).parent_path()/entry.at("file").get<std::string>();
                                auto resource=wi::resourcemanager::Load(path.string(),wi::resourcemanager::Flags::IMPORT_RETAIN_FILEDATA);
                                if(!resource.IsValid())throw std::runtime_error("Cannot load registered source-card DDS mip chain");
                                const auto& desc=resource.GetTexture().GetDesc();
                                if(desc.width!=entry.at("width").get<uint32_t>()||desc.height!=entry.at("height").get<uint32_t>()||desc.mip_levels!=entry.at("mip_levels").get<uint32_t>())throw std::runtime_error("Source-card DDS mip dimensions mismatch");
                                const auto expected=index==wi::scene::MaterialComponent::NORMALMAP?wi::graphics::Format::R8G8B8A8_UNORM:wi::graphics::Format::R8G8B8A8_UNORM_SRGB;
                                if(desc.format!=expected)throw std::runtime_error("Source-card DDS mip color space/format mismatch");
                                auto& slot=m.textures[index];slot.name=path.string();slot.resource=resource;
                            }
                            m.userdata.y=0x5247424eu;
                        }
                        if(!explicit_mips&&declared_source_normals&&material_profile.is_object()&&material_profile.value("source_card_full_rgb_normals",false)){
                            // These are projected, averaged source-volume normals,
                            // not small tangent-space bumps. BC5 discards their
                            // independent blue component and cannot reconstruct it
                            // after spatial averaging. Retain the exact source PNG
                            // in a separate linear RGBA resource; all instances share it.
                            auto& slot=m.textures[wi::scene::MaterialComponent::NORMALMAP];
                            if(!slot.resource.IsValid())throw std::runtime_error("Source card has no registered normal image");
                            const auto& bytes=slot.resource.GetFileData();
                            if(bytes.empty())throw std::runtime_error("Source card normal image bytes were not retained");
                            const auto key=slot.name+".bvr-source-rgb.png";
                            auto rgb=wi::resourcemanager::Load(key,wi::resourcemanager::Flags::IMPORT_RETAIN_FILEDATA|wi::resourcemanager::Flags::IMPORT_NORMALMAP,bytes.data(),bytes.size());
                            if(!rgb.IsValid()||rgb.GetTexture().GetDesc().format!=wi::graphics::Format::R8G8B8A8_UNORM)
                                throw std::runtime_error("Source card RGB normals require a linear RGBA8 texture");
                            slot.name=key;slot.resource=rgb;m.userdata.y=0x5247424eu;m.SetDirty();
                        }
                    }
                }
            }
        }
        if(material_profile.contains("scenery_materials")&&
           (base_model=="tree_oak"||base_model=="tree_pine"||base_model=="tree_small"||base_model=="bush")){
            const auto& policy=material_profile.at("scenery_materials");
            for(size_t i=0;i<loaded.materials.GetCount();++i){
                auto n=loaded.names.GetComponent(loaded.materials.GetEntity(i));std::string name=n?n->name:"";
                const char* role=name.find("leaf")!=std::string::npos?"leaf_albedo":name.find("woodBark")!=std::string::npos?"bark_albedo":nullptr;
                if(!role||!policy.contains(role))continue;
                auto c=policy.at(role).get<std::array<float,3>>();auto& m=loaded.materials[i];
                m.SetBaseColor({c[0],c[1],c[2],1});m.SetMetalness(0);m.SetRoughness(.9f);m.SetDirty();
            }
        }
        if (loaded.objects.GetCount() == 0)
            throw std::runtime_error("Empty GLB: " + file->second);
        loaded.Update(0);
        Prototype data;
        data.ground_spec=std::move(ground_spec);data.ground_cluster=std::move(ground_cluster);data.ground_parameters=std::move(ground_parameters);
        for (size_t i = 0; i < loaded.objects.GetCount(); ++i) {
            auto entity = loaded.objects.GetEntity(i);
            auto &object = loaded.objects[i];
            auto transform = loaded.transforms.GetComponent(entity);
            if (!transform)
                throw std::runtime_error("Mesh missing transform");
            if(!data.ground_spec.is_null()){
                DirectX::XMFLOAT4X4 identity;DirectX::XMStoreFloat4x4(&identity,DirectX::XMMatrixIdentity());
                for(int r=0;r<4;++r)for(int c=0;c<4;++c)if(std::abs(transform->world.m[r][c]-identity.m[r][c])>1e-5f)
                    throw std::runtime_error("Ground-conforming source mesh nodes must have identity transforms");
                const auto mesh=loaded.meshes.GetComponent(object.meshID);
                if(!mesh || mesh->vertex_uvset_1.size()!=mesh->vertex_positions.size())throw std::runtime_error("Ground-conforming source mesh is missing UV1 anchors");
                if(!mesh->vertex_boneindices.empty())throw std::runtime_error("Ground-conforming source groves must be static meshes");
                for(size_t k=0;k+2<mesh->indices.size();k+=3){
                    const auto a=mesh->vertex_uvset_1[mesh->indices[k]],b=mesh->vertex_uvset_1[mesh->indices[k+1]],c=mesh->vertex_uvset_1[mesh->indices[k+2]];
                    if(a.x!=b.x||a.y!=b.y||a.x!=c.x||a.y!=c.y)throw std::runtime_error("Ground-conforming triangles must belong to exactly one source tree");
                }
                for(const auto& subset:mesh->subsets){auto m=loaded.materials.GetComponent(subset.materialID);if(m&&m->IsUsingWind())throw std::runtime_error("Ground-conforming static groves do not support wind deformation");}
            }
            data.parts.push_back({object.meshID, transform->world, object.color});
            object.SetRenderable(false);
        }
        // Resource entities remain in the scene exactly once. Instances only reference mesh IDs.
        scene.Merge(loaded);
        import_counts[model]++;
        return prototypes.emplace(model, std::move(data)).first->second;
    }
    wi::ecs::Entity child(wi::ecs::Entity root, const Part &part, const std::string &name) {
        auto e = scene.Entity_CreateObject(name);
        auto object = scene.objects.GetComponent(e);
        object->meshID = part.mesh;
        object->color = part.color;
        auto t = scene.transforms.GetComponent(e);
        t->MatrixTransform(DirectX::XMLoadFloat4x4(&part.transform));
        t->UpdateTransform();
        scene.Component_Attach(e, root, true);
        return e;
    }
    wi::ecs::Entity material(const SceneMaterial &spec) {
        auto e = scene.Entity_CreateMaterial("surface_" + spec.id);
        auto m = scene.materials.GetComponent(e);
        m->SetBaseColor({spec.color[0], spec.color[1], spec.color[2], spec.color[3]});
        m->SetRoughness(spec.roughness);
        m->texMulAdd = {2 / spec.tile_m, 2 / spec.tile_m,
            -spec.uv_origin_north/spec.tile_m,-spec.uv_origin_west/spec.tile_m};
        if(spec.world_uv)world_uv_materials.insert(spec.id);
        if (!spec.base_color.empty()) {
            if (!std::filesystem::exists(spec.base_color))
                throw std::runtime_error("Missing material texture: " + spec.base_color);
            auto &slot = m->textures[wi::scene::MaterialComponent::BASECOLORMAP];
            slot.name = spec.base_color;
            slot.resource = wi::resourcemanager::Load(spec.base_color);
        }
        if (!spec.normal.empty()) {
            if (!std::filesystem::exists(spec.normal))
                throw std::runtime_error("Missing normal texture: " + spec.normal);
            auto &slot = m->textures[wi::scene::MaterialComponent::NORMALMAP];
            slot.name = spec.normal;
            slot.resource = wi::resourcemanager::Load(spec.normal,wi::resourcemanager::Flags::IMPORT_NORMALMAP);
            m->normalMapStrength = .45f;
        }
        if (!spec.roughness_map.empty()) {
            if (!std::filesystem::exists(spec.roughness_map))
                throw std::runtime_error("Missing roughness texture: " + spec.roughness_map);
            // Source maps are grayscale, so G is roughness in Wicked's surface map.
            // Disable the unused R occlusion and B metalness channels explicitly.
            auto &slot = m->textures[wi::scene::MaterialComponent::SURFACEMAP];
            slot.name = spec.roughness_map;
            slot.resource = wi::resourcemanager::Load(spec.roughness_map);
            m->SetOcclusionEnabled_Primary(false);
            m->SetMetalness(0);
        }
        if(!spec.detail_color.empty()&&spec.detail_strength>0){
            detail_tile_m_=spec.detail_tile_m;
            auto& detail=m->textures[wi::scene::MaterialComponent::EMISSIVEMAP];
            detail.name=spec.detail_color;detail.resource=wi::resourcemanager::Load(spec.detail_color);detail.uvset=1;
            m->SetEmissiveColor({0,0,0,0}); // shader uses this slot as albedo detail only
            m->userdata.x=0x42565244u;
            m->userdata.y=std::bit_cast<uint32_t>(1.f/std::max(.001f,spec.detail_mean_linear));
            m->userdata.z=std::bit_cast<uint32_t>(spec.detail_strength);
            auto& normal=m->textures[wi::scene::MaterialComponent::NORMALMAP];
            normal.name=spec.detail_normal;normal.resource=wi::resourcemanager::Load(spec.detail_normal,wi::resourcemanager::Flags::IMPORT_NORMALMAP);normal.uvset=1;
            auto& rough=m->textures[wi::scene::MaterialComponent::SURFACEMAP];
            rough.name=spec.detail_roughness;rough.resource=wi::resourcemanager::Load(spec.detail_roughness);rough.uvset=1;
            m->SetOcclusionEnabled_Primary(false);m->SetMetalness(0);m->normalMapStrength=.5f;
        }
        if (spec.water) {
            m->shaderType = wi::scene::MaterialComponent::SHADERTYPE_WATER;
            m->refraction = .1f;
            m->SetDoubleSided(true);
        }
        m->SetUseVertexColors(true);
        m->SetDirty();
        materials[spec.id] = e;
        return e;
    }
    void terrain_patch(const bvr_sim::TerrainTile &patch, int chunk_cells, const std::vector<int> &cover,
                       const std::vector<std::array<float, 4>> &colors, const std::array<double, 4> &cutout,
                       const std::string &override_material = "",const bvr_sim::GameTerrain* full_terrain=nullptr) {
        using namespace DirectX;
        // Macro colors and land-use tints are baked per cell. Interpolate them at
        // mesh vertices so the 2 km regional colors and 50 m biome edges do not
        // render as a checkerboard of hard-edged quads.
        auto sample_color = [&](int row, int col) {
            const int max_row = patch.rows - 2, max_col = patch.columns - 2;
            float r = std::clamp(float(row) - .5f, 0.f, float(max_row));
            float c = std::clamp(float(col) - .5f, 0.f, float(max_col));
            int r0 = int(r), c0 = int(c), r1 = std::min(r0 + 1, max_row), c1 = std::min(c0 + 1, max_col);
            float fr = r - r0, fc = c - c0;
            std::array<float, 4> result{1, 1, 1, 1};
            for (int channel = 0; channel < 4; ++channel) {
                float a = colors[r0 * (patch.columns - 1) + c0][channel];
                float b = colors[r0 * (patch.columns - 1) + c1][channel];
                float d = colors[r1 * (patch.columns - 1) + c0][channel];
                float e = colors[r1 * (patch.columns - 1) + c1][channel];
                result[channel] = (a + (b - a) * fc) * (1 - fr) + (d + (e - d) * fc) * fr;
            }
            return result;
        };
        static const std::array<std::string, 8> names{"grass", "farmland", "forest", "soil",
                                                      "rock",  "pavement", "water",  "marking"};
        for (int row0 = 0; row0 < patch.rows - 1; row0 += chunk_cells)
            for (int col0 = 0; col0 < patch.columns - 1; col0 += chunk_cells) {
                int cols = std::min(chunk_cells, patch.columns - 1 - col0) + 1,
                    rows = std::min(chunk_cells, patch.rows - 1 - row0) + 1;
                wi::vector<XMFLOAT3> positions;
                wi::vector<XMFLOAT2> uvs;
                wi::vector<XMFLOAT2> detail_uvs;
                wi::vector<XMFLOAT3> smooth_normals;
                wi::vector<uint32_t> vertex_colors;
                for (int row = 0; row < rows; ++row)
                    for (int col = 0; col < cols; ++col) {
                        double n = patch.origin_north + (col0 + col) * patch.spacing,
                               w = patch.origin_west + (row0 + row) * patch.spacing;
                        positions.push_back({float(-w),
                                             float(patch.heights[(row0 + row) * patch.columns + col0 + col]),
                                             float(n)});
                        bool world_uv=override_material.empty()||world_uv_materials.contains(override_material);
                        uvs.push_back({float(world_uv?n/2:(n-patch.origin_north)/2),
                                        float(world_uv?w/2:(w-patch.origin_west)/2)});
                        detail_uvs.push_back({float(n/detail_tile_m_),float(w/detail_tile_m_)});
                        if(full_terrain){
                            double step=std::min(50.,patch.spacing);
                            double dn=(full_terrain->height(n+step,w)-full_terrain->height(n-step,w))/(2*step);
                            double dw=(full_terrain->height(n,w+step)-full_terrain->height(n,w-step))/(2*step);
                            double inv=1/std::sqrt(1+dn*dn+dw*dw);
                            smooth_normals.push_back({float(dw*inv),float(inv),float(-dn*inv)});
                        }
                        std::array<float, 4> c{1, 1, 1, 1};
                        if (!colors.empty() && override_material.empty())
                            c = sample_color(row0 + row, col0 + col);
                        vertex_colors.push_back(wi::Color(uint8_t(std::clamp(c[0], 0.f, 1.f) * 255),
                                                          uint8_t(std::clamp(c[1], 0.f, 1.f) * 255),
                                                          uint8_t(std::clamp(c[2], 0.f, 1.f) * 255), 255)
                                                    .rgba);
                    }
                std::array<wi::vector<uint32_t>, 8> grouped;
                for (int row = 0; row < rows - 1; ++row)
                    for (int col = 0; col < cols - 1; ++col) {
                        double n = patch.origin_north + (col0 + col + .5) * patch.spacing,
                               w = patch.origin_west + (row0 + row + .5) * patch.spacing;
                        if (n > cutout[0] && n < cutout[2] && w > cutout[1] && w < cutout[3])
                            continue;
                        int group =
                            cover.empty() ? 0 : cover[(row0 + row) * (patch.columns - 1) + col0 + col];
                        uint32_t a = row * cols + col, b = a + cols;
                        for (auto i : {a, a + 1, b, a + 1, b + 1, b})
                            grouped[std::clamp(group, 0, 7)].push_back(i);
                    }
                wi::vector<uint32_t> indices;
                for (auto &group : grouped)
                    indices.insert(indices.end(), group.begin(), group.end());
                if (indices.empty())
                    continue;
                auto e = scene.Entity_CreateMeshFromData("terrain_chunk", indices.size(), indices.data(),
                                                         positions.size(), positions.data());
                auto mesh = scene.meshes.GetComponent(e);
                mesh->subsets.clear();
                uint32_t offset = 0;
                for (size_t i = 0; i < grouped.size(); ++i)
                    if (!grouped[i].empty()) {
                        wi::scene::MeshComponent::MeshSubset subset;
                        subset.indexOffset = offset;
                        subset.indexCount = uint32_t(grouped[i].size());
                        subset.materialID =
                            materials.at(override_material.empty() ? names[i] : override_material);
                        mesh->subsets.push_back(subset);
                        offset += subset.indexCount;
                    }
                scene.materials.Remove(e);
                mesh->SetQuantizedPositionsDisabled(true);
                mesh->vertex_uvset_0 = std::move(uvs);
                mesh->vertex_uvset_1 = std::move(detail_uvs);
                if(!smooth_normals.empty())mesh->vertex_normals=std::move(smooth_normals);
                mesh->vertex_colors = std::move(vertex_colors);
                mesh->CreateRenderData();
                scene.layers.GetComponent(e)->layerMask = 1;
                world_geometry.push_back(e);
                terrain_meshes.push_back({e, patch.origin_north + col0 * patch.spacing,
                                          patch.origin_west + row0 * patch.spacing, patch.spacing, cols,
                                          rows});
            }
    }

  public:
    WorldScene(wi::scene::Scene &s, const std::unordered_map<std::string, std::string> &files,const nlohmann::json& profile=nullptr)
        : scene(s), model_files(files),material_profile(profile) {}
    wi::ecs::Entity instantiate(const std::string &uid, const std::string &model) {
        auto &data = prototype(model);
        if(!data.ground_spec.is_null())throw std::runtime_error("Ground-conforming resources must be configured as static scenery");
        auto root = scene.Entity_CreateTransform(uid);
        scene.layers.Create(root).layerMask = 1;
        for (size_t i = 0; i < data.parts.size(); ++i)
            child(root, data.parts[i], uid + "_part" + std::to_string(i));
        return root;
    }
    void clear() {
        for (auto &instance : instances)
            scene.Entity_Remove(instance.root);
        instances.clear();
        child_instances.clear();
        for (auto e : world_geometry)
            scene.Entity_Remove(e);
        world_geometry.clear();
        terrain_meshes.clear();
        contact_meshes.clear();
        for (auto [_, e] : materials)
            scene.Entity_Remove(e);
        materials.clear();
        world_uv_materials.clear();
    }
    void configure(const bvr_sim::GameTerrain &terrain, const std::vector<int> &cover,
                   const std::vector<std::array<float, 4>> &colors, const std::vector<SceneMaterial> &mats,
                   const std::vector<SceneSurface> &surfaces, const std::vector<ScenePlacement> &placements,
                   const std::vector<int> &outer_cover,
                   const std::vector<std::array<float, 4>> &outer_colors,
                   const std::vector<std::string> &terrain_materials) {
        using namespace DirectX;
        clear();
        std::vector<std::array<float,2>> streamed_points;
        for(const auto& spec:placements)for(const auto& point:spec.ground_stems){
            if(!std::isfinite(point[0])||!std::isfinite(point[1]))throw std::invalid_argument("Nonfinite independent source tree position");
            streamed_points.push_back({float(point[0]),float(point[1])});
        }
        ground_atlas_.set_tree_positions(streamed_points);
        uint32_t stream_offset=0;
        for (const auto &m : mats)
            material(m);
        bvr_sim::TerrainTile base;
        base.origin_north = terrain.origin_north;
        base.origin_west = terrain.origin_west;
        base.spacing = terrain.spacing;
        base.columns = terrain.columns;
        base.rows = terrain.rows;
        base.heights = terrain.heights;
        std::array<double, 4> cut{0, 0, 0, 0};
        if (!terrain.detail_tiles.empty()) {
            auto &t = terrain.detail_tiles.front();
            cut = {t.origin_north, t.origin_west, t.origin_north + (t.columns - 1) * t.spacing,
                   t.origin_west + (t.rows - 1) * t.spacing};
        }
        const std::string base_material=terrain_materials.size()>terrain.detail_tiles.size()?terrain_materials.back():"";
        if(!base_material.empty()&&!materials.count(base_material))
            throw std::invalid_argument("Unknown outer terrain material: "+base_material);
        terrain_patch(base, 16, outer_cover, outer_colors, cut,base_material,&terrain);
        for (size_t i = 0; i < terrain.detail_tiles.size(); ++i) {
            const auto &fine = terrain.detail_tiles[i];
            std::array<double, 4> inner{0, 0, 0, 0};
            if (i + 1 < terrain.detail_tiles.size()) {
                const auto &t = terrain.detail_tiles[i + 1];
                inner = {t.origin_north, t.origin_west, t.origin_north + (t.columns - 1) * t.spacing,
                         t.origin_west + (t.rows - 1) * t.spacing};
            }
            const std::string material_name = i < terrain_materials.size() ? terrain_materials[i] :
                (i > 0 ? "detail_" + std::to_string(i) : "");
            if (!material_name.empty() && !materials.count(material_name))
                throw std::invalid_argument("Unknown terrain tile material: " + material_name);
            if (!material_name.empty())
                terrain_patch(fine, std::max(1, int(1000 / fine.spacing)), {}, {}, inner, material_name,&terrain);
            else
                terrain_patch(fine, std::max(1, int(1000 / fine.spacing)), cover, colors, inner,"",&terrain);
        }
        for (const auto &surface : surfaces) {
            if (surface.indices.empty())
                continue;
            wi::vector<XMFLOAT3> vertices;
            wi::vector<XMFLOAT2> uvs;
            wi::vector<uint32_t> indices(surface.indices.begin(), surface.indices.end());
            for (auto p : surface.vertices) {
                vertices.push_back({-p[1], p[2], p[0]});
                uvs.push_back({p[0] / 2, p[1] / 2});
            }
            auto e = scene.Entity_CreateMeshFromData(surface.id, indices.size(), indices.data(),
                                                     vertices.size(), vertices.data());
            auto mesh = scene.meshes.GetComponent(e);
            mesh->subsets[0].materialID = materials.at(surface.material);
            scene.materials.Remove(e);
            mesh->vertex_uvset_0 = std::move(uvs);
            mesh->CreateRenderData();
            scene.layers.GetComponent(e)->layerMask = 1;
            scene.objects.GetComponent(e)->SetCastShadow(false);
            world_geometry.push_back(e);
            if (surface.material == "pavement" && surface.drivable) {
                std::array<double, 4> bounds{INFINITY, INFINITY, -INFINITY, -INFINITY};
                for (auto p : surface.vertices) {
                    bounds[0] = std::min(bounds[0], double(p[0]));
                    bounds[1] = std::min(bounds[1], double(p[1]));
                    bounds[2] = std::max(bounds[2], double(p[0]));
                    bounds[3] = std::max(bounds[3], double(p[1]));
                }
                contact_meshes.push_back({e, bounds});
            }
        }
        for (const auto &spec : placements) {
            prototype(spec.model);
            if (model_files.count(spec.model + "::lod1"))
                prototype(spec.model + "::lod1");
            auto &data = prototypes.at(spec.model);
            size_t count = data.parts.size();
            if (prototypes.count(spec.model + "::lod1"))
                count = std::max(count, prototypes.at(spec.model + "::lod1").parts.size());
            Instance instance;
            instance.spec = spec;
            instance.has_lod = prototypes.count(spec.model+"::lod1")!=0;
            instance.root = scene.Entity_CreateTransform(spec.id);
            scene.layers.Create(instance.root).layerMask = 1;
            auto t = scene.transforms.GetComponent(instance.root);
            t->Scale(XMFLOAT3(spec.scale, spec.scale, spec.scale));
            t->RotateRollPitchYaw(XMFLOAT3(0, -spec.yaw, 0));
            // Optional rigid terrain-plane fit for decorative source groves.
            // Yaw is applied first; +Y then maps onto the declared world normal.
            const auto &up=spec.up_normal;
            if (!std::isfinite(up[0]) || !std::isfinite(up[1]) || !std::isfinite(up[2]) || up[1]<=0)
                throw std::runtime_error("Invalid scenery up normal");
            if(up[0]!=0 || up[1]!=1 || up[2]!=0){
                const auto normal=XMVector3Normalize(XMVectorSet(up[0],up[1],up[2],0));
                const auto axis=XMVector3Cross(XMVectorSet(0,1,0,0),normal);
                t->Rotate(XMQuaternionNormalize(XMVectorSet(XMVectorGetX(axis),0,XMVectorGetZ(axis),1+XMVectorGetY(normal))));
            }
            t->Translate(
                XMFLOAT3(float(-spec.position[1]), float(spec.position[2]), float(spec.position[0])));
            t->UpdateTransform();
            if(!data.ground_spec.is_null()){
                if(spec.up_normal!=std::array<float,3>{0,1,0}||spec.scale<=0)throw std::invalid_argument("Per-tree grounding requires upright static groves with positive scale");
                const auto& cluster=data.ground_cluster;
                const auto center=cluster.at("recentering").get<std::array<float,3>>();
                const auto& poses=cluster.at("poses_before_recentering");
                const auto& bounds=data.ground_spec.at("tree_bounds_relative_blender");
                if(poses.size()!=bounds.size())throw std::runtime_error("Source grove anchor/bounds count mismatch");
                const bool independent=data.ground_spec.value("anchor_encoding","")=="source_tree_index_uv1";
                if(independent){
                    if(spec.ground_stems.empty()||spec.ground_stems.size()>poses.size())throw std::runtime_error("Independent source batch must specify1..source_count tree positions");
                    instance.ground_tree_offset_plus1=stream_offset+1;
                }else if(!spec.ground_stems.empty())throw std::runtime_error("Source resource does not declare independent tree indices");
                wi::primitive::AABB box;
                for(size_t j=0;j<(independent?spec.ground_stems.size():poses.size());++j){
                    const auto anchor=poses[j].at("base_anchor").get<std::array<float,3>>();
                    const auto base=XMVector3TransformCoord(XMVectorSet(anchor[0]-center[0],0,anchor[1]-center[1],1),t->GetWorldMatrix());
                    const double n=independent?spec.ground_stems[j][0]:XMVectorGetZ(base),w=independent?spec.ground_stems[j][1]:-XMVectorGetX(base);
                    if(!ground_atlas_.covers(n,w))throw std::runtime_error("Source grove base lies outside the shared ground atlas");
                    const float height=float(terrain.height(n,w));
                    const auto lo=bounds[j].at("min").get<std::array<float,3>>(), hi=bounds[j].at("max").get<std::array<float,3>>();
                    for(int corner=0;corner<8;++corner){
                        const auto offset=XMVector3TransformNormal(XMVectorSet(corner&1?hi[0]:lo[0],corner&4?hi[2]:lo[2],corner&2?hi[1]:lo[1],0),t->GetWorldMatrix());
                        box.AddPoint(XMVectorSet(float(-w)+XMVectorGetX(offset),height+XMVectorGetY(offset),float(n)+XMVectorGetZ(offset),1));
                    }
                }
                // Covers source UV/position packing and float conversion; it
                // does not change the mesh bounds used for vertex decoding.
                box._min.x-=.05f;box._min.y-=.05f;box._min.z-=.05f;box._max.x+=.05f;box._max.y+=.05f;box._max.z+=.05f;
                instance.ground_bounds=box;
            }
            else if(!spec.ground_stems.empty())throw std::runtime_error("Independent tree placement requires a registered grounding resource");
            stream_offset+=uint32_t(spec.ground_stems.size());
            for (size_t i = 0; i < count; ++i) {
                auto e = child(instance.root, data.parts[std::min(i, data.parts.size() - 1)],
                               spec.id + "_part" + std::to_string(i));
                child_instances[e] = instances.size();
                instance.children.push_back(e);
                scene.objects.GetComponent(e)->draw_distance = spec.cull_distance;
            }
            instances.push_back(std::move(instance));
        }
    }
    GroundAtlas& ground_atlas() {return ground_atlas_;}
    void ground_bounds_before_visibility() {
        // Scene::Update overwrites ordinary rigid bounds. Run after that update
        // and before both main/reflection visibility and shadow rendering.
        std::vector<GroundBoundsUpdate> patches;
        for(const auto& instance:instances)if(instance.ground_bounds){
            const auto& box=*instance.ground_bounds;const auto center=box.getCenter();const float radius=box.getRadius();
            for(auto e:instance.children){
                const auto index=scene.objects.GetIndex(e);if(index==size_t(-1))continue;
                auto& aabb=scene.aabb_objects[index];aabb._min=box._min;aabb._max=box._max;
                scene.objects[index].center=center;scene.objects[index].radius=radius;
                patches.push_back({uint32_t(index),instance.ground_tree_offset_plus1,uint32_t(instance.spec.ground_stems.size()),0,{center.x,center.y,center.z,radius}});
            }
        }
        ground_bounds_updater.apply(scene,patches);
    }
    std::vector<GroundVertexState> scenery_ground_vertices(const std::string& id,bool all_vertices=false) {
        for(const auto& instance:instances)if(instance.spec.id==id){
            if(!instance.ground_bounds)throw std::invalid_argument("Scenery does not declare per-tree ground deformation");
            std::vector<std::array<uint32_t,4>> queries;std::vector<GroundVertexState> states;
            for(auto child:instance.children){
                const auto index=scene.objects.GetIndex(child);const auto& object=scene.objects[index];
                const auto mesh=scene.meshes.GetComponent(object.meshID);
                for(uint32_t subset=0;subset<mesh->subsets.size();++subset){
                    std::set<std::pair<float,float>> seen;std::set<uint32_t> seen_vertices;const auto& part=mesh->subsets[subset];
                    for(uint32_t k=part.indexOffset;k<part.indexOffset+part.indexCount;++k){
                        const auto vertex=mesh->indices[k];const auto uv=mesh->vertex_uvset_1[vertex];
                        if(all_vertices){if(!seen_vertices.insert(vertex).second)continue;}
                        else if(!seen.emplace(uv.x,uv.y).second)continue;
                        queries.push_back({uint32_t(index),mesh->geometryOffset+subset,vertex,0});
                        GroundVertexState state;state.subset=subset;state.vertex_index=vertex;state.uv_anchor={uv.x,uv.y};
                        const auto& box=scene.aabb_objects[index];state.bounds_min={box._min.x,box._min.y,box._min.z};state.bounds_max={box._max.x,box._max.y,box._max.z};states.push_back(state);
                    }
                }
            }
            auto values=ground_atlas_.vertices(scene,queries);
            for(size_t i=0;i<states.size();++i){
                states[i].world_position={values[i][0],values[i][1],values[i][2]};states[i].world_base={values[i][4],values[i][5],values[i][6]};
                states[i].source_tree_active=values[i][3]>.5f;
                states[i].surface_position={values[i][8],values[i][9],values[i][10]};states[i].previous_position={values[i][12],values[i][13],values[i][14]};
                states[i].gpu_instance_sphere={values[i][16],values[i][17],values[i][18],values[i][19]};
            }
            return states;
        }
        throw std::invalid_argument("Scenery instance not found: "+id);
    }
    void update(const DirectX::XMFLOAT3 &eye, const bvr_sim::GameFrame &frame) {
        using namespace DirectX;
        for (auto &instance : instances) {
            auto &p = instance.spec;
            const double x=eye.x+p.position[1],y=eye.y-p.position[2],z=eye.z-p.position[0];
            const double distance_squared=x*x+y*y+z*z;
            // The thresholds and visible content are identical. Avoid two
            // square roots and a string allocation/map lookup per placement.
            int lod = distance_squared > double(p.lod_distance)*p.lod_distance && instance.has_lod ? 1 : 0;
            bool shown = distance_squared < double(p.cull_distance)*p.cull_distance;
            if (lod != instance.lod || shown != instance.shown) {
                auto &parts = prototypes.at(p.model + (lod ? "::lod1" : "")).parts;
                for (size_t i = 0; i < instance.children.size(); ++i) {
                    auto e = instance.children[i];
                    auto object = scene.objects.GetComponent(e);
                    object->SetRenderable(shown && i < parts.size());
                    if (i < parts.size()) {
                        object->meshID = parts[i].mesh;
                        object->color = parts[i].color;
                        auto t = scene.transforms.GetComponent(e);
                        t->ClearTransform();
                        t->MatrixTransform(XMLoadFloat4x4(&parts[i].transform));
                        t->UpdateTransform();
                    }
                }
                instance.lod = lod;
                instance.shown = shown;
            }
            if (!p.target_uid.empty())
                for (const auto &entity : frame.entities)
                    if (entity.uid == p.target_uid) {
                        for (auto e : instance.children)
                            scene.objects.GetComponent(e)->color =
                                entity.alive ? XMFLOAT4(1, 1, 1, 1) : XMFLOAT4(.1f, .1f, .1f, 1);
                    }
        }
    }
    std::vector<std::array<double,3>> scenery_points(const std::string& id,const std::vector<std::array<double,3>>& points) const {
        for(const auto& instance:instances)if(instance.spec.id==id){
            const auto matrix=scene.transforms.GetComponent(instance.root)->GetWorldMatrix();
            std::vector<std::array<double,3>> result;result.reserve(points.size());
            for(const auto& p:points){
                const auto v=DirectX::XMVector3TransformCoord(DirectX::XMVectorSet(float(p[0]),float(p[1]),float(p[2]),1),matrix);
                result.push_back({DirectX::XMVectorGetX(v),DirectX::XMVectorGetY(v),DirectX::XMVectorGetZ(v)});
            }
            return result;
        }
        throw std::runtime_error("Scenery instance not found: "+id);
    }
    SceneStats stats(const wi::renderer::Visibility &visibility) const {
        SceneStats result;
        result.import_counts = import_counts;
        result.imported_glbs = import_counts.size();
        std::set<std::string> models;
        for (auto [model, count] : import_counts)
            models.insert(model.substr(0, model.find("::")));
        result.unique_models = models.size();
        result.mesh_resources = scene.meshes.GetCount();
        result.material_resources = scene.materials.GetCount();
        result.instances = instances.size();
        for (auto &instance : instances)
            result.chunk_instances[instance.spec.chunk]++;
        std::unordered_set<size_t> visible;
        std::set<std::pair<wi::ecs::Entity, wi::ecs::Entity>> groups;
        for (auto index : visibility.visibleObjects) {
            if (index >= scene.objects.GetCount())
                continue;
            const auto &object = scene.objects[index];
            auto mesh = scene.meshes.GetComponent(object.meshID);
            if (!mesh)
                continue;
            result.visible_objects++;
            result.visible_triangles += mesh->indices.size() / 3;
            for (auto subset : mesh->subsets)
                groups.insert({object.meshID, subset.materialID});
            auto found = child_instances.find(scene.objects.GetEntity(index));
            if (found != child_instances.end())
                visible.insert(found->second);
        }
        result.visible_instances = visible.size();
        for (auto index : visible) {
            result.visible_lods[std::clamp(instances[index].lod, 0, 1)]++;
            result.visible_chunks[instances[index].spec.chunk]++;
        }
        result.visible_mesh_subset_groups = groups.size();
        return result;
    }
    std::vector<SourceCardMaterialState> source_card_materials() const {
        std::vector<SourceCardMaterialState> result;
        for(size_t i=0;i<scene.materials.GetCount();++i){
            const auto& material=scene.materials[i];
            if(material.userdata.x!=0x42565256u)continue;
            const auto& slot=material.textures[wi::scene::MaterialComponent::NORMALMAP];
            SourceCardMaterialState item;
            auto name=scene.names.GetComponent(scene.materials.GetEntity(i));item.name=name?name->name:"";
            item.normal_resource=slot.name;
            const auto& albedo=material.textures[wi::scene::MaterialComponent::BASECOLORMAP];item.albedo_resource=albedo.name;item.explicit_mips=std::filesystem::path(albedo.name).extension()==".dds";
            if(albedo.resource.IsValid()){const auto& d=albedo.resource.GetTexture().GetDesc();item.albedo_format=uint32_t(d.format);item.albedo_mip_levels=d.mip_levels;}
            if(slot.resource.IsValid()){
                const auto& desc=slot.resource.GetTexture().GetDesc();
                item.normal_format=uint32_t(desc.format);item.width=desc.width;item.height=desc.height;item.mip_levels=desc.mip_levels;
                item.rgb_preserved=material.userdata.y==0x5247424eu&&desc.format==wi::graphics::Format::R8G8B8A8_UNORM;
            }
            result.push_back(std::move(item));
        }
        return result;
    }
    double render_surface_height(double north, double west, double reference = INFINITY) const {
        double result = render_height(north, west);
        for (const auto &surface : contact_meshes) {
            const auto &r = surface.bounds;
            if (north < r[0] || west < r[1] || north > r[2] || west > r[3])
                continue;
            auto mesh = scene.meshes.GetComponent(surface.entity);
            if (!mesh)
                continue;
            for (size_t i = 0; i + 2 < mesh->indices.size(); i += 3) {
                auto a = mesh->vertex_positions[mesh->indices[i]],
                     b = mesh->vertex_positions[mesh->indices[i + 1]],
                     c = mesh->vertex_positions[mesh->indices[i + 2]];
                // Wicked (-west,up,north) -> the NWU plane, independent of core surface sampling.
                double det = (b.z - a.z) * (-c.x + a.x) - (c.z - a.z) * (-b.x + a.x);
                if (std::abs(det) < 1e-10)
                    continue;
                double u = ((north - a.z) * (-c.x + a.x) - (west + a.x) * (c.z - a.z)) / det;
                double v = ((b.z - a.z) * (west + a.x) - (-b.x + a.x) * (north - a.z)) / det;
                if (u >= -1e-8 && v >= -1e-8 && u + v <= 1 + 1e-8) {
                    double h = a.y + u * (b.y - a.y) + v * (c.y - a.y);
                    if (h <= reference + .6)
                        result = std::max(result, h);
                }
            }
        }
        return result;
    }
    double render_height(double north, double west) const {
        // Query the actual CPU vertices uploaded to GPU, independently of GameTerrain::height.
        const TerrainMesh *best = nullptr;
        for (auto &patch : terrain_meshes)
            if (north >= patch.n && west >= patch.w &&
                north <= patch.n + (patch.columns - 1) * patch.spacing &&
                west <= patch.w + (patch.rows - 1) * patch.spacing &&
                (!best || patch.spacing < best->spacing))
                best = &patch;
        if (!best)
            throw std::out_of_range("No rendered terrain at query point");
        auto mesh = scene.meshes.GetComponent(best->entity);
        double u = (north - best->n) / best->spacing, v = (west - best->w) / best->spacing;
        int c = std::min(int(u), best->columns - 2), r = std::min(int(v), best->rows - 2);
        double x = u - c, y = v - r;
        auto a = mesh->vertex_positions[r * best->columns + c],
             b = mesh->vertex_positions[r * best->columns + c + 1],
             d = mesh->vertex_positions[(r + 1) * best->columns + c],
             e = mesh->vertex_positions[(r + 1) * best->columns + c + 1];
        return x + y <= 1 ? (1 - x - y) * a.y + x * b.y + y * d.y
                          : (x + y - 1) * e.y + (1 - x) * d.y + (1 - y) * b.y;
    }
};
