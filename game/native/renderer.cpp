#include "WickedEngine.h"
#include "ModelImporter.h" // Upstream importer declarations require WickedEngine.h first.
#include "gameplay/game_session.hxx"
#include <Windows.h>
#include <filesystem>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include "world_scene.hxx"
#include "audio_presenter.hxx"
#include "visual_effects.hxx"
namespace py = pybind11;
using namespace DirectX;
using wi::ecs::Entity;
struct HudText {
    float x = 0, y = 0;
    int size = 20;
    std::string text;
    uint32_t color = 0xffffffff;
};
struct HudLine {
    float x = 0, y = 0, w = 1, h = 1;
    uint32_t color = 0xffffffff;
    float rotation = 0;
};
struct Input {
    float x = 0, y = 0;
    bool active = false, quit = false;
    std::vector<int> held, pressed;
};
class GamePath : public wi::RenderPath3D {
  public:
    std::vector<HudText> texts;
    std::vector<HudLine> lines;
    void Compose(wi::graphics::CommandList cmd) const override {
        wi::RenderPath3D::Compose(cmd);
        // HUD coordinates are physical pixels; do not apply Windows DPI a second time.
        wi::Canvas hud;
        hud.init(GetPhysicalWidth(), GetPhysicalHeight(), 96);
        wi::image::SetCanvas(hud);
        wi::font::SetCanvas(hud);
        for (const auto &l : lines) {
            wi::image::Params p;
            p.pos = {l.x, l.y, 0};
            p.siz = {l.w, l.h};
            p.color = wi::Color(l.color).toFloat4();
            p.rotation = l.rotation;
            wi::image::Draw(wi::texturehelper::getWhite(), p, cmd);
        }
        for (const auto &t : texts) {
            wi::font::Params p(t.x, t.y, t.size);
            p.color = wi::Color(t.color);
            p.shadowColor = wi::Color(0, 0, 0, 200);
            p.shadow_offset_x = p.shadow_offset_y = 1;
            wi::font::Draw(t.text, p, cmd);
        }
    }
};
class Renderer {
    std::unique_ptr<wi::Application> app;
    std::unique_ptr<GamePath> path;
    HWND window = nullptr;
    bool closed = false;
    bool previous[256]{};
    std::unordered_map<std::string, Entity> roots;
    std::unordered_map<std::string, std::string> model_files;
    std::unique_ptr<WorldScene> baked_world;
    std::vector<Entity> world_entities;
    Entity depot = wi::ecs::INVALID_ENTITY;
    wi::graphics::Texture last_frame;
    std::unordered_map<std::string, std::pair<Entity, uint64_t>> flashes;
    std::string quality = "medium";
    XMFLOAT3 camera_eye{}, camera_at{};
    XMFLOAT3 camera_up_vector{0, 1, 0};
    bool camera_set = false;
    int width, height;
    bool studio = false;
    std::vector<Entity> studio_entities;
    std::map<Entity, std::vector<Entity>> engine_effects;
    AudioPresenter audio;
    std::unique_ptr<VisualEffects> effects;
    std::map<Entity, Entity> weapon_flames;
    static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l) {
        if (m == WM_CLOSE) {
            PostMessage(h, WM_APP + 1, 0, 0);
            return 0;
        }
        if (m == WM_INPUT) {
            wi::input::rawinput::ParseMessage((void *)l);
            return 0;
        }
        return DefWindowProc(h, m, w, l);
    }
    Entity cube(const std::string &name, XMFLOAT3 pos, XMFLOAT3 scale, XMFLOAT4 color) {
        auto &s = wi::scene::GetScene();
        auto e = s.Entity_CreateCube(name);
        auto t = s.transforms.GetComponent(e);
        t->Scale(scale);
        t->Translate(pos);
        t->UpdateTransform();
        // Entity_CreateCube owns its material on the same entity.
        auto mat = s.materials.GetComponent(e);
        if (mat) {
            mat->SetBaseColor(color);
            mat->SetRoughness(.85f);
        }
        return e;
    }
    Entity import_model(const std::string &uid, const std::string &model) {
        auto root = baked_world->instantiate(uid, model);
        roots[uid] = root;
        return root;
    }
    void exhaust(Entity parent, const std::string &model) {
        auto &s = wi::scene::GetScene();
        const int count = model == "F22" ? 2 : 1;
        for (int i = 0; i < count; ++i) {
            auto e = s.Entity_CreateSphere("engine_glow", 1, 10, 10);
            auto t = s.transforms.GetComponent(e);
            t->Scale(XMFLOAT3(.22f, .22f, .6f));
            t->Translate(
                XMFLOAT3(count == 2 ? (i == 0 ? -.7f : .7f) : 0, -.1f, model == "F22" ? -8.6f : -5.9f));
            t->UpdateTransform();
            s.Component_Attach(e, parent, true);
            auto m = s.materials.GetComponent(e);
            m->SetBaseColor({1, .30f, .05f, 1});
            m->SetEmissiveColor({1, .25f, .03f, 3});
            engine_effects[parent].push_back(e);
        }
    }

  public:
    Renderer(int w, int h, bool visible, const std::string &engine, const std::string &shaders,
             const std::map<std::string, std::string> &models)
        : model_files(models.begin(), models.end()), width(w), height(h) {
        if (w < 320 || h < 240)
            throw std::invalid_argument("Window too small");
        if (!LoadLibraryW(std::filesystem::path(engine + "/WickedEngine/dxcompiler.dll").c_str()))
            throw std::runtime_error("Cannot load Wicked Engine dxcompiler.dll");
        wi::arguments::Parse(L"alwaysactive dx12");
        wi::renderer::SetShaderSourcePath(engine + "/WickedEngine/shaders/");
        wi::renderer::SetShaderPath(shaders + "/");
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        WNDCLASSW wc{};
        wc.lpfnWndProc = wndproc;
        wc.hInstance = GetModuleHandle(nullptr);
        wc.lpszClassName = L"BvrWickedGame";
        wc.hCursor = LoadCursor(nullptr, IDC_CROSS);
        RegisterClassW(&wc);
        RECT r{0, 0, w, h};
        AdjustWindowRect(&r, WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX, FALSE);
        window = CreateWindowW(wc.lpszClassName, L"BVR SIM | Flight Operations",
                               WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU | WS_MINIMIZEBOX, 100, 80,
                               r.right - r.left, r.bottom - r.top, nullptr, nullptr, wc.hInstance, nullptr);
        if (!window)
            throw std::runtime_error("Cannot create game window");
        if (visible)
            ShowWindow(window, SW_SHOW);
        app = std::make_unique<wi::Application>();
        app->SetWindow(window);
        app->swapChain.desc.vsync = false;
        app->Initialize();
        wi::initializer::WaitForInitializationsToFinish();
        path = std::make_unique<GamePath>();
        app->ActivatePath(path.get());
        path->camera->CreatePerspective(float(w), float(h), .2f, 600000.f, 1.05f);
        set_quality("medium");
        auto &s = wi::scene::GetScene();
        baked_world = std::make_unique<WorldScene>(s, model_files);
        effects = std::make_unique<VisualEffects>(s);
        auto weather = wi::ecs::CreateEntity();
        auto &sky = s.weathers.Create(weather);
        sky.SetRealisticSky(false);
        sky.SetRealisticSkyAerialPerspective(false);
        sky.SetVolumetricClouds(false);
        sky.ambient = {.22f, .25f, .3f};
        sky.horizon = {.58f, .70f, .78f};
        sky.zenith = {.18f, .35f, .65f};
        sky.fogStart = 40000;
        // Keep nearby BVR contacts clear while fading the finite regional terrain
        // into the same horizon color as the sky before its outer boundary appears.
        sky.fogDensity = .000020f;
        auto sun = s.Entity_CreateLight("sun", {0, 100, 0}, {1, .94f, .84f}, 4, 100000,
                                        wi::scene::LightComponent::DIRECTIONAL);
        auto t = s.transforms.GetComponent(sun);
        t->RotateRollPitchYaw(XMFLOAT3(-.65f, -.6f, 0));
        t->UpdateTransform();
        s.lights.GetComponent(sun)->SetCastShadow(true);
        s.layers.Create(sun).layerMask = 1;
        auto floor = cube("hangar_floor", {0, -.4f, 0}, {55, .3f, 45}, {.23f, .25f, .28f, 1});
        auto wall = cube("hangar_back", {0, 15, 34}, {55, 15, 1}, {.18f, .21f, .25f, 1});
        auto side = cube("hangar_side", {-55, 15, 0}, {1, 15, 35}, {.18f, .21f, .25f, 1});
        for (auto e : {floor, wall, side}) {
            s.layers.GetComponent(e)->layerMask = 2;
            studio_entities.push_back(e);
        }
        for (auto position : {XMFLOAT3(-18, 16, -12), XMFLOAT3(22, 12, 8), XMFLOAT3(0, 18, 20)}) {
            auto light = s.Entity_CreateLight("hangar_softbox", position, {.9f, .95f, 1}, 1800, 90,
                                              wi::scene::LightComponent::POINT);
            s.layers.Create(light).layerMask = 2;
            studio_entities.push_back(light);
        }
    }
    ~Renderer() { close(); }
    void close() {
        if (closed)
            return;
        closed = true;
        audio.stop();
        if (effects)
            effects->clear();
        if (wi::graphics::GetDevice())
            wi::graphics::GetDevice()->WaitForGPU();
        wi::jobsystem::ShutDown();
        if (app)
            app->ActivatePath(nullptr);
        path.reset();
        wi::scene::GetScene().Clear();
        if (window)
            DestroyWindow(window);
        window = nullptr;
        app.reset();
    }
    void set_quality(const std::string &q) {
        quality = q;
        path->setShadowsEnabled(q != "low");
        path->setFXAAEnabled(true);
        path->setBloomEnabled(q != "low");
        path->setSSREnabled(q == "high");
        path->setSSGIEnabled(q == "high");
        path->setMotionBlurEnabled(false);
        path->setEyeAdaptionEnabled(false);
        path->setFSR2Enabled(false);
    }
    void configure_world(const bvr_sim::GameTerrain &terrain, const std::array<double, 3> &target,
                         const std::array<double, 3> &runway, float length, float width, uint32_t seed,
                         const std::string &asphalt, const std::string &grass) {
        auto &s = wi::scene::GetScene();
        for (auto e : world_entities)
            s.Entity_Remove(e);
        world_entities.clear();
        wi::vector<XMFLOAT3> vertices;
        wi::vector<uint32_t> indices;
        for (int row = 0; row < terrain.rows; ++row)
            for (int col = 0; col < terrain.columns; ++col)
                vertices.push_back({float(-terrain.origin_west - row * terrain.spacing),
                                    float(terrain.heights[row * terrain.columns + col]),
                                    float(terrain.origin_north + col * terrain.spacing)});
        for (int row = 0; row < terrain.rows - 1; ++row)
            for (int col = 0; col < terrain.columns - 1; ++col) {
                uint32_t a = row * terrain.columns + col, b = a + terrain.columns;
                for (auto x : {a, a + 1, b, a + 1, b + 1, b})
                    indices.push_back(x);
            }
        auto ground = s.Entity_CreateMeshFromData("physics_heightfield", indices.size(), indices.data(),
                                                  vertices.size(), vertices.data());
        world_entities.push_back(ground);
        auto ground_mat = s.materials.GetComponent(ground);
        ground_mat->SetBaseColor({.65f, .7f, .5f, 1});
        ground_mat->SetRoughness(.9f);
        auto ground_mesh = s.meshes.GetComponent(ground);
        for (auto v : vertices)
            ground_mesh->vertex_uvset_0.push_back({v.x / 2, v.z / 2});
        std::mt19937 tint_rng(seed);
        std::uniform_int_distribution<int> terrain_tint(155, 255);
        for (size_t i = 0; i < vertices.size(); ++i) {
            int c = terrain_tint(tint_rng);
            ground_mesh->vertex_colors.push_back(wi::Color(c, c, c, 255).rgba);
        }
        ground_mat->SetUseVertexColors(true);
        if (!grass.empty()) {
            if (!std::filesystem::exists(grass))
                throw std::runtime_error("Missing terrain texture: " + grass);
            ground_mat->textures[wi::scene::MaterialComponent::BASECOLORMAP].name = grass;
            ground_mat->textures[wi::scene::MaterialComponent::BASECOLORMAP].resource =
                wi::resourcemanager::Load(grass);
            ground_mat->SetDirty();
        }
        ground_mesh->CreateRenderData();
        auto add = [&](std::string name, XMFLOAT3 pos, XMFLOAT3 scale, XMFLOAT4 color) {
            auto e = cube(name, pos, scale, color);
            world_entities.push_back(e);
            return e;
        };
        depot = add("depot_building", {float(-target[1]), float(target[2] + 7), float(target[0])},
                    {14, 7, 22}, {.40f, .37f, .30f, 1});
        auto strip = add("runway", {float(-runway[1]), float(runway[2] + .2), float(runway[0])},
                         {width / 2, .2f, length / 2}, {.3f, .3f, .3f, 1});
        if (!asphalt.empty()) {
            if (!std::filesystem::exists(asphalt))
                throw std::runtime_error("Missing runway texture: " + asphalt);
            auto m = s.materials.GetComponent(strip);
            m->textures[wi::scene::MaterialComponent::BASECOLORMAP].name = asphalt;
            m->textures[wi::scene::MaterialComponent::BASECOLORMAP].resource =
                wi::resourcemanager::Load(asphalt);
            m->texMulAdd = {4, 80, 0, 0};
            m->SetDirty();
        }
        for (int i = 0; i < 30; ++i)
            add("runway_mark",
                {float(-runway[1]), float(runway[2] + .45),
                 float(runway[0] - length * .46 + length * i / 30)},
                {.8f, .05f, 12}, {.85f, .85f, .78f, 1});
        // Seeded fields give altitude/speed cues. They are terrain surface markings.
        std::mt19937 rng(seed);
        std::uniform_real_distribution<float> offset(-18000, 18000), size(150, 700), tint(.7f, 1.1f);
        for (int i = 0; i < 140; ++i) {
            float n = offset(rng), w = offset(rng);
            if ((std::abs(w) < 1000 && n > 1000 && n < 7000) || terrain.height(n, w) > 1)
                continue;
            float c = tint(rng);
            add("field", {-w, float(terrain.height(n, w) + .04), n}, {size(rng), .015f, size(rng)},
                {.18f * c, .21f * c, .10f * c, 1});
        }
    }
    void place_asset(const std::string &uid, const std::string &model, const std::array<double, 3> &pos,
                     float scale) {
        auto e = import_model(uid, model);
        roots.erase(uid);
        world_entities.push_back(e);
        auto t = wi::scene::GetScene().transforms.GetComponent(e);
        t->Scale(XMFLOAT3(scale, scale, scale));
        t->Translate(XMFLOAT3(float(-pos[1]), float(pos[2]), float(pos[0])));
        t->UpdateTransform();
    }
    void configure_scene(const bvr_sim::GameTerrain &terrain, const std::vector<int> &cover,
                         const std::vector<std::array<float, 4>> &colors,
                         const std::vector<SceneMaterial> &materials,
                         const std::vector<SceneSurface> &surfaces,
                         const std::vector<ScenePlacement> &placements, const std::vector<int> &outer_cover,
                         const std::vector<std::array<float, 4>> &outer_colors) {
        baked_world->configure(terrain, cover, colors, materials, surfaces, placements, outer_cover,
                               outer_colors);
    }
    SceneStats statistics() const { return baked_world->stats(path->visibility_main); }
    double render_height(double n, double w) const { return baked_world->render_height(n, w); }
    void presentation(bool hangar) {
        studio = hangar;
        path->setlayerMask(hangar ? 2 : 1);
    }
    void configure_audio(const std::map<std::string, std::string> &files, bool enabled) {
        audio.configure(files, enabled);
    }
    std::map<std::string, uint64_t> audio_counts() const { return audio.counts; }
    std::map<std::string, bool> audio_available() const { return audio.available; }
    Input poll() {
        Input in;
        if (closed) {
            in.quit = true;
            return in;
        }
        MSG m;
        while (PeekMessage(&m, window, 0, 0, PM_REMOVE)) {
            if (m.message == WM_APP + 1)
                in.quit = true;
            TranslateMessage(&m);
            DispatchMessage(&m);
        }
        in.active = GetForegroundWindow() == window;
        POINT p;
        GetCursorPos(&p);
        ScreenToClient(window, &p);
        in.x = float(p.x);
        in.y = float(p.y);
        for (int k = 1; k < 256; ++k) {
            bool down = in.active && (GetAsyncKeyState(k) & 0x8000);
            if (down)
                in.held.push_back(k);
            if (down && !previous[k])
                in.pressed.push_back(k);
            previous[k] = down;
        }
        return in;
    }
    void camera(const std::array<float, 3> &eye, const std::array<float, 3> &target, float fov) {
        camera_up_vector = {0, 1, 0};
        camera_eye = {eye[0], eye[1], eye[2]};
        camera_at = {target[0], target[1], target[2]};
        camera_set = true;
        auto &c = *path->camera;
        c.fov = fov;
        c.Eye = camera_eye;
        XMStoreFloat3(&c.At, XMVector3Normalize(XMLoadFloat3(&camera_at) - XMLoadFloat3(&camera_eye)));
        c.Up = {0, 1, 0};
        c.SetDirty();
        c.UpdateCamera();
    }
    void camera_up(const std::array<float, 3> &up) { camera_up_vector = {up[0], up[1], up[2]}; }
    std::array<float, 3> project(const std::array<double, 3> &nwu) {
        auto c = path->camera;
        auto p =
            XMVector3Project(XMVectorSet(float(-nwu[1]), float(nwu[2]), float(nwu[0]), 1), 0, 0, float(width),
                             float(height), 0, 1, c->GetProjection(), c->GetView(), XMMatrixIdentity());
        std::array<float, 3> r;
        XMStoreFloat3(reinterpret_cast<XMFLOAT3 *>(r.data()), p);
        return r;
    }
    void render(const bvr_sim::GameFrame &f, const std::vector<HudText> &texts,
                const std::vector<HudLine> &lines) {
        if (closed)
            throw std::runtime_error("Renderer closed");
        baked_world->update(camera_eye, f);
        audio.update(f, studio);
        if (!studio)
            effects->update(f);
        auto &s = wi::scene::GetScene();
        wi::unordered_set<std::string> live;
        if (depot != wi::ecs::INVALID_ENTITY) {
            bool alive = false;
            for (const auto &e : f.entities)
                if (e.uid == "depot")
                    alive = e.alive;
            auto mat = s.materials.GetComponent(depot);
            if (mat) {
                mat->SetBaseColor(alive ? XMFLOAT4(.40f, .37f, .30f, 1) : XMFLOAT4(.08f, .07f, .06f, 1));
            }
        }
        for (const auto &e : f.entities) {
            if (studio && e.uid != "player")
                continue;
            if (!e.alive)
                continue;
            live.insert(e.uid);
            Entity root;
            auto it = roots.find(e.uid);
            if (it == roots.end()) {
                if (e.kind == "aircraft") {
                    root = import_model(e.uid, e.model);
                    exhaust(root, e.model);
                } else if (e.kind == "missile" || e.kind == "bomb") {
                    root = s.Entity_CreateSphere(e.uid, 1, 10, 8);
                    auto body = s.transforms.GetComponent(root);
                    // Dimensions are metres: AIM-120 3.65 x .178; Mk-82 generic 2.2 x .27.
                    auto mesh = s.meshes.GetComponent(root);
                    for (auto &p : mesh->vertex_positions) {
                        p.x *= e.kind == "bomb" ? .135f : .089f;
                        p.y *= e.kind == "bomb" ? .135f : .089f;
                        p.z *= e.kind == "bomb" ? 1.1f : 1.825f;
                    }
                    mesh->CreateRenderData();
                    s.materials.GetComponent(root)->SetBaseColor(
                        e.kind == "bomb" ? XMFLOAT4(.18f, .23f, .12f, 1) : XMFLOAT4(.8f, .8f, .8f, 1));
                    roots[e.uid] = root;
                    if (e.kind == "missile") {
                        auto flame =
                            cube("missile_motor", {0, 0, -2.3f}, {.08f, .08f, .7f}, {1, .45f, .02f, 1});
                        s.Component_Attach(flame, root, true);
                        s.materials.GetComponent(flame)->SetEmissiveColor({1, .4f, .02f, 4});
                        weapon_flames[root] = flame;
                    }
                } else
                    continue;
            } else
                root = it->second;
            auto t = s.transforms.GetComponent(root);
            s.layers.GetComponent(root)->layerMask = studio ? 2 : 1;
            t->ClearTransform();
            // Converted glTF: +Z forward, +Y up, +X starboard. NWU maps (west,up,north).
            if (!studio)
                t->RotateRollPitchYaw(
                    XMFLOAT3(float(-e.orientation[1]), float(-e.orientation[2]), float(-e.orientation[0])));
            t->Translate(studio
                             ? XMFLOAT3(0, 2.1f, 0)
                             : XMFLOAT3(float(-e.position[1]), float(e.position[2]), float(e.position[0])));
            t->UpdateTransform();
            if (weapon_flames.count(root))
                s.objects.GetComponent(weapon_flames[root])->SetRenderable(e.motor_burning);
            for (auto effect : engine_effects[root])
                if (auto material = s.materials.GetComponent(effect)) {
                    float intensity = studio ? 0 : float(std::clamp((e.throttle - .35) / .65, 0.0, 1.0));
                    s.objects.GetComponent(effect)->SetRenderable(intensity > .02f);
                    material->SetEmissiveColor({1, .25f, .03f, intensity * 4});
                    material->SetBaseColor({intensity, .15f * intensity, .01f, 1});
                }
        }
        for (auto it = roots.begin(); it != roots.end();) {
            if (!live.count(it->first)) {
                s.Entity_Remove(it->second);
                engine_effects.erase(it->second);
                weapon_flames.erase(it->second);
                it = roots.erase(it);
            } else
                ++it;
        }
        for (const auto &event : f.events)
            if ((event.kind == "missile_hit" || event.kind == "bomb_impact") && f.tick - event.tick <= 50) {
                std::string id = event.kind + std::to_string(event.tick);
                if (!flashes.count(id)) {
                    auto e = s.Entity_CreateSphere("impact_flash", 1, 12, 12);
                    auto t = s.transforms.GetComponent(e);
                    bool ground_blast = event.kind == "bomb_impact";
                    t->Scale(ground_blast ? XMFLOAT3(12, 18, 12) : XMFLOAT3(8, 8, 8));
                    t->Translate(XMFLOAT3(float(-event.position[1]),
                                          float(event.position[2] + (ground_blast ? 10 : 2)),
                                          float(event.position[0])));
                    t->UpdateTransform();
                    auto mat = s.materials.GetComponent(e);
                    mat->SetBaseColor({1, .15f, .01f, 1});
                    mat->SetEmissiveColor({1, .2f, .01f, 5});
                    flashes[id] = {e, event.tick};
                }
            }
        for (auto it = flashes.begin(); it != flashes.end();) {
            if (f.tick < it->second.second || f.tick - it->second.second > 50) {
                s.Entity_Remove(it->second.first);
                it = flashes.erase(it);
            } else
                ++it;
        }
        if (camera_set) {
            auto &c = *path->camera;
            c.Eye = camera_eye;
            XMStoreFloat3(&c.At, XMVector3Normalize(XMLoadFloat3(&camera_at) - XMLoadFloat3(&camera_eye)));
            c.Up = camera_up_vector;
            c.SetDirty();
            c.UpdateCamera();
        }
        path->texts = texts;
        path->lines = lines;
        // Queue new glyphs before Application::Run updates the atlas. This also
        // makes the first flight/debrief capture complete after a menu change.
        for (const auto &text : texts) {
            wi::font::Params params(text.x, text.y, text.size);
            wi::font::TextSize(text.text, params);
        }
        // Retain the buffer BEFORE Present advances the swapchain index.
        last_frame = wi::graphics::GetDevice()->GetBackBuffer(&app->swapChain);
        app->Run();
    }
    std::string capture(const std::string &filename) {
        if (closed || !last_frame.IsValid())
            throw std::runtime_error("Render a frame before capture");
        std::filesystem::create_directories(std::filesystem::path(filename).parent_path());
        if (!wi::helper::saveTextureToFile(last_frame, filename))
            throw std::runtime_error("GPU capture failed");
        return filename;
    }
    int shader_errors() const {
        return wi::renderer::GetShaderErrorCount() + wi::renderer::GetShaderMissingCount();
    }
    void reload() {
        auto &s = wi::scene::GetScene();
        for (auto [_, e] : roots)
            s.Entity_Remove(e);
        roots.clear();
        engine_effects.clear();
        weapon_flames.clear();
        if (effects)
            effects->clear();
        for (auto [_, e] : flashes)
            s.Entity_Remove(e.first);
        flashes.clear();
    }
};
PYBIND11_MODULE(bvr_game_render, m) {
    py::class_<ScenePlacement>(m, "ScenePlacement")
        .def(py::init<>())
        .def_readwrite("id", &ScenePlacement::id)
        .def_readwrite("model", &ScenePlacement::model)
        .def_readwrite("chunk", &ScenePlacement::chunk)
        .def_readwrite("category", &ScenePlacement::category)
        .def_readwrite("target_uid", &ScenePlacement::target_uid)
        .def_readwrite("position", &ScenePlacement::position)
        .def_readwrite("yaw", &ScenePlacement::yaw)
        .def_readwrite("scale", &ScenePlacement::scale)
        .def_readwrite("lod_distance", &ScenePlacement::lod_distance)
        .def_readwrite("cull_distance", &ScenePlacement::cull_distance);
    py::class_<SceneMaterial>(m, "SceneMaterial")
        .def(py::init<>())
        .def_readwrite("id", &SceneMaterial::id)
        .def_readwrite("base_color", &SceneMaterial::base_color)
        .def_readwrite("normal", &SceneMaterial::normal)
        .def_readwrite("color", &SceneMaterial::color)
        .def_readwrite("tile_m", &SceneMaterial::tile_m)
        .def_readwrite("roughness", &SceneMaterial::roughness)
        .def_readwrite("water", &SceneMaterial::water);
    py::class_<SceneSurface>(m, "SceneSurface")
        .def(py::init<>())
        .def_readwrite("id", &SceneSurface::id)
        .def_readwrite("material", &SceneSurface::material)
        .def_readwrite("vertices", &SceneSurface::vertices)
        .def_readwrite("indices", &SceneSurface::indices);
    py::class_<SceneStats>(m, "SceneStats")
        .def_readonly("unique_models", &SceneStats::unique_models)
        .def_readonly("imported_glbs", &SceneStats::imported_glbs)
        .def_readonly("mesh_resources", &SceneStats::mesh_resources)
        .def_readonly("material_resources", &SceneStats::material_resources)
        .def_readonly("instances", &SceneStats::instances)
        .def_readonly("visible_instances", &SceneStats::visible_instances)
        .def_readonly("visible_objects", &SceneStats::visible_objects)
        .def_readonly("visible_triangles", &SceneStats::visible_triangles)
        .def_readonly("visible_mesh_subset_groups", &SceneStats::visible_mesh_subset_groups)
        .def_readonly("import_counts", &SceneStats::import_counts)
        .def_readonly("chunk_instances", &SceneStats::chunk_instances)
        .def_readonly("visible_lods", &SceneStats::visible_lods)
        .def_readonly("visible_chunks", &SceneStats::visible_chunks);
    py::class_<HudText>(m, "HudText")
        .def(py::init<>())
        .def_readwrite("x", &HudText::x)
        .def_readwrite("y", &HudText::y)
        .def_readwrite("size", &HudText::size)
        .def_readwrite("text", &HudText::text)
        .def_readwrite("color", &HudText::color);
    py::class_<HudLine>(m, "HudLine")
        .def(py::init<>())
        .def_readwrite("x", &HudLine::x)
        .def_readwrite("y", &HudLine::y)
        .def_readwrite("w", &HudLine::w)
        .def_readwrite("h", &HudLine::h)
        .def_readwrite("color", &HudLine::color)
        .def_readwrite("rotation", &HudLine::rotation);
    py::class_<Input>(m, "Input")
        .def_readonly("x", &Input::x)
        .def_readonly("y", &Input::y)
        .def_readonly("active", &Input::active)
        .def_readonly("quit", &Input::quit)
        .def_readonly("held", &Input::held)
        .def_readonly("pressed", &Input::pressed);
    py::class_<Renderer>(m, "Renderer")
        .def(py::init<int, int, bool, const std::string &, const std::string &,
                      const std::map<std::string, std::string> &>())
        .def("render", &Renderer::render)
        .def("poll", &Renderer::poll)
        .def("camera", &Renderer::camera)
        .def("camera_up", &Renderer::camera_up)
        .def("project", &Renderer::project)
        .def("capture", &Renderer::capture)
        .def("reload", &Renderer::reload)
        .def("set_quality", &Renderer::set_quality)
        .def("shader_errors", &Renderer::shader_errors)
        .def("configure_world", &Renderer::configure_world)
        .def("configure_scene", &Renderer::configure_scene)
        .def("statistics", &Renderer::statistics)
        .def("render_height", &Renderer::render_height)
        .def("presentation", &Renderer::presentation)
        .def("configure_audio", &Renderer::configure_audio)
        .def("audio_counts", &Renderer::audio_counts)
        .def("audio_available", &Renderer::audio_available)
        .def("place_asset", &Renderer::place_asset)
        .def("close", &Renderer::close);
}
