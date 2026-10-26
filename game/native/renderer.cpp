#include "WickedEngine.h"
#ifdef BVR_FAR_DISTANCE
namespace wi::renderer {float BvrDrawDistanceRoundTrip(float);}
#endif
#include "ModelImporter.h" // Upstream importer declarations require WickedEngine.h first.
#include "gameplay/game_session.hxx"
#include <Windows.h>
#include <Xinput.h>
#include <atomic>
#include <filesystem>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include <functional>
#include <random>
#include <stdexcept>
#include <unordered_map>
#include <chrono>
#include <thread>
#include "world_scene.hxx"
#include "audio_presenter.hxx"
#include "visual_effects.hxx"
#include "aircraft_visuals.hxx"
#include "hangar_scene.hxx"
#include "cloud_profile.hxx"
namespace py = pybind11;
using namespace DirectX;
using wi::ecs::Entity;
namespace wi::profiler { std::map<std::string,double> GetTimingSnapshot(bool gpu); }
namespace wi::graphics { std::map<std::string,uint64_t> GetBvrDescriptorState(); }
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
    int wheel = 0;
    bool active = false, quit = false;
    int width=0,height=0;
    bool pad_connected=false;
    std::array<float,6> pad_axes{};
    std::vector<int> held, pressed;
};
struct HudImage {
    float x=0,y=0,w=1,h=1;
    std::string file;
};
class GamePath : public wi::RenderPath3D {
  public:
    std::function<void()> before_visibility;
    bool presentation_paused=false;
    bool planar_reflections_enabled=true;
    std::map<std::string,double> cpu_timings;
    const wi::graphics::Texture& sampled_depth() const {return depthBuffer_Copy;}
    void Update(float dt) override {
        const auto begin=std::chrono::steady_clock::now();
        wi::RenderPath3D::Update(dt);
        cpu_timings["engine_update_ms"]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-begin).count();
    }
    void PreRender() override {
        const auto begin=std::chrono::steady_clock::now();
        if(before_visibility)before_visibility();
        const auto bounds_end=std::chrono::steady_clock::now();
        cpu_timings["ground_bounds_ms"]=std::chrono::duration<double,std::milli>(bounds_end-begin).count();
        // Scene::Update needs positive dt to allocate/upload new geometry.
        // Freeze only shader time while constructing this frame's constants;
        // camera, visibility, glyphs and scene uploads must keep working.
        struct RestoreSpeed {
            float previous;bool active;
            ~RestoreSpeed(){if(active)wi::renderer::SetGameSpeed(previous);}
        } restore{wi::renderer::GetGameSpeed(),presentation_paused};
        if(presentation_paused)wi::renderer::SetGameSpeed(0);
        wi::RenderPath3D::PreRender();
        if(!planar_reflections_enabled){
            // Retain water geometry/SSR/sky lighting, but avoid rendering the
            // full forest again through the mirrored camera. Never sample a
            // stale or uninitialised planar target when that pass is disabled.
            visibility_main.planar_reflection_visible=false;
            camera->texture_reflection_index=-1;
            camera->texture_reflection_depth_index=-1;
        }
        cpu_timings["engine_prerender_ms"]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-bounds_end).count();
    }
    std::vector<HudText> texts;
    std::vector<HudLine> lines;
    std::vector<HudImage> images;
    std::map<std::string,wi::Resource> image_resources;
    int ui_font=0;
    bool menu_blur=false;
    void Compose(wi::graphics::CommandList cmd) const override {
        // Profiling is an Agent-readable API, not a product overlay. Keep
        // diagnostic text out of scene captures while retaining timestamps.
        wi::profiler::DisableDrawForThisFrame();
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
        for(const auto& i:images){
            const auto found=image_resources.find(i.file);
            if(found==image_resources.end())continue;
            wi::image::Params p;p.pos={i.x,i.y,0};p.siz={i.w,i.h};
            wi::image::Draw(&found->second.GetTexture(),p,cmd);
        }
        for (const auto &t : texts) {
            wi::font::Params p(t.x, t.y, t.size);
            p.style=ui_font;
            p.color = wi::Color(t.color);
            p.shadowColor = wi::Color(0, 0, 0, 200);
            p.shadow_offset_x = p.shadow_offset_y = 1;
            wi::font::Draw(t.text, p, cmd);
        }
    }
};
class Renderer {
    inline static int wheel_delta = 0;
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
    Entity preview_root = wi::ecs::INVALID_ENTITY;
    std::vector<Entity> studio_entities;
    std::map<Entity, std::vector<Entity>> engine_effects;
    AudioPresenter audio;
    std::unique_ptr<VisualEffects> effects;
    std::unique_ptr<AircraftVisuals> aircraft_visuals;
    std::map<Entity, Entity> weapon_flames;
    nlohmann::json visual_profile;
    std::map<std::string,double> cpu_timings;
    Entity weather_entity=wi::ecs::INVALID_ENTITY;
    Entity sun_entity=wi::ecs::INVALID_ENTITY;
    static LRESULT CALLBACK wndproc(HWND h, UINT m, WPARAM w, LPARAM l) {
        if (m == WM_CLOSE) {
            PostMessage(h, WM_APP + 1, 0, 0);
            return 0;
        }
        if (m == WM_INPUT) {
            wi::input::rawinput::ParseMessage((void *)l);
            return 0;
        }
        if (m == WM_MOUSEWHEEL) {
            wheel_delta += GET_WHEEL_DELTA_WPARAM(w) / WHEEL_DELTA;
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
            auto e = visual_profile.is_null()?s.Entity_CreateSphere("engine_glow", 1, 10, 10):soft_sprite(s,"afterburner",{1,.4f,.09f,.45f},1.2f);
            auto t = s.transforms.GetComponent(e);
            if(visual_profile.is_null())t->Scale(XMFLOAT3(.22f, .22f, .6f));
            else {t->Scale(XMFLOAT3(.18f,.75f,1));t->RotateRollPitchYaw(XMFLOAT3(DirectX::XM_PIDIV2,0,0));}
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
             const std::map<std::string, std::string> &models,const std::string& profile_file="")
        : model_files(models.begin(), models.end()), width(w), height(h) {
        auto core=py::module_::import("bvr_sim.bvr_sim_cpp");
        if(!py::hasattr(core,"GAME_API_ABI")||core.attr("GAME_API_ABI").cast<int>()!=2)
            throw std::runtime_error("Core/renderer Game API ABI mismatch: rebuild matching native modules");
        if (w < 320 || h < 240)
            throw std::invalid_argument("Window too small");
        // Wicked owns process-global GPU jobs/resources; rebuilding that
        // runtime after ShutDown caused a reproducible native crash. Reuse the
        // resident Renderer/scene reset, or start a fresh process instead.
        static std::atomic_flag process_gpu_started=ATOMIC_FLAG_INIT;
        if(process_gpu_started.test_and_set())throw std::runtime_error("One Wicked Renderer lifetime per process: reuse the resident Renderer or start a new process");
        if (!LoadLibraryW(std::filesystem::path(engine + "/WickedEngine/dxcompiler.dll").c_str()))
            throw std::runtime_error("Cannot load Wicked Engine dxcompiler.dll");
        wi::arguments::Parse(L"alwaysactive dx12");
        if(!profile_file.empty()){
            std::ifstream file(profile_file);
            if(!file)throw std::runtime_error("Cannot read visual profile: "+profile_file);
            file>>visual_profile;
        }
        const int worker_threads=visual_profile.value("worker_threads",0);
        if(worker_threads<0||worker_threads>64)throw std::invalid_argument("worker_threads must be0(auto) or1..64");
        if(worker_threads>0)wi::jobsystem::Initialize(uint32_t(worker_threads));
#ifdef BVR_WIDE_PRIMITIVE_IDS
        if(visual_profile.is_null()||!visual_profile.value("wide_primitive_id_raster",false))throw std::runtime_error("Direct64-bit renderer requires its prepared wide primitive-ID shader profile");
        wi::renderer::SetMeshShaderAllowed(false);
#else
        if(!visual_profile.is_null()&&visual_profile.value("wide_primitive_id_raster",false))throw std::runtime_error("Wide primitive-ID shaders require the matching native renderer");
#endif
        wi::renderer::SetShaderSourcePath((visual_profile.is_null()?engine+"/WickedEngine/shaders":visual_profile.value("shader_source",engine+"/WickedEngine/shaders"))+"/");
        wi::renderer::SetShaderPath((visual_profile.is_null()?shaders:visual_profile.value("shader_cache",shaders))+"/");
        SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2);
        WNDCLASSW wc{};
        wc.lpfnWndProc = wndproc;
        wc.hInstance = GetModuleHandle(nullptr);
        wc.lpszClassName = L"BvrWickedGame";
        wc.hCursor = LoadCursor(nullptr, IDC_CROSS);
        RegisterClassW(&wc);
        RECT r{0, 0, w, h};
        AdjustWindowRect(&r, WS_OVERLAPPEDWINDOW, FALSE);
        window = CreateWindowW(wc.lpszClassName, L"BVR SIM | Flight Operations",
                               WS_OVERLAPPEDWINDOW, 100, 80,
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
        // Shader errors can be zero while asynchronous object PSOs are still
        // compiling. Do not start gameplay/capture against an empty opaque pass.
        auto loading_deadline=std::chrono::steady_clock::now()+std::chrono::seconds(120);
        while(wi::renderer::IsPipelineCreationActive()){
            if(std::chrono::steady_clock::now()>loading_deadline)throw std::runtime_error("Timed out waiting for Wicked object shader pipelines");
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
        path = std::make_unique<GamePath>();
        app->ActivatePath(path.get());
        path->planar_reflections_enabled=visual_profile.value("planar_reflections",true);
        path->camera->CreatePerspective(float(w), float(h), .2f,600000.f, 1.05f);
        set_quality("medium");
        set_render_scale(visual_profile.value("render_scale",1.f));
        auto &s = wi::scene::GetScene();
        baked_world = std::make_unique<WorldScene>(s, model_files,visual_profile);
        wi::renderer::SetOcclusionCullingEnabled(visual_profile.value("occlusion_culling",true));
        path->before_visibility=[this](){baked_world->ground_bounds_before_visibility();};
#ifdef BVR_WIDE_PRIMITIVE_IDS
        set_visibility_compute(visual_profile.value("visibility_compute_shading",false));
#endif
        effects = std::make_unique<VisualEffects>(s,!visual_profile.is_null());
        aircraft_visuals = std::make_unique<AircraftVisuals>(s);
        aircraft_visuals->set_material_profile(visual_profile);
        if(!visual_profile.is_null()&&visual_profile.contains("aircraft_exhaust_profiles_file")){
            auto file=std::filesystem::path(profile_file).parent_path()/visual_profile.at("aircraft_exhaust_profiles_file").get<std::string>();
            std::ifstream input(file);if(!input)throw std::runtime_error("Cannot read source aircraft exhaust profiles: "+file.string());
            nlohmann::json profiles;input>>profiles;
            if(profiles.at("schema_version").get<int>()!=1)throw std::runtime_error("Unsupported source exhaust profile schema");
            aircraft_visuals->set_exhaust_profiles(profiles.at("aircraft"));
        }
        auto weather = weather_entity=wi::ecs::CreateEntity();
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
        auto sun = sun_entity=s.Entity_CreateLight("sun", {0, 100, 0}, {1, .94f, .84f}, visual_profile.is_null()?4.f:visual_profile.value("sun_energy",4.f), 100000,
                                        wi::scene::LightComponent::DIRECTIONAL);
        auto t = s.transforms.GetComponent(sun);
        t->RotateRollPitchYaw(XMFLOAT3(-.65f, -.6f, 0));
        t->UpdateTransform();
        s.lights.GetComponent(sun)->SetCastShadow(true);
        if(!visual_profile.is_null()&&visual_profile.contains("sun_shadow_cascades_m"))
            set_shadow_cascades(visual_profile.at("sun_shadow_cascades_m").get<std::vector<float>>());
        if(!visual_profile.is_null()&&visual_profile.contains("sun_shadow_resolution")&&!visual_profile.at("sun_shadow_resolution").is_number_integer())
            throw std::invalid_argument("Sun shadow resolution must be an integer");
        if(!visual_profile.is_null()&&visual_profile.contains("sun_shadow_resolution"))
            set_shadow_resolution(visual_profile.at("sun_shadow_resolution").get<int>());
        if(!visual_profile.is_null()){
            sky.SetRealisticSky(visual_profile.value("physical_sky",true));
            sky.SetRealisticSkyAerialPerspective(visual_profile.value("aerial_perspective",true));
            sky.SetRealisticSkyHighQuality(visual_profile.value("high_quality_sky",false));
            sky.SetVolumetricClouds(visual_profile.value("volumetric_clouds",false));
            auto a=visual_profile.at("ambient");sky.ambient={a[0].get<float>(),a[1].get<float>(),a[2].get<float>()};
            sky.skyExposure=visual_profile.value("sky_exposure",1.f);
            // Aerial perspective already integrates atmospheric extinction.
            // A weak height-fog layer begins beyond 100 km and applies to both
            // the sky planet and finite terrain to make their horizon continuous.
            auto haze=visual_profile.value("horizon_height_fog",nlohmann::json::object());
            sky.SetHeightFog(haze.value("enabled",true));sky.fogStart=haze.value("start_m",100000.f);sky.fogDensity=haze.value("density_per_m",.00005f);
            sky.fogHeightStart=haze.value("base_m",0.f);sky.fogHeightEnd=haze.value("top_m",16000.f);sky.stars=0;
            auto albedo=visual_profile.value("planet_albedo",std::vector<float>{.12f,.16f,.1f});
            sky.atmosphereParameters.groundAlbedo={albedo[0],albedo[1],albedo[2]};
            auto r=visual_profile.at("sun_rotation");t->ClearTransform();t->RotateRollPitchYaw(XMFLOAT3(r[0].get<float>(),r[1].get<float>(),r[2].get<float>()));t->UpdateTransform();
            path->setExposure(visual_profile.value("exposure",1.f));
            path->setSaturation(visual_profile.value("saturation",1.f));
            path->setTonemap(wi::renderer::Tonemap::ACES);
        }
        s.layers.Create(sun).layerMask = 1;
        apply_cloud_profile(sky,visual_profile);
        build_hangar_apron([&](auto name,auto position,auto scale,auto color){return cube(name,position,scale,color);},studio_entities);
        auto hangar_sun=s.Entity_CreateLight("hangar_daylight",{0,100,0},{1,.94f,.84f},3.2f,100000,wi::scene::LightComponent::DIRECTIONAL);
        s.layers.Create(hangar_sun).layerMask=2;
        auto hs=s.transforms.GetComponent(hangar_sun);hs->RotateRollPitchYaw(XMFLOAT3(-.8f,-.5f,0));hs->UpdateTransform();
        s.lights.GetComponent(hangar_sun)->SetCastShadow(true);studio_entities.push_back(hangar_sun);
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
        const bool taa=!visual_profile.is_null()&&visual_profile.value("temporal_aa",false);
        wi::renderer::SetTemporalAAEnabled(taa);
        path->setFXAAEnabled(visual_profile.is_null()?true:visual_profile.value("fxaa",!taa));
        path->setBloomEnabled(q != "low");
        path->setSSREnabled(q == "high");
        path->setSSGIEnabled(q == "high");
        path->setMotionBlurEnabled(false);
        path->setEyeAdaptionEnabled(false);
        path->setFSR2Enabled(false);
    }
    void set_visibility_compute(bool enabled){
        if(enabled&&!visual_profile.value("wide_visibility_compute_v1",false))
            throw std::invalid_argument("Visibility shading requires its prepared direct64 material-parity shaders");
        path->setVisibilityComputeShadingEnabled(enabled);
    }
    void set_occlusion_culling(bool enabled){wi::renderer::SetOcclusionCullingEnabled(enabled);}
    void set_planar_reflections(bool enabled){path->planar_reflections_enabled=enabled;}
    void set_ui_font(const std::string& file) {
        if(!std::filesystem::is_regular_file(file))throw std::runtime_error("Missing UI font: "+file);
        path->ui_font=wi::font::AddFontStyle(file);
    }
    void set_menu_overlay(bool blur,const std::vector<HudImage>& images) {
        path->menu_blur=blur;path->images=images;
        path->setDepthOfFieldEnabled(blur);
        path->camera->focal_length=1.f;
        path->camera->aperture_size=blur?.7f:0.f;
        for(const auto& i:images)if(!path->image_resources.count(i.file)){
            if(!std::filesystem::is_regular_file(i.file))throw std::runtime_error("Missing UI thumbnail: "+i.file);
            path->image_resources[i.file]=wi::resourcemanager::Load(i.file);
        }
    }
    void set_audio_volume(float volume){wi::audio::SetVolume(std::clamp(volume,0.f,1.f));}
    void set_hangar_floor_texture(const std::string& file){
        auto& s=wi::scene::GetScene();
        for(auto e:studio_entities)if(auto name=s.names.GetComponent(e);name&&name->name=="apron_concrete"){
            auto mat=s.materials.GetComponent(e);auto mesh=s.meshes.GetComponent(e);
            auto& slot=mat->textures[wi::scene::MaterialComponent::BASECOLORMAP];slot.name=file;slot.resource=wi::resourcemanager::Load(file);
            mat->texMulAdd={60,60,0,0};mat->SetBaseColor({.7f,.7f,.7f,1});mat->SetDirty();
        }
    }
    void configure_world(const bvr_sim::GameTerrain &terrain, const std::array<double, 3> &target,
                         const std::array<double, 3> &runway, float length, float width, uint32_t seed,
                         const std::string &asphalt, const std::string &grass) {
        auto &s = wi::scene::GetScene();
        wi::graphics::GetDevice()->WaitForGPU();
        baked_world->clear();
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
        // Legacy terrain must not leak through the independent hangar apron.
        for(auto e:world_entities)s.layers.Create(e).layerMask=1;
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
                         const std::vector<std::array<float, 4>> &outer_colors,
                         const std::vector<std::string> &terrain_materials) {
        wi::graphics::GetDevice()->WaitForGPU();
        auto& scene = wi::scene::GetScene();
        for (auto e : world_entities) scene.Entity_Remove(e);
        world_entities.clear();
        baked_world->configure(terrain, cover, colors, materials, surfaces, placements, outer_cover,
                               outer_colors, terrain_materials);
    }
    void register_scene_models(const std::unordered_map<std::string, std::string>& models) {
        // Registered asset IDs are immutable. A different resource version must
        // use a distinct ID so cached prototype meshes cannot silently change.
        for (const auto& [id, file] : models) {
            auto old = model_files.find(id);
            if (old != model_files.end() && std::filesystem::path(old->second).lexically_normal() != std::filesystem::path(file).lexically_normal())
                throw std::invalid_argument("Map asset ID already names a different resource: " + id);
        }
        for (const auto& [id, file] : models) model_files.emplace(id, file);
    }
    SceneStats statistics() const { return baked_world->stats(path->visibility_main); }
    void set_vegetation_lod_distance(double meters){baked_world->set_vegetation_lod_distance(meters);}
    std::string vegetation_state() const{return baked_world->vegetation_state().dump();}
    void set_spatial_vegetation_lod(bool enabled){baked_world->set_spatial_vegetation_lod(enabled);}
    py::bytes vegetation_lod_bytes() const {const auto states=baked_world->vegetation_lod_states();return py::bytes(reinterpret_cast<const char*>(states.data()),states.size());}
    void set_static_cache_enabled(bool enabled){baked_world->set_static_cache_enabled(enabled);}
    std::map<std::string,uint64_t> static_cache_state() const{return baked_world->static_cache_state();}
    void set_inline_ground_bounds(bool enabled){baked_world->set_inline_ground_bounds(enabled);}
    void configure_ground_atlas(py::array_t<float,py::array::c_style> values,float north,float west,float spacing,const std::string& source_sha256) {
        if(values.ndim()!=2)throw std::invalid_argument("Terrain atlas must be a contiguous float32 array [west,north]");
        baked_world->ground_atlas().upload(values.data(),uint32_t(values.shape(1)),uint32_t(values.shape(0)),north,west,spacing,source_sha256);
    }
    GroundAtlasState ground_atlas_state() {return baked_world->ground_atlas().state();}
    std::vector<float> gpu_ground_heights(const std::vector<std::array<float,2>>& points) {return baked_world->ground_atlas().heights(points);}
    std::vector<GroundVertexState> scenery_ground_vertices(const std::string& id,bool all_vertices=false) {return baked_world->scenery_ground_vertices(id,all_vertices);}
    std::vector<SourceCardMaterialState> source_card_materials() const { return baked_world->source_card_materials(); }
    std::string facing_leaf_state() const { return baked_world->facing_leaf_state().dump(); }
    std::string primitive_id_state() const {
        const auto& scene=wi::scene::GetScene();
        const uint64_t allocated=scene.meshletAllocator.load();
        constexpr uint64_t capacity=(uint64_t(1)<<25)-1;
        return nlohmann::json({{"allocated_meshlets",allocated},{"raster_packed_meshlet_capacity",capacity},
            {"raster_packed_meshlet_overflow",allocated>capacity},{"meshlet_buffer_bytes",scene.meshletBuffer.desc.size},
            {"mesh_shader_allowed",wi::renderer::IsMeshShaderAllowed()},
#ifdef BVR_WIDE_PRIMITIVE_IDS
            {"id_encoding","direct64_indexed"},{"global_meshlet_lookup_enabled",false},
#else
            {"id_encoding","packed32_meshlet25"},{"global_meshlet_lookup_enabled",true},
#endif
            {"scope","Actual scene allocation versus pinned shader PrimitiveID::pack25-bit meshlet field;not a GPU pixel correctness certificate."}}).dump();
    }
    std::optional<std::array<float,4>> reflection_plane() const {
        const auto& visibility=path->visibility_main;
        if(!visibility.planar_reflection_visible)return std::nullopt;
        const auto& p=visibility.reflectionPlane;return std::array<float,4>{p.x,p.y,p.z,p.w};
    }
    std::vector<std::array<double,3>> scenery_points(const std::string& id,const std::vector<std::array<double,3>>& points) const {return baked_world->scenery_points(id,points);}
    double render_height(double n, double w) const { return baked_world->render_height(n, w); }
    double render_surface_height(double n,double w,double reference=INFINITY) const {return baked_world->render_surface_height(n,w,reference);}
    void presentation(bool hangar) {
        if(studio!=hangar&&!visual_profile.is_null()){
            auto sky=wi::scene::GetScene().weathers.GetComponent(weather_entity);
            sky->SetRealisticSky(!hangar&&visual_profile.value("physical_sky",true));
            sky->SetRealisticSkyAerialPerspective(!hangar&&visual_profile.value("aerial_perspective",true));
            sky->SetVolumetricClouds(!hangar&&visual_profile.value("volumetric_clouds",false));
            auto a=visual_profile.at("ambient");sky->ambient=hangar?XMFLOAT3(.12f,.14f,.18f):XMFLOAT3(a[0].get<float>(),a[1].get<float>(),a[2].get<float>());
            sky->horizon={.08f,.1f,.13f};sky->zenith={.025f,.035f,.055f};
        }
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
        in.wheel = wheel_delta;
        wheel_delta = 0;
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
        RECT bounds{};GetClientRect(window,&bounds);
        int client_width=bounds.right-bounds.left,client_height=bounds.bottom-bounds.top;
        if(client_width>0&&client_height>0&&(client_width!=width||client_height!=height)){
            width=client_width;height=client_height;
            wi::graphics::GetDevice()->WaitForGPU();app->SetWindow(window);
            auto& c=*path->camera;c.CreatePerspective(float(width),float(height),.2f,600000.f,c.fov);
        }
        in.width=width;in.height=height;
        in.active = GetForegroundWindow() == window;
        POINT p;
        GetCursorPos(&p);
        ScreenToClient(window, &p);
        in.x = float(p.x);
        in.y = float(p.y);
        using GetPad=DWORD(WINAPI*)(DWORD,XINPUT_STATE*);
        static HMODULE pad_library=LoadLibraryW(L"xinput1_4.dll");
        static GetPad get_pad=pad_library?reinterpret_cast<GetPad>(GetProcAddress(pad_library,"XInputGetState")):nullptr;
        if(get_pad&&in.active)for(DWORD i=0;i<XUSER_MAX_COUNT;++i){
            XINPUT_STATE state{};if(get_pad(i,&state)!=ERROR_SUCCESS)continue;
            const auto& g=state.Gamepad;in.pad_connected=true;
            auto norm=[](SHORT v){return std::clamp(float(v)/32767.f,-1.f,1.f);};
            in.pad_axes={norm(g.sThumbLX),norm(g.sThumbLY),norm(g.sThumbRX),norm(g.sThumbRY),g.bLeftTrigger/255.f,g.bRightTrigger/255.f};break;
        }
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
    void resize(int w,int h){
        if(closed||w<320||h<240)throw std::invalid_argument("Resize requires a live window of at least320x240");
        RECT bounds{0,0,w,h};AdjustWindowRect(&bounds,DWORD(GetWindowLongPtrW(window,GWL_STYLE)),FALSE);
        if(!SetWindowPos(window,nullptr,0,0,bounds.right-bounds.left,bounds.bottom-bounds.top,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE))throw std::runtime_error("Window resize failed");
        poll();
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
                const std::vector<HudLine> &lines,float presentation_dt=1.f/60) {
        if (closed)
            throw std::runtime_error("Renderer closed");
        const auto frame_begin=std::chrono::steady_clock::now();
        auto stamp=frame_begin;
        const auto measure=[&](const char* name){const auto now=std::chrono::steady_clock::now();cpu_timings[name]=std::chrono::duration<double,std::milli>(now-stamp).count();stamp=now;};
        baked_world->update(camera_eye, f);
        measure("scenery_update_ms");
        audio.update(f, studio);
        if (!studio)
            effects->update(f,camera_eye,presentation_dt);
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
            if(preview_root!=wi::ecs::INVALID_ENTITY)break;
            if (studio && e.uid != "player")
                continue;
            if (!e.alive)
                continue;
            live.insert(e.uid);
            Entity root;
            auto it = roots.find(e.uid);
            if (it == roots.end()) {
                if (e.kind == "aircraft") {
                    auto file=model_files.find(e.model);
                    if(file==model_files.end())throw std::runtime_error("Missing aircraft model: "+e.model);
                    root=aircraft_visuals->instantiate(e.uid,file->second);
                    roots[e.uid]=root;
                    if(e.model=="F22"||e.model=="F16")exhaust(root,e.model);
                } else if(e.kind=="vehicle") {
                    root=import_model(e.uid,e.model);
                } else if(e.kind=="sam") {
                    // Authored schematic launcher proxy; it does not claim a surveyed SLAMRAAM mesh.
                    root=s.Entity_CreateTransform(e.uid);s.layers.Create(root).layerMask=1;roots[e.uid]=root;
                    auto add=[&](const std::string& name,XMFLOAT3 position,XMFLOAT3 scale) {
                        auto part=cube(e.uid+name,position,scale,{.17f,.23f,.12f,1});s.Component_Attach(part,root,true);return part;
                    };
                    add("_platform",{0,.65f,0},{1.15f,.65f,2.5f});
                    add("_pedestal",{0,1.6f,0},{.7f,.35f,.65f});
                    for(int row=0;row<2;++row)for(int col=0;col<3;++col)
                        add("_launch_tube",{(col-1)*.42f,2.f+row*.4f,0},{.18f,.18f,1.85f});
                    add("_radar",{.8f,2.8f,-1.6f},{.3f,.45f,.15f});
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
                    // Aircraft NWU pitch is negative nose-up; Wicked +X rotation
                    // pitches a +Z nose downward. Ground contacts use positive slope.
                    XMFLOAT3(float(e.kind=="aircraft" ? e.orientation[1] : -e.orientation[1]), float(-e.orientation[2]), float(-e.orientation[0])));
            t->Translate(studio
                             ? XMFLOAT3(0, 2.1f, 0)
                             : XMFLOAT3(float(-e.position[1]), float(e.position[2]), float(e.position[0])));
            t->UpdateTransform();
            if(e.kind=="aircraft")aircraft_visuals->update(root,e.animation_properties,e.throttle,studio);
            if (weapon_flames.count(root))
                s.objects.GetComponent(weapon_flames[root])->SetRenderable(e.motor_burning);
            for (auto effect : engine_effects[root])
                if (auto material = s.materials.GetComponent(effect)) {
                    float intensity = studio ? 0 : float(visual_profile.is_null()?std::clamp((e.throttle-.35)/.65,0.,1.):std::clamp((e.throttle-.95)/.05,0.,1.));
                    s.objects.GetComponent(effect)->SetRenderable(intensity > .02f);
                    material->SetEmissiveColor({1, .25f, .03f, intensity * (visual_profile.is_null()?4:1.2f)});
                    material->SetBaseColor({1, .3f, .08f, visual_profile.is_null()?1.f:intensity*.45f});
                }
        }
        for (auto it = roots.begin(); it != roots.end();) {
            if (!live.count(it->first)) {
                s.Entity_Remove(it->second);
                aircraft_visuals->remove(it->second);
                engine_effects.erase(it->second);
                weapon_flames.erase(it->second);
                it = roots.erase(it);
            } else
                ++it;
        }
        for (const auto &event : f.events)
            if (visual_profile.is_null()&&(event.kind == "missile_hit" || event.kind == "bomb_impact") && f.tick - event.tick <= 50) {
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
        measure("dynamic_entities_ms");
        baked_world->update_facing_leaves(*path->camera);
        measure("facing_leaves_ms");
        path->texts = texts;
        path->lines = lines;
        // Queue new glyphs before Application::Run updates the atlas. This also
        // makes the first flight/debrief capture complete after a menu change.
        for (const auto &text : texts) {
            wi::font::Params params(text.x, text.y, text.size);
            params.style=path->ui_font;
            wi::font::TextSize(text.text, params);
        }
        // Retain the buffer BEFORE Present advances the swapchain index.
        last_frame = wi::graphics::GetDevice()->GetBackBuffer(&app->swapChain);
        measure("hud_setup_ms");
        app->Run();
        measure("application_run_ms");
        cpu_timings["native_frame_ms"]=std::chrono::duration<double,std::milli>(std::chrono::steady_clock::now()-frame_begin).count();
    }
    void set_profiling(bool enabled) {wi::profiler::SetEnabled(enabled);}
    std::string frame_timings() const {
        auto cpu=cpu_timings;cpu.insert(path->cpu_timings.begin(),path->cpu_timings.end());
        return nlohmann::json({{"native_cpu_ms",cpu},{"descriptors",wi::graphics::GetBvrDescriptorState()},{"engine_cpu_ms",wi::profiler::GetTimingSnapshot(false)},
            {"engine_gpu_ms",wi::profiler::GetTimingSnapshot(true)},
            {"scope","CPU wall times; engine GPU timestamp ranges are buffered and smoothed, nested ranges must not be summed."}}).dump();
    }
    std::string depth_coverage() const {
        const auto& texture=path->sampled_depth();
        if(texture.desc.format!=wi::graphics::Format::R32_FLOAT)throw std::runtime_error("Depth coverage requires R32_FLOAT depth copy");
        wi::vector<uint8_t> bytes;
        if(!wi::helper::saveTextureToMemory(texture,bytes))throw std::runtime_error("Cannot read rendered GPU depth");
        const size_t count=size_t(texture.desc.width)*texture.desc.height;
        if(bytes.size()<count*sizeof(float))throw std::runtime_error("Incomplete rendered depth readback");
        std::array<uint64_t,16*9> occupied{},totals{};uint64_t valid=0,invalid=0;
        for(size_t i=0;i<count;++i){
            float depth;std::memcpy(&depth,bytes.data()+i*sizeof(float),sizeof(float));
            const auto bin=((i/texture.desc.width)*9/texture.desc.height)*16+(i%texture.desc.width)*16/texture.desc.width;
            ++totals[bin];
            if(!std::isfinite(depth)||depth<0||depth>1)++invalid;
            else if(depth>0){++valid;++occupied[bin];}
        }
        std::array<double,16*9> coverage{};for(size_t i=0;i<coverage.size();++i)coverage[i]=double(occupied[i])/std::max<uint64_t>(1,totals[i]);
        return nlohmann::json({{"width",texture.desc.width},{"height",texture.desc.height},{"occupied_fraction",double(valid)/count},
            {"invalid_pixels",invalid},{"tile_columns",16},{"tile_rows",9},{"tile_coverage",coverage},
            {"scope","Actual GPU reversed-Z depth copy; positive samples certify geometry coverage, not material or glyph correctness."}}).dump();
    }
    std::string capture(const std::string &filename) {
        if (closed || !last_frame.IsValid())
            throw std::runtime_error("Render a frame before capture");
        std::filesystem::create_directories(std::filesystem::path(filename).parent_path());
        if (!wi::helper::saveTextureToFile(last_frame, filename))
            throw std::runtime_error("GPU capture failed");
        return filename;
    }
    void capture_menu_background(const std::string& filename){
        wi::helper::saveTextureToFile(*path->GetGUIBlurredBackground(),filename);
        wi::helper::saveTextureToFile(path->GetRenderResult3D(),filename+".scene.png");
    }
    py::bytes capture_rgb() {
        if(closed||!last_frame.IsValid())throw std::runtime_error("Render a frame before capture");
        const auto desc=last_frame.GetDesc();
        using wi::graphics::Format;
        if(desc.format!=Format::R8G8B8A8_UNORM&&desc.format!=Format::R8G8B8A8_UNORM_SRGB&&desc.format!=Format::R10G10B10A2_UNORM)
            throw std::runtime_error("Unsupported video backbuffer pixel format");
        wi::vector<uint8_t> pixels;
        if(!wi::helper::saveTextureToMemory(last_frame,pixels))throw std::runtime_error("GPU video readback failed");
        size_t count=size_t(desc.width)*desc.height;std::string rgb(count*3,'\0');
        for(size_t i=0;i<count;++i){
            if(desc.format==Format::R10G10B10A2_UNORM){
                uint32_t packed;std::memcpy(&packed,pixels.data()+i*4,4);
                for(int c=0;c<3;++c)rgb[i*3+c]=char((((packed>>(c*10))&1023)*255+511)/1023);
            }else for(int c=0;c<3;++c)rgb[i*3+c]=char(pixels[i*4+c]);
        }
        return py::bytes(rgb);
    }
    int shader_errors() const {
        return wi::renderer::GetShaderErrorCount() + wi::renderer::GetShaderMissingCount();
    }
    static void validate_sun_shadows(const std::vector<float>& distances,int resolution){
        if(distances.empty()||distances.size()>4)throw std::invalid_argument("Directional shadows require1..4 cascade distances");
        float previous=0;
        for(float v:distances){if(!std::isfinite(v)||v<=previous||v>50000)throw std::invalid_argument("Shadow cascade distances must increase in(0,50000] metres");previous=v;}
        if(resolution!=-1&&(resolution<128||resolution>8192||(resolution&(resolution-1))!=0||size_t(resolution)*distances.size()>16384))
            throw std::invalid_argument("Sun shadow resolution must be auto(-1) or power-of-two128..8192;cascade atlas width must fit16384");
    }
    void set_shadow_cascades(const std::vector<float>& distances){
        auto light=wi::scene::GetScene().lights.GetComponent(sun_entity);
        if(!light)throw std::runtime_error("Sun is not initialized");
        validate_sun_shadows(distances,light->forced_shadow_resolution);
        light->cascade_distances.assign(distances.begin(),distances.end());
    }
    void set_shadow_resolution(int resolution){
        auto light=wi::scene::GetScene().lights.GetComponent(sun_entity);
        if(!light)throw std::runtime_error("Sun is not initialized");
        validate_sun_shadows(std::vector<float>(light->cascade_distances.begin(),light->cascade_distances.end()),resolution);
        light->forced_shadow_resolution=resolution;
    }
    void apply_environment(const std::string& encoded) {
        const auto profile=nlohmann::json::parse(encoded);
        if(!profile.is_object())throw std::invalid_argument("Baked environment must be an object");
        auto& scene=wi::scene::GetScene();auto weather=scene.weathers.GetComponent(weather_entity);
        if(!weather)throw std::runtime_error("Weather is not initialized");
        auto candidate=*weather;
        auto number=[&](const nlohmann::json& object,const char* key,float fallback,float lo,float hi){
            const float v=object.value(key,fallback);
            if(!std::isfinite(v)||v<lo||v>hi)throw std::invalid_argument(std::string("Invalid environment value: ")+key);
            return v;
        };
        auto color=[&](const char* key,std::vector<float> fallback,float maximum){
            auto v=profile.value(key,fallback);
            if(v.size()!=3)throw std::invalid_argument(std::string("Environment vector requires3 values: ")+key);
            for(float value:v)if(!std::isfinite(value)||value<0||value>maximum)throw std::invalid_argument(std::string("Invalid environment color: ")+key);
            return XMFLOAT3(v[0],v[1],v[2]);
        };
        const auto ambient=color("ambient",{.13f,.14f,.15f},10.f);
        candidate.ambient=studio?XMFLOAT3(.12f,.14f,.18f):ambient;
        candidate.skyExposure=number(profile,"sky_exposure",1.f,.01f,64.f);
        candidate.SetRealisticSky(!studio&&profile.value("physical_sky",true));
        candidate.SetRealisticSkyAerialPerspective(!studio&&profile.value("aerial_perspective",true));
        candidate.SetRealisticSkyHighQuality(profile.value("high_quality_sky",false));
        candidate.SetVolumetricClouds(!studio&&profile.value("volumetric_clouds",false));
        candidate.atmosphereParameters.groundAlbedo=color("planet_albedo",{.12f,.16f,.1f},1.f);
        const auto haze=profile.value("horizon_height_fog",nlohmann::json::object());
        candidate.SetHeightFog(haze.value("enabled",false));
        candidate.fogStart=number(haze,"start_m",100000.f,0.f,1e7f);
        candidate.fogDensity=number(haze,"density_per_m",0.f,0.f,.1f);
        candidate.fogHeightStart=number(haze,"base_m",0.f,-1e6f,1e6f);
        candidate.fogHeightEnd=number(haze,"top_m",16000.f,candidate.fogHeightStart,1e6f);
        candidate.volumetricCloudParameters.init();apply_cloud_profile(candidate,profile);
        auto rotation=profile.value("sun_rotation",std::vector<float>{-.4f,-.65f,0.f});
        if(rotation.size()!=3)throw std::invalid_argument("sun_rotation requires3 values");
        for(float v:rotation)if(!std::isfinite(v))throw std::invalid_argument("Invalid sun rotation");
        const float energy=number(profile,"sun_energy",4.f,0.f,100.f);
        const float exposure=number(profile,"exposure",2.f,.01f,64.f);
        const float saturation=number(profile,"saturation",1.f,0.f,4.f);
        const auto cascades=profile.value("sun_shadow_cascades_m",std::vector<float>{8,80,800});
        if(profile.contains("sun_shadow_resolution")&&!profile.at("sun_shadow_resolution").is_number_integer())throw std::invalid_argument("Sun shadow resolution must be an integer");
        const int shadow_resolution=profile.value("sun_shadow_resolution",-1);
        validate_sun_shadows(cascades,shadow_resolution);
        // Commit only after all validation, preserving material/shader settings.
        *weather=std::move(candidate);
        scene.lights.GetComponent(sun_entity)->intensity=energy;
        scene.lights.GetComponent(sun_entity)->cascade_distances.assign(cascades.begin(),cascades.end());
        scene.lights.GetComponent(sun_entity)->forced_shadow_resolution=shadow_resolution;
        auto transform=scene.transforms.GetComponent(sun_entity);transform->ClearTransform();
        transform->RotateRollPitchYaw(XMFLOAT3(rotation[0],rotation[1],rotation[2]));transform->UpdateTransform();
        path->setExposure(exposure);path->setSaturation(saturation);
        for(const char* key:{"physical_sky","aerial_perspective","high_quality_sky","volumetric_clouds","planet_albedo",
                "sky_exposure","ambient","sun_rotation","sun_energy","exposure","saturation","horizon_height_fog","cloud_layer","cloud_weather_map"}){
            visual_profile.erase(key);if(profile.contains(key))visual_profile[key]=profile.at(key);
        }
    }
    std::string visual_settings() const {
        auto result=visual_profile.is_null()?nlohmann::json::object():visual_profile;
        result["actual_output"]={{"width",width},{"height",height},{"vertical_fov",path->camera->fov},{"temporal_aa",wi::renderer::GetTemporalAAEnabled()},{"fxaa",path->getFXAAEnabled()}};
        auto internal=path->GetInternalResolution();
        result["actual_output"]["internal_resolution"]={internal.x,internal.y};
        result["actual_output"]["render_scale"]=path->resolutionScale;
        result["actual_output"]["visibility_compute_shading"]=path->getVisibilityComputeShadingEnabled();
        result["actual_output"]["occlusion_culling"]=wi::renderer::GetOcclusionCullingEnabled();
        result["actual_output"]["worker_threads"]=wi::jobsystem::GetThreadCount();
        result["actual_output"]["planar_reflections"]=path->planar_reflections_enabled;
        result["actual_output"]["ssr"]=path->getSSREnabled();
        result["actual_output"]["ssgi"]=path->getSSGIEnabled();
        result["actual_output"]["presentation_paused"]=path->presentation_paused;
        result["actual_output"]["presentation_time_s"]=path->frameCB.time;
        result["actual_output"]["render_frame_count"]=path->frameCB.frame_count;
        const auto weather_state=wi::scene::GetScene().weathers.GetComponent(weather_entity);
        result["actual_output"]["height_fog_color_override"]=weather_state->IsOverrideFogColor();
        result["actual_output"]["height_fog_color_linear"]={weather_state->horizon.x,weather_state->horizon.y,weather_state->horizon.z};
        const auto& cloud_map=wi::scene::GetScene().weathers.GetComponent(weather_entity)->volumetricCloudsWeatherMapFirst;
        if(cloud_map.IsValid()){
            const auto& desc=cloud_map.GetTexture().GetDesc();
            result["actual_output"]["cloud_weather_map"]={{"width",desc.width},{"height",desc.height},{"format",uint32_t(desc.format)}};
        }
        const auto light=wi::scene::GetScene().lights.GetComponent(sun_entity);
        if(light){result["actual_output"]["sun_shadow_cascades_m"]=std::vector<float>(light->cascade_distances.begin(),light->cascade_distances.end());result["actual_output"]["sun_cast_shadow"]=light->IsCastingShadow();result["actual_output"]["sun_forced_shadow_resolution"]=light->forced_shadow_resolution;}
        auto colorspace=wi::graphics::GetDevice()->GetSwapChainColorSpace(&app->swapChain);
        result["actual_output"]["color_space"]=colorspace==wi::graphics::ColorSpace::SRGB?"sRGB":colorspace==wi::graphics::ColorSpace::HDR10_ST2084?"HDR10_ST2084":"HDR_LINEAR";
        const auto& sky=wi::scene::GetScene().weather;
        result["actual_environment"]={{"sky_exposure",sky.skyExposure},{"physical_sky",sky.IsRealisticSky()},
            {"aerial_perspective",sky.IsRealisticSkyAerialPerspective()},{"high_quality_sky",sky.IsRealisticSkyHighQuality()},
            {"volumetric_clouds",sky.IsVolumetricClouds()},{"height_fog",sky.IsHeightFog()}};
        const auto& clouds=sky.volumetricCloudParameters;
        result["actual_cloud_layer"]={{"base_height_m",clouds.cloudStartHeight},{"thickness_m",clouds.cloudThickness},
            {"coverage",clouds.layerFirst.coverageAmount},{"type",clouds.layerFirst.typeAmount},
            {"noise_scale_per_m",clouds.layerFirst.totalNoiseScale},{"weather_scale_per_m",clouds.layerFirst.weatherScale},
            {"ray_steps",clouds.maxStepCount},{"step_distribution_m",clouds.inverseDistanceStepCount},
            {"initial_step_scale",clouds.bigStepMarch},{"shadow_samples",clouds.shadowSampleCount},
            {"ground_samples",clouds.groundContributionSampleCount}};
        result["actual_lighting"]={{"sun_direction",{sky.sunDirection.x,sky.sunDirection.y,sky.sunDirection.z}},
            {"sun_radiance",{sky.sunColor.x,sky.sunColor.y,sky.sunColor.z}},
            {"ambient",{sky.ambient.x,sky.ambient.y,sky.ambient.z}},{"exposure",path->getExposure()}};
        return result.dump();
    }
    void set_daylight(float energy,float exposure,float sky_exposure,const std::array<float,3>& ambient){
        for(float v:{energy,exposure,sky_exposure})if(!std::isfinite(v)||v<=0||v>100)throw std::invalid_argument("Invalid daylight intensity/exposure");
        for(float v:ambient)if(!std::isfinite(v)||v<0||v>1)throw std::invalid_argument("Invalid daylight ambient color");
        auto& scene=wi::scene::GetScene();scene.lights.GetComponent(sun_entity)->intensity=energy;
        auto sky=scene.weathers.GetComponent(weather_entity);sky->skyExposure=sky_exposure;sky->ambient={ambient[0],ambient[1],ambient[2]};
        path->setExposure(exposure);
        if(!visual_profile.is_null()){
            visual_profile["sun_energy"]=energy;visual_profile["exposure"]=exposure;
            visual_profile["sky_exposure"]=sky_exposure;visual_profile["ambient"]=ambient;
        }
    }
    size_t effect_count() const {return effects?effects->count():0;}
    void set_clouds(bool enabled){
        if(visual_profile.is_null())throw std::runtime_error("Cloud evaluation requires the visual profile");
        visual_profile["volumetric_clouds"]=enabled;
        wi::scene::GetScene().weathers.GetComponent(weather_entity)->SetVolumetricClouds(enabled&&!studio);
    }
    void set_presentation_paused(bool enabled){
        // Shader weather/wave clock only. The simulator owns its clock.
        path->presentation_paused=enabled;
    }
    void set_render_scale(float value){
        if(!std::isfinite(value)||value<.5f||value>4.f)throw std::invalid_argument("Render scale must be in[0.5,4]");
        if(path->resolutionScale==value)return;
        path->resolutionScale=value;path->ResizeBuffers();
    }
    std::map<std::string,uint64_t> memory_usage() const {
        auto v=wi::graphics::GetDevice()->GetMemoryUsage();return {{"usage_bytes",v.usage},{"budget_bytes",v.budget}};
    }
    std::array<float,3> entity_forward(const std::string& uid) const {
        auto it=roots.find(uid);
        if(it==roots.end())throw std::invalid_argument("Rendered entity not found: "+uid);
        auto transform=wi::scene::GetScene().transforms.GetComponent(it->second);
        auto forward=transform->GetForward();return {forward.x,forward.y,forward.z};
    }
    std::array<std::array<float,3>,3> entity_basis(const std::string& uid) const {
        auto it=roots.find(uid);if(it==roots.end())throw std::runtime_error("Entity has not been rendered: "+uid);
        auto transform=wi::scene::GetScene().transforms.GetComponent(it->second);
        auto right=transform->GetRight(),up=transform->GetUp(),forward=transform->GetForward();
        return {{{right.x,right.y,right.z},{up.x,up.y,up.z},{forward.x,forward.y,forward.z}}};
    }
    void preview_aircraft(const std::string& model,const std::map<std::string,double>& properties,double throttle){
        reload();
        auto file=model_files.find(model);
        if(file==model_files.end())throw std::runtime_error("Missing review aircraft: "+model);
        auto& s=wi::scene::GetScene();preview_root=aircraft_visuals->instantiate("asset_review",file->second);
        s.layers.GetComponent(preview_root)->layerMask=2;
        // Asset review can contain 80-m airliners: hide finite hangar walls.
        // Keep the presentation apron for imported aircraft too.
        float lift=.02f;
        std::ifstream manifest(std::filesystem::path(file->second).parent_path()/"manifest.json");
        if(manifest){nlohmann::json m;manifest>>m;lift+=std::max(0.f,-m.at("bounds_blender").at("min").at(2).get<float>());}
        s.transforms.GetComponent(preview_root)->Translate(XMFLOAT3(0,lift,0));
        aircraft_visuals->update(preview_root,properties,throttle,false);
    }
    std::map<std::string,uint64_t> aircraft_statistics() const { return aircraft_visuals->stats(); }
    std::vector<AircraftExhaustState> aircraft_exhaust_state() const { return aircraft_visuals->exhaust_state(); }
    std::map<std::string,uint64_t> aircraft_import_counts() const { return aircraft_visuals->imports(); }
    void reload() {
        auto &s = wi::scene::GetScene();
        if(preview_root!=wi::ecs::INVALID_ENTITY){
            s.Entity_Remove(preview_root);preview_root=wi::ecs::INVALID_ENTITY;
            for(auto e:studio_entities)if(auto o=s.objects.GetComponent(e))o->SetRenderable(true);
        }
        for (auto [_, e] : roots)
            s.Entity_Remove(e);
        roots.clear();
        if(aircraft_visuals)aircraft_visuals->clear();
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
#ifdef BVR_FAR_DISTANCE
    m.attr("TERRAIN_CONTINUATION_V1")=true;
    m.def("draw_distance_round_trip",&wi::renderer::BvrDrawDistanceRoundTrip);
#else
    m.attr("TERRAIN_CONTINUATION_V1")=false;
#endif
    m.attr("VISUAL_BETA")=true;
    m.attr("BAKED_ENVIRONMENT")=true;
    m.attr("SUN_SHADOW_PROFILE_V1")=true;
    m.attr("SURFACE_DETAIL_UVS_V1")=true;
    m.attr("CACHED_TREE_HEIGHTS_V1")=true;
    m.attr("WIDE_VISIBILITY_COMPUTE_V1")=true;
    m.attr("STATIC_VEGETATION_WORLD_TRANSFORMS_V1")=true;
    m.attr("ROOTLESS_SPATIAL_VEGETATION_V1")=true;
#if defined(BVR_STATIC_SCENERY_CACHE) && !defined(BVR_INLINE_GROUND_BOUNDS)
    m.attr("STATIC_SCENERY_CACHE_V1")=true;
#else
    m.attr("STATIC_SCENERY_CACHE_V1")=false;
#endif
#ifdef BVR_INLINE_GROUND_BOUNDS
    m.attr("INLINE_GROUND_BOUNDS_V1")=true;
#else
    m.attr("INLINE_GROUND_BOUNDS_V1")=false;
#endif
#ifdef BVR_SCENE_MATERIAL_CACHE
    m.attr("SCENE_MATERIAL_CACHE_V1")=true;
#else
    m.attr("SCENE_MATERIAL_CACHE_V1")=false;
#endif
#ifdef BVR_WIDE_PRIMITIVE_IDS
    m.attr("WIDE_PRIMITIVE_ID_RASTER")=true;
#else
    m.attr("WIDE_PRIMITIVE_ID_RASTER")=false;
#endif
    m.attr("GAME_API_ABI")=2;
    m.attr("CLOUD_LAYER_SAMPLING")=true;
    m.attr("TERRAIN_TILE_MATERIALS")=true;
    m.attr("SOURCE_CARD_AREA_MIPS")=true;
    m.attr("SOURCE_FACING_LEAVES_CPU_V1")=true;
    m.attr("BAKED_CLOUD_WEATHER_MAP")=true;
    m.attr("FOG_COLOR_PROFILE_V1")=true;
    m.attr("TERRAIN_BASE_MATERIAL")=true;
    py::class_<ScenePlacement>(m, "ScenePlacement")
        .def(py::init<>())
        .def_readwrite("id", &ScenePlacement::id)
        .def_readwrite("model", &ScenePlacement::model)
        .def_readwrite("chunk", &ScenePlacement::chunk)
        .def_readwrite("category", &ScenePlacement::category)
        .def_readwrite("target_uid", &ScenePlacement::target_uid)
        .def_readwrite("position", &ScenePlacement::position)
        .def_readwrite("up_normal", &ScenePlacement::up_normal)
        .def_readwrite("ground_stems", &ScenePlacement::ground_stems)
        .def_readwrite("yaw", &ScenePlacement::yaw)
        .def_readwrite("scale", &ScenePlacement::scale)
        .def_readwrite("lod_distance", &ScenePlacement::lod_distance)
        .def_readwrite("cull_distance", &ScenePlacement::cull_distance);
    py::class_<SceneMaterial>(m, "SceneMaterial")
        .def(py::init<>())
        .def_readwrite("id", &SceneMaterial::id)
        .def_readwrite("base_color", &SceneMaterial::base_color)
        .def_readwrite("normal", &SceneMaterial::normal)
        .def_readwrite("roughness_map", &SceneMaterial::roughness_map)
        .def_readwrite("detail_color", &SceneMaterial::detail_color)
        .def_readwrite("detail_normal", &SceneMaterial::detail_normal)
        .def_readwrite("detail_roughness", &SceneMaterial::detail_roughness)
        .def_readwrite("detail_tile_m", &SceneMaterial::detail_tile_m)
        .def_readwrite("detail_mean_linear", &SceneMaterial::detail_mean_linear)
        .def_readwrite("detail_strength", &SceneMaterial::detail_strength)
        .def_readwrite("color", &SceneMaterial::color)
        .def_readwrite("tile_m", &SceneMaterial::tile_m)
        .def_readwrite("world_uv", &SceneMaterial::world_uv)
        .def_readwrite("uv_origin_north", &SceneMaterial::uv_origin_north)
        .def_readwrite("uv_origin_west", &SceneMaterial::uv_origin_west)
        .def_readwrite("roughness", &SceneMaterial::roughness)
        .def_readwrite("water", &SceneMaterial::water);
    py::class_<SceneSurface>(m, "SceneSurface")
        .def(py::init<>())
        .def_readwrite("id", &SceneSurface::id)
        .def_readwrite("material", &SceneSurface::material)
        .def_readwrite("vertices", &SceneSurface::vertices)
        .def_readwrite("indices", &SceneSurface::indices)
        .def_readwrite("drivable", &SceneSurface::drivable);
    py::class_<SceneStats>(m, "SceneStats")
        .def_readonly("unique_models", &SceneStats::unique_models)
        .def_readonly("imported_glbs", &SceneStats::imported_glbs)
        .def_readonly("mesh_resources", &SceneStats::mesh_resources)
        .def_readonly("material_resources", &SceneStats::material_resources)
        .def_readonly("transform_components", &SceneStats::transform_components)
        .def_readonly("lod_candidates", &SceneStats::lod_candidates)
        .def_readonly("instances", &SceneStats::instances)
        .def_readonly("visible_instances", &SceneStats::visible_instances)
        .def_readonly("visible_objects", &SceneStats::visible_objects)
        .def_readonly("visible_triangles", &SceneStats::visible_triangles)
        .def_readonly("visible_mesh_subset_groups", &SceneStats::visible_mesh_subset_groups)
        .def_readonly("import_counts", &SceneStats::import_counts)
        .def_readonly("chunk_instances", &SceneStats::chunk_instances)
        .def_readonly("visible_lods", &SceneStats::visible_lods)
        .def_readonly("visible_chunks", &SceneStats::visible_chunks);
    py::class_<SourceCardMaterialState>(m,"SourceCardMaterialState")
        .def_readonly("albedo_resource",&SourceCardMaterialState::albedo_resource).def_readonly("albedo_format",&SourceCardMaterialState::albedo_format)
        .def_readonly("albedo_mip_levels",&SourceCardMaterialState::albedo_mip_levels).def_readonly("explicit_mips",&SourceCardMaterialState::explicit_mips)
        .def_readonly("name",&SourceCardMaterialState::name).def_readonly("normal_resource",&SourceCardMaterialState::normal_resource)
        .def_readonly("normal_format",&SourceCardMaterialState::normal_format).def_readonly("width",&SourceCardMaterialState::width)
        .def_readonly("height",&SourceCardMaterialState::height).def_readonly("mip_levels",&SourceCardMaterialState::mip_levels)
        .def_readonly("rgb_preserved",&SourceCardMaterialState::rgb_preserved);
    py::class_<GroundAtlasState>(m,"GroundAtlasState")
        .def_readonly("columns",&GroundAtlasState::columns).def_readonly("rows",&GroundAtlasState::rows)
        .def_readonly("origin_north",&GroundAtlasState::origin_north).def_readonly("origin_west",&GroundAtlasState::origin_west)
        .def_readonly("spacing",&GroundAtlasState::spacing).def_readonly("bytes",&GroundAtlasState::bytes)
        .def_readonly("tree_positions_count",&GroundAtlasState::tree_positions_count).def_readonly("tree_positions_bytes",&GroundAtlasState::tree_positions_bytes)
        .def_readonly("source_sha256",&GroundAtlasState::source_sha256);
    py::class_<GroundVertexState>(m,"GroundVertexState")
        .def_readonly("source_tree_active",&GroundVertexState::source_tree_active)
        .def_readonly("subset",&GroundVertexState::subset).def_readonly("vertex_index",&GroundVertexState::vertex_index)
        .def_readonly("uv_anchor",&GroundVertexState::uv_anchor).def_readonly("world_position",&GroundVertexState::world_position)
        .def_readonly("world_base",&GroundVertexState::world_base).def_readonly("bounds_min",&GroundVertexState::bounds_min)
        .def_readonly("surface_position",&GroundVertexState::surface_position).def_readonly("previous_position",&GroundVertexState::previous_position)
        .def_readonly("gpu_instance_sphere",&GroundVertexState::gpu_instance_sphere)
        .def_readonly("bounds_max",&GroundVertexState::bounds_max);
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
    py::class_<HudImage>(m,"HudImage").def(py::init<>())
        .def_readwrite("x",&HudImage::x).def_readwrite("y",&HudImage::y)
        .def_readwrite("w",&HudImage::w).def_readwrite("h",&HudImage::h)
        .def_readwrite("file",&HudImage::file);
    py::class_<Input>(m, "Input")
        .def_readonly("x", &Input::x)
        .def_readonly("y", &Input::y)
        .def_readonly("wheel", &Input::wheel)
        .def_readonly("active", &Input::active)
        .def_readonly("width", &Input::width).def_readonly("height", &Input::height)
        .def_readonly("pad_connected", &Input::pad_connected).def_readonly("pad_axes", &Input::pad_axes)
        .def_readonly("quit", &Input::quit)
        .def_readonly("held", &Input::held)
        .def_readonly("pressed", &Input::pressed);
    py::class_<AircraftExhaustState>(m,"AircraftExhaustState")
        .def_readonly("uid",&AircraftExhaustState::uid).def_readonly("engine_index",&AircraftExhaustState::engine_index)
        .def_readonly("mode",&AircraftExhaustState::mode).def_readonly("property",&AircraftExhaustState::property)
        .def_readonly("reason",&AircraftExhaustState::reason).def_readonly("attachment_association",&AircraftExhaustState::attachment_association)
        .def_readonly("property_available",&AircraftExhaustState::property_available)
        .def_readonly("visible",&AircraftExhaustState::visible).def_readonly("intensity",&AircraftExhaustState::intensity);
    py::class_<Renderer>(m, "Renderer")
        .def(py::init<int, int, bool, const std::string &, const std::string &,
                      const std::map<std::string, std::string> &,const std::string&>(),py::arg("width"),py::arg("height"),py::arg("visible"),py::arg("engine"),py::arg("shaders"),py::arg("models"),py::arg("visual_profile")="")
        .def("render", &Renderer::render,py::arg("frame"),py::arg("texts"),py::arg("lines"),py::arg("presentation_dt")=1.f/60)
        .def("set_profiling", &Renderer::set_profiling)
        .def("frame_timings", &Renderer::frame_timings)
        .def("set_visibility_compute", &Renderer::set_visibility_compute)
        .def("set_occlusion_culling", &Renderer::set_occlusion_culling)
        .def("set_planar_reflections", &Renderer::set_planar_reflections)
        .def("depth_coverage", &Renderer::depth_coverage)
        .def("poll", &Renderer::poll)
        .def("camera", &Renderer::camera)
        .def("camera_up", &Renderer::camera_up)
        .def("project", &Renderer::project)
        .def("capture", &Renderer::capture)
        .def("capture_menu_background", &Renderer::capture_menu_background)
        .def("capture_rgb", &Renderer::capture_rgb)
        .def("set_shadow_cascades", &Renderer::set_shadow_cascades)
        .def("set_shadow_resolution", &Renderer::set_shadow_resolution)
        .def("apply_environment", &Renderer::apply_environment)
        .def("set_presentation_paused", &Renderer::set_presentation_paused)
        .def("set_render_scale", &Renderer::set_render_scale)
        .def("reload", &Renderer::reload)
        .def("set_quality", &Renderer::set_quality)
        .def("set_ui_font", &Renderer::set_ui_font)
        .def("set_menu_overlay", &Renderer::set_menu_overlay)
        .def("set_audio_volume", &Renderer::set_audio_volume)
        .def("set_hangar_floor_texture", &Renderer::set_hangar_floor_texture)
        .def("shader_errors", &Renderer::shader_errors)
        .def("visual_settings", &Renderer::visual_settings)
        .def("set_daylight", &Renderer::set_daylight,py::arg("sun_energy"),py::arg("exposure"),py::arg("sky_exposure"),py::arg("ambient"))
        .def("effect_count", &Renderer::effect_count)
        .def("set_clouds", &Renderer::set_clouds)
        .def("memory_usage", &Renderer::memory_usage)
        .def("entity_forward", &Renderer::entity_forward)
        .def("entity_basis", &Renderer::entity_basis)
        .def("scenery_points", &Renderer::scenery_points)
        .def("configure_world", &Renderer::configure_world)
        .def("register_scene_models", &Renderer::register_scene_models)
        .def("configure_scene", &Renderer::configure_scene, py::arg("terrain"), py::arg("cover"),
             py::arg("colors"), py::arg("materials"), py::arg("surfaces"), py::arg("placements"),
             py::arg("outer_cover"), py::arg("outer_colors"),
             py::arg("terrain_materials")=std::vector<std::string>{})
        .def("statistics", &Renderer::statistics)
        .def("set_vegetation_lod_distance", &Renderer::set_vegetation_lod_distance)
        .def("vegetation_state", &Renderer::vegetation_state)
        .def("set_spatial_vegetation_lod", &Renderer::set_spatial_vegetation_lod)
        .def("vegetation_lod_bytes", &Renderer::vegetation_lod_bytes)
        .def("set_static_cache_enabled", &Renderer::set_static_cache_enabled)
        .def("static_cache_state", &Renderer::static_cache_state)
        .def("set_inline_ground_bounds", &Renderer::set_inline_ground_bounds)
        .def("source_card_materials", &Renderer::source_card_materials)
        .def("facing_leaf_state", &Renderer::facing_leaf_state)
        .def("configure_ground_atlas", &Renderer::configure_ground_atlas,py::arg("values").noconvert(),py::arg("origin_north"),py::arg("origin_west"),py::arg("spacing"),py::arg("source_sha256"))
        .def("ground_atlas_state", &Renderer::ground_atlas_state)
        .def("gpu_ground_heights", &Renderer::gpu_ground_heights)
        .def("scenery_ground_vertices", &Renderer::scenery_ground_vertices,py::arg("id"),py::arg("all_vertices")=false)
        .def("reflection_plane", &Renderer::reflection_plane)
        .def("primitive_id_state", &Renderer::primitive_id_state)
        .def("preview_aircraft", &Renderer::preview_aircraft)
        .def("aircraft_statistics", &Renderer::aircraft_statistics)
        .def("aircraft_exhaust_state", &Renderer::aircraft_exhaust_state)
        .def("aircraft_import_counts", &Renderer::aircraft_import_counts)
        .def("render_height", &Renderer::render_height)
        .def("render_surface_height",&Renderer::render_surface_height,py::arg("north"),py::arg("west"),py::arg("reference_height")=INFINITY)
        .def("presentation", &Renderer::presentation)
        .def("configure_audio", &Renderer::configure_audio)
        .def("audio_counts", &Renderer::audio_counts)
        .def("audio_available", &Renderer::audio_available)
        .def("place_asset", &Renderer::place_asset)
        .def("resize",&Renderer::resize)
        .def("close", &Renderer::close);
}
