#pragma once
// Shared low-poly smoke geometry; all motion comes from measured weapon snapshots.
class VisualEffects {
    struct Puff {
        wi::ecs::Entity entity;
        DirectX::XMFLOAT3 position;
        double born, life, radius;
        DirectX::XMFLOAT3 axis{0, 0, 1};
        double length = 0;
    };
    wi::scene::Scene &scene;
    wi::ecs::Entity smoke = wi::ecs::INVALID_ENTITY;
    std::vector<Puff> puffs;
    std::map<std::string, double> sampled;
    std::map<std::string, DirectX::XMFLOAT3> previous_positions;
    std::set<std::pair<uint64_t, std::string>> impacts;
    double previous_time = 0;
    void spawn(DirectX::XMFLOAT3 p, double time, double life, double radius) {
        if (smoke == wi::ecs::INVALID_ENTITY) {
            smoke = scene.Entity_CreateSphere("shared_smoke_mesh", 1, 6, 5);
            scene.objects.GetComponent(smoke)->SetRenderable(false);
            auto mat = scene.materials.GetComponent(smoke);
            mat->SetBaseColor({.55f, .58f, .6f, .2f});
            mat->SetRoughness(1);
            mat->userBlendMode = wi::enums::BLENDMODE_ALPHA;
            mat->SetCastShadow(false);
            mat->SetDirty();
        }
        auto e = scene.Entity_CreateObject("smoke_puff");
        auto o = scene.objects.GetComponent(e);
        o->meshID = smoke;
        o->SetCastShadow(false);
        o->draw_distance = 60000;
        scene.layers.GetComponent(e)->layerMask = 1;
        puffs.push_back({e, p, time, life, radius});
    }

  public:
    VisualEffects(wi::scene::Scene &s) : scene(s) {}
    void clear() {
        for (auto &p : puffs)
            scene.Entity_Remove(p.entity);
        puffs.clear();
        sampled.clear();
        previous_positions.clear();
        impacts.clear();
        previous_time = 0;
    }
    void update(const bvr_sim::GameFrame &f) {
        if (f.sim_time < previous_time)
            clear();
        previous_time = f.sim_time;
        for (const auto &entity : f.entities)
            if (entity.kind == "missile" && entity.alive && entity.motor_burning) {
                auto it = sampled.find(entity.uid);
                if (it == sampled.end() || f.sim_time - it->second >= .095) {
                    DirectX::XMFLOAT3 current{float(-entity.position[1]), float(entity.position[2]),
                                              float(entity.position[0])};
                    auto last = previous_positions.find(entity.uid);
                    if (last == previous_positions.end())
                        spawn(current, f.sim_time, 5, .7);
                    else {
                        auto a = last->second;
                        DirectX::XMFLOAT3 delta{current.x - a.x, current.y - a.y, current.z - a.z};
                        double length = std::hypot(std::hypot(delta.x, delta.y), delta.z);
                        spawn({(current.x + a.x) * .5f, (current.y + a.y) * .5f, (current.z + a.z) * .5f},
                              f.sim_time, 5, .7);
                        if (length > .01) {
                            puffs.back().axis = {float(delta.x / length), float(delta.y / length),
                                                 float(delta.z / length)};
                            puffs.back().length = length;
                        }
                    }
                    sampled[entity.uid] = f.sim_time;
                    previous_positions[entity.uid] = current;
                }
            }
        for (const auto &event : f.events)
            if ((event.kind == "bomb_impact" || event.kind == "missile_hit") && f.tick - event.tick < 20 &&
                impacts.insert({event.tick, event.kind}).second) {
                for (int i = 0; i < 12; ++i) {
                    float angle = float(i * 2.39996), radius = float(2 + i * .6);
                    bool ground_blast = event.kind == "bomb_impact";
                    if (ground_blast && i >= 8)
                        radius = 50;
                    float lift = ground_blast ? (i < 8 ? 10 + float(i % 4) * 6 : 3) : 2 + float(i % 4) * 2;
                    spawn({float(-event.position[1]) + std::cos(angle) * radius,
                           float(event.position[2]) + lift,
                           float(event.position[0]) + std::sin(angle) * radius},
                          f.sim_time, 7, 3 + float(i % 3));
                }
            }
        for (auto it = puffs.begin(); it != puffs.end();) {
            double age = f.sim_time - it->born;
            if (age > it->life) {
                scene.Entity_Remove(it->entity);
                it = puffs.erase(it);
                continue;
            }
            auto t = scene.transforms.GetComponent(it->entity);
            t->ClearTransform();
            float radius = float(it->radius * (1 + age * .5));
            t->Scale(DirectX::XMFLOAT3(radius, radius, float(it->length * .5) + radius));
            if (it->length > 0)
                t->RotateRollPitchYaw(DirectX::XMFLOAT3(-std::asin(std::clamp(it->axis.y, -1.f, 1.f)),
                                                        std::atan2(it->axis.x, it->axis.z), 0));
            t->Translate(DirectX::XMFLOAT3(it->position.x + float(age), it->position.y + float(age * .8),
                                           it->position.z));
            t->UpdateTransform();
            scene.objects.GetComponent(it->entity)->color = {1, 1, 1, float(1 - age / it->life)};
            ++it;
        }
    }
    size_t count() const { return puffs.size(); }
};
