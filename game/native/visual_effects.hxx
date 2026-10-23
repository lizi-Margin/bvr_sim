#pragma once
#include "soft_sprite.hxx"
// Shared low-poly smoke geometry; all motion comes from measured weapon snapshots.
class VisualEffects {
    struct Puff {
        wi::ecs::Entity entity;
        DirectX::XMFLOAT3 position;
        double born, life, radius;
        DirectX::XMFLOAT3 axis{0, 0, 1};
        double length = 0;
        bool flash=false;
    };
    wi::scene::Scene &scene;
    wi::ecs::Entity smoke = wi::ecs::INVALID_ENTITY;
    std::vector<Puff> puffs;
    std::map<std::string, double> sampled;
    std::map<std::string, DirectX::XMFLOAT3> previous_positions;
    std::set<std::pair<uint64_t, std::string>> impacts;
    double previous_time = 0;
    double previous_core_time=0;
    bool soft=false;
    wi::ecs::Entity flash_mesh=wi::ecs::INVALID_ENTITY;
    void spawn(DirectX::XMFLOAT3 p, double time, double life, double radius) {
        if (smoke == wi::ecs::INVALID_ENTITY) {
            smoke = soft?soft_sprite(scene,"shared_smoke_mesh",{.62f,.65f,.67f,.25f}):scene.Entity_CreateSphere("shared_smoke_mesh", 1, 6, 5);
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
    VisualEffects(wi::scene::Scene &s,bool use_soft=false) : scene(s),soft(use_soft) {}
    void clear() {
        for (auto &p : puffs)
            scene.Entity_Remove(p.entity);
        puffs.clear();
        sampled.clear();
        previous_positions.clear();
        impacts.clear();
        previous_time = 0;
        previous_core_time=0;
    }
    void update(const bvr_sim::GameFrame &f,const DirectX::XMFLOAT3& camera,float presentation_dt=1.f/60) {
        if (f.sim_time < previous_core_time)
            clear();
        // Once the core ends a sortie, visual smoke/flash may still dissipate.
        // This presentation clock never advances physics or creates new shots.
        double time=f.result=="running"?f.sim_time:std::max(previous_time,f.sim_time)+std::clamp(double(presentation_dt),0.,.1);
        previous_core_time=f.sim_time;previous_time=time;
        for (const auto &entity : f.entities)
            if (f.result=="running" && entity.kind == "missile" && entity.alive && entity.motor_burning) {
                auto it = sampled.find(entity.uid);
                if (it == sampled.end() || time - it->second >= .095) {
                    DirectX::XMFLOAT3 current{float(-entity.position[1]), float(entity.position[2]),
                                              float(entity.position[0])};
                    auto last = previous_positions.find(entity.uid);
                    if (last == previous_positions.end())
                        spawn(current, time, 5, .7);
                    else {
                        auto a = last->second;
                        DirectX::XMFLOAT3 delta{current.x - a.x, current.y - a.y, current.z - a.z};
                        double length = std::hypot(std::hypot(delta.x, delta.y), delta.z);
                        spawn({(current.x + a.x) * .5f, (current.y + a.y) * .5f, (current.z + a.z) * .5f},
                              time, 5, .7);
                        if (length > .01) {
                            puffs.back().axis = {float(delta.x / length), float(delta.y / length),
                                                 float(delta.z / length)};
                            puffs.back().length = length;
                        }
                    }
                    sampled[entity.uid] = time;
                    previous_positions[entity.uid] = current;
                }
            }
        for (const auto &event : f.events)
            if ((event.kind == "bomb_impact" || event.kind == "missile_hit") && f.tick - event.tick < 20 &&
                impacts.insert({event.tick, event.kind}).second) {
                if(soft){
                    if(flash_mesh==wi::ecs::INVALID_ENTITY){
                        flash_mesh=soft_sprite(scene,"shared_brief_flash",{1,.42f,.10f,.85f},1.6f);
                        scene.objects.GetComponent(flash_mesh)->SetRenderable(false);
                    }
                    auto e=scene.Entity_CreateObject("actual_impact_flash");scene.objects.GetComponent(e)->meshID=flash_mesh;
                    scene.layers.GetComponent(e)->layerMask=1;
                    Puff p{e,{float(-event.position[1]),float(event.position[2])+2,float(event.position[0])},time,.18,8};p.flash=true;puffs.push_back(p);
                }
                for (int i = 0; i < 12; ++i) {
                    float angle = float(i * 2.39996), radius = float(2 + i * .6);
                    bool ground_blast = event.kind == "bomb_impact";
                    if (ground_blast && i >= 8)
                        radius = 50;
                    float lift = ground_blast ? (i < 8 ? 10 + float(i % 4) * 6 : 3) : 2 + float(i % 4) * 2;
                    spawn({float(-event.position[1]) + std::cos(angle) * radius,
                           float(event.position[2]) + lift,
                           float(event.position[0]) + std::sin(angle) * radius},
                          time, 7, 3 + float(i % 3));
                }
            }
        for (auto it = puffs.begin(); it != puffs.end();) {
            double age = time - it->born;
            if (age > it->life) {
                scene.Entity_Remove(it->entity);
                it = puffs.erase(it);
                continue;
            }
            auto t = scene.transforms.GetComponent(it->entity);
            t->ClearTransform();
            float radius = float(it->radius * (1 + age * .5));
            if(soft){
                using namespace DirectX;
                XMFLOAT3 position{it->position.x+float(age),it->position.y+float(age*.8),it->position.z};
                auto normal=XMVector3Normalize(XMLoadFloat3(&camera)-XMLoadFloat3(&position));
                auto axis=it->length>0?XMLoadFloat3(&it->axis):XMVectorSet(0,1,0,0);
                auto right=XMVector3Normalize(XMVector3Cross(axis,normal));
                if(XMVectorGetX(XMVector3LengthSq(right))<.01f)right=XMVectorSet(1,0,0,0);
                auto up=XMVector3Normalize(XMVector3Cross(normal,right));
                XMMATRIX rotation(right,up,normal,XMVectorSet(0,0,0,1));
                t->MatrixTransform(XMMatrixScaling(radius,float(it->length*.5)+radius,1)*rotation*XMMatrixTranslation(position.x,position.y,position.z));t->UpdateTransform();
                scene.objects.GetComponent(it->entity)->color={1,1,1,float(1-age/it->life)};++it;continue;
            }
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
