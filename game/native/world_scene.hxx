#pragma once
// Renderer-owned presentation data. No simulation object can be changed through this API.
#include <unordered_set>
#include <set>
#include <map>
struct ScenePlacement {
    std::string id, model, chunk, category, target_uid;
    std::array<double, 3> position{};
    float yaw = 0, scale = 1, lod_distance = 1700, cull_distance = 35000;
};
struct SceneMaterial {
    std::string id, base_color, normal;
    std::array<float, 4> color{1, 1, 1, 1};
    float tile_m = 2, roughness = .9f;
    bool water = false;
};
struct SceneSurface {
    std::string id, material;
    std::vector<std::array<float, 3>> vertices;
    std::vector<uint32_t> indices;
};
struct SceneStats {
    uint64_t unique_models = 0, imported_glbs = 0, mesh_resources = 0, material_resources = 0;
    uint64_t instances = 0, visible_instances = 0, visible_objects = 0, visible_triangles = 0,
             visible_mesh_subset_groups = 0;
    std::map<std::string, uint64_t> import_counts, chunk_instances;
    std::map<std::string, uint64_t> visible_chunks;
    std::array<uint64_t, 2> visible_lods{0, 0};
};
class WorldScene {
    struct Part {
        wi::ecs::Entity mesh;
        DirectX::XMFLOAT4X4 transform;
        DirectX::XMFLOAT4 color;
    };
    struct Prototype {
        std::vector<Part> parts;
    };
    struct Instance {
        ScenePlacement spec;
        wi::ecs::Entity root;
        std::vector<wi::ecs::Entity> children;
        int lod = -1;
        bool shown = true;
    };
    struct TerrainMesh {
        wi::ecs::Entity entity;
        double n, w, spacing;
        int columns, rows;
    };
    wi::scene::Scene &scene;
    const std::unordered_map<std::string, std::string> &model_files;
    std::map<std::string, Prototype> prototypes;
    std::map<std::string, uint64_t> import_counts;
    std::vector<Instance> instances;
    std::unordered_map<wi::ecs::Entity, size_t> child_instances;
    std::vector<wi::ecs::Entity> world_geometry;
    std::vector<TerrainMesh> terrain_meshes;
    std::map<std::string, wi::ecs::Entity> materials;
    Prototype &prototype(const std::string &model) {
        auto found = prototypes.find(model);
        if (found != prototypes.end())
            return found->second;
        auto file = model_files.find(model);
        if (file == model_files.end() || !std::filesystem::exists(file->second))
            throw std::runtime_error("Missing registered model/LOD: " + model);
        wi::scene::Scene loaded;
        ImportModel_GLTF(file->second, loaded);
        if (loaded.objects.GetCount() == 0)
            throw std::runtime_error("Empty GLB: " + file->second);
        loaded.Update(0);
        Prototype data;
        for (size_t i = 0; i < loaded.objects.GetCount(); ++i) {
            auto entity = loaded.objects.GetEntity(i);
            auto &object = loaded.objects[i];
            auto transform = loaded.transforms.GetComponent(entity);
            if (!transform)
                throw std::runtime_error("Mesh missing transform");
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
        m->texMulAdd = {2 / spec.tile_m, 2 / spec.tile_m, 0, 0};
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
            slot.resource = wi::resourcemanager::Load(spec.normal);
            m->normalMapStrength = .45f;
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
                       const std::vector<std::array<float, 4>> &colors, const std::array<double, 4> &cutout) {
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
                wi::vector<uint32_t> vertex_colors;
                for (int row = 0; row < rows; ++row)
                    for (int col = 0; col < cols; ++col) {
                        double n = patch.origin_north + (col0 + col) * patch.spacing,
                               w = patch.origin_west + (row0 + row) * patch.spacing;
                        positions.push_back({float(-w),
                                             float(patch.heights[(row0 + row) * patch.columns + col0 + col]),
                                             float(n)});
                        uvs.push_back({float(col * patch.spacing / 2), float(row * patch.spacing / 2)});
                        std::array<float, 4> c{1, 1, 1, 1};
                        if (!colors.empty())
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
                        subset.materialID = materials.at(names[i]);
                        mesh->subsets.push_back(subset);
                        offset += subset.indexCount;
                    }
                scene.materials.Remove(e);
                mesh->SetQuantizedPositionsDisabled(true);
                mesh->vertex_uvset_0 = std::move(uvs);
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
    WorldScene(wi::scene::Scene &s, const std::unordered_map<std::string, std::string> &files)
        : scene(s), model_files(files) {}
    wi::ecs::Entity instantiate(const std::string &uid, const std::string &model) {
        auto &data = prototype(model);
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
        for (auto [_, e] : materials)
            scene.Entity_Remove(e);
        materials.clear();
    }
    void configure(const bvr_sim::GameTerrain &terrain, const std::vector<int> &cover,
                   const std::vector<std::array<float, 4>> &colors, const std::vector<SceneMaterial> &mats,
                   const std::vector<SceneSurface> &surfaces, const std::vector<ScenePlacement> &placements,
                   const std::vector<int> &outer_cover,
                   const std::vector<std::array<float, 4>> &outer_colors) {
        using namespace DirectX;
        clear();
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
        terrain_patch(base, 16, outer_cover, outer_colors, cut);
        for (const auto &fine : terrain.detail_tiles)
            terrain_patch(fine, std::max(1, int(1000 / fine.spacing)), cover, colors, {0, 0, 0, 0});
        for (const auto &surface : surfaces) {
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
            instance.root = scene.Entity_CreateTransform(spec.id);
            scene.layers.Create(instance.root).layerMask = 1;
            auto t = scene.transforms.GetComponent(instance.root);
            t->Scale(XMFLOAT3(spec.scale, spec.scale, spec.scale));
            t->RotateRollPitchYaw(XMFLOAT3(0, -spec.yaw, 0));
            t->Translate(
                XMFLOAT3(float(-spec.position[1]), float(spec.position[2]), float(spec.position[0])));
            t->UpdateTransform();
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
    void update(const DirectX::XMFLOAT3 &eye, const bvr_sim::GameFrame &frame) {
        using namespace DirectX;
        for (auto &instance : instances) {
            auto &p = instance.spec;
            double distance =
                std::hypot(std::hypot(eye.x + p.position[1], eye.y - p.position[2]), eye.z - p.position[0]);
            int lod = distance > p.lod_distance && prototypes.count(p.model + "::lod1") ? 1 : 0;
            bool shown = distance < p.cull_distance;
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
