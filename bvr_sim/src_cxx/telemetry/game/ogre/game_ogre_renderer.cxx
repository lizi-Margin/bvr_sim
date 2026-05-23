#include "../dx11/game_dx11_internal.hxx"

#ifdef BVR_SIM_ENABLE_OGRE_NEXT

#include "Ogre.h"
#include "OgreAbiUtils.h"
#include "OgreArchiveManager.h"
#include "OgreCamera.h"
#include "OgreHlmsManager.h"
#include "OgreHlmsPbs.h"
#include "OgreHlmsUnlit.h"
#include "OgreManualObject2.h"
#include "OgreRoot.h"
#include "OgreSceneManager.h"
#include "OgreSceneNode.h"
#include "OgreWindow.h"
#include "Compositor/OgreCompositorManager2.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <sstream>
#include <string>
#include <unordered_map>

namespace bvr_sim {

#ifdef _WIN32

namespace {

#ifndef BVR_SIM_OGRE_PLUGIN_DIR
#define BVR_SIM_OGRE_PLUGIN_DIR ""
#endif

#ifndef BVR_SIM_OGRE_MEDIA_DIR
#define BVR_SIM_OGRE_MEDIA_DIR ""
#endif

std::string normalize_path(std::string path) {
    std::replace(path.begin(), path.end(), '\\', '/');
    if (!path.empty() && path.back() != '/') {
        path.push_back('/');
    }
    return path;
}

Ogre::Vector3 to_ogre_position(const Float3& value) {
    return Ogre::Vector3(value.x, value.y, value.z);
}

Ogre::Vector3 transform_position(const Float4x4& m, const DX11Vertex& vertex) {
    const float x = vertex.position[0];
    const float y = vertex.position[1];
    const float z = vertex.position[2];
    return Ogre::Vector3(
        x * m.m[0][0] + y * m.m[1][0] + z * m.m[2][0] + m.m[3][0],
        x * m.m[0][1] + y * m.m[1][1] + z * m.m[2][1] + m.m[3][1],
        x * m.m[0][2] + y * m.m[1][2] + z * m.m[2][2] + m.m[3][2]);
}

Ogre::ColourValue to_colour(const DX11Vertex& vertex) {
    return Ogre::ColourValue(vertex.color[0], vertex.color[1], vertex.color[2], 1.0f);
}

void append_vertices(Ogre::ManualObject* manual,
                     const std::vector<DX11Vertex>& vertices,
                     const Float4x4& world,
                     uint32_t& next_index) {
    for (const DX11Vertex& vertex : vertices) {
        manual->position(transform_position(world, vertex));
        manual->normal(vertex.normal[0], vertex.normal[1], vertex.normal[2]);
        manual->tangent(1.0f, 0.0f, 0.0f);
        manual->textureCoord(vertex.uv[0], vertex.uv[1]);
        manual->colour(to_colour(vertex));
        manual->index(next_index++);
    }
}

void register_hlms_from_media(Ogre::Root& root, const std::string& media_dir) {
    Ogre::ArchiveManager& archive_manager = Ogre::ArchiveManager::getSingleton();
    const Ogre::String archive_type = "FileSystem";
    const Ogre::String root_hlms_folder = normalize_path(media_dir);

    Ogre::String main_folder;
    Ogre::StringVector library_folders;

    Ogre::HlmsUnlit::getDefaultPaths(main_folder, library_folders);
    Ogre::Archive* archive_unlit = archive_manager.load(root_hlms_folder + main_folder, archive_type, true);
    Ogre::ArchiveVec unlit_libraries;
    for (const Ogre::String& folder : library_folders) {
        unlit_libraries.push_back(archive_manager.load(root_hlms_folder + folder, archive_type, true));
    }
    root.getHlmsManager()->registerHlms(OGRE_NEW Ogre::HlmsUnlit(archive_unlit, &unlit_libraries));

    Ogre::HlmsPbs::getDefaultPaths(main_folder, library_folders);
    Ogre::Archive* archive_pbs = archive_manager.load(root_hlms_folder + main_folder, archive_type, true);
    Ogre::ArchiveVec pbs_libraries;
    for (const Ogre::String& folder : library_folders) {
        pbs_libraries.push_back(archive_manager.load(root_hlms_folder + folder, archive_type, true));
    }
    root.getHlmsManager()->registerHlms(OGRE_NEW Ogre::HlmsPbs(archive_pbs, &pbs_libraries));
}

} // namespace

class OgreRenderer final : public IRenderer {
public:
    OgreRenderer() = default;
    ~OgreRenderer() override { destroy(); }

    bool initialize(std::string& error) override {
        if (!create_window(window_, error)) {
            return false;
        }

        const std::string plugin_dir = normalize_path(BVR_SIM_OGRE_PLUGIN_DIR);
        const std::string media_dir = normalize_path(BVR_SIM_OGRE_MEDIA_DIR);
        if (plugin_dir.empty() || media_dir.empty()) {
            error = "OGRE backend requires BVR_SIM_OGRE_PLUGIN_DIR and BVR_SIM_OGRE_MEDIA_DIR";
            destroy_window(window_);
            return false;
        }

        SetDllDirectoryA(plugin_dir.c_str());

        try {
            const Ogre::AbiCookie abi_cookie = Ogre::generateAbiCookie();
            root_ = OGRE_NEW Ogre::Root(&abi_cookie, "", "", "bvr_sim_ogre.log", "BVR Sim");
            root_->loadPlugin(plugin_dir + "RenderSystem_Direct3D11", false, nullptr);

            Ogre::RenderSystem* render_system = root_->getRenderSystemByName("Direct3D11 Rendering Subsystem");
            if (!render_system) {
                error = "OGRE Direct3D11 RenderSystem is not available";
                destroy();
                return false;
            }

            render_system->setConfigOption("Full Screen", "No");
            render_system->setConfigOption("VSync", "Yes");
            render_system->setConfigOption("sRGB Gamma Conversion", "Yes");
            root_->setRenderSystem(render_system);
            root_->initialise(false);

            RECT rect = {};
            GetClientRect(window_.hwnd, &rect);
            const int width = std::max(1L, rect.right - rect.left);
            const int height = std::max(1L, rect.bottom - rect.top);

            Ogre::NameValuePairList params;
            params["externalWindowHandle"] = std::to_string(reinterpret_cast<std::uintptr_t>(window_.hwnd));
            render_window_ = root_->createRenderWindow("BVR Sim Game Mode (OGRE)",
                                                       static_cast<uint32_t>(width),
                                                       static_cast<uint32_t>(height),
                                                       false,
                                                       &params);

            register_hlms_from_media(*root_, media_dir);
            Ogre::Hlms* unlit = root_->getHlmsManager()->getHlms(Ogre::HLMS_UNLIT);
            if (unlit && !unlit->getDatablock("bvr_ogre_unlit")) {
                unlit->createDatablock("bvr_ogre_unlit",
                                       "bvr_ogre_unlit",
                                       Ogre::HlmsMacroblock(),
                                       Ogre::HlmsBlendblock(),
                                       Ogre::HlmsParamVec());
            }

            scene_manager_ = root_->createSceneManager(Ogre::ST_GENERIC, 1, "BvrSimOgreScene");
            camera_ = scene_manager_->createCamera("BvrSimOgreCamera");
            camera_->setNearClipDistance(0.2f);
            camera_->setFarClipDistance(2000000.0f);
            camera_->setAutoAspectRatio(true);

            Ogre::CompositorManager2* compositor = root_->getCompositorManager2();
            const Ogre::String workspace_name("BVR Sim OGRE Workspace");
            if (!compositor->hasWorkspaceDefinition(workspace_name)) {
                compositor->createBasicWorkspaceDef(workspace_name, Ogre::ColourValue(0.55f, 0.68f, 0.82f), Ogre::IdString());
            }
            workspace_ = compositor->addWorkspace(scene_manager_, render_window_->getTexture(), camera_, workspace_name, true);

            manual_ = scene_manager_->createManualObject(Ogre::SCENE_DYNAMIC);
            manual_node_ = scene_manager_->getRootSceneNode(Ogre::SCENE_DYNAMIC)->createChildSceneNode(Ogre::SCENE_DYNAMIC);
            manual_node_->attachObject(manual_);

            initialized_ = true;
            return true;
        } catch (const Ogre::Exception& exc) {
            error = std::string("OGRE initialize failed: ") + exc.getFullDescription();
            destroy();
            return false;
        } catch (const std::exception& exc) {
            error = std::string("OGRE initialize failed: ") + exc.what();
            destroy();
            return false;
        }
    }

    void destroy() override {
        if (root_) {
            try {
                if (scene_manager_) {
                    if (manual_node_) {
                        manual_node_->detachAllObjects();
                        scene_manager_->destroySceneNode(manual_node_);
                        manual_node_ = nullptr;
                    }
                    if (manual_) {
                        scene_manager_->destroyManualObject(manual_);
                        manual_ = nullptr;
                    }
                }
                if (workspace_) {
                    root_->getCompositorManager2()->removeWorkspace(workspace_);
                    workspace_ = nullptr;
                }
                if (scene_manager_) {
                    root_->destroySceneManager(scene_manager_);
                    scene_manager_ = nullptr;
                }
                render_window_ = nullptr;
                OGRE_DELETE root_;
                root_ = nullptr;
            } catch (...) {
                root_ = nullptr;
            }
        }
        destroy_window(window_);
        initialized_ = false;
    }

    bool process_messages() override {
        MSG msg = {};
        while (PeekMessage(&msg, nullptr, 0, 0, PM_REMOVE)) {
            if (msg.message == WM_QUIT) {
                window_closed_ = true;
                return false;
            }
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }
        return true;
    }

    void apply_camera_state(const RendererCameraState& state) override {
        window_.input.input_mode = state.input_mode == "control"
            ? ViewerInputState::InputMode::Control
            : ViewerInputState::InputMode::Follow;
        window_.input.camera_mode = state.camera_mode == "follow"
            ? ViewerInputState::CameraMode::FollowObject
            : ViewerInputState::CameraMode::Free;
        window_.input.focus_uid = state.target_uid;
        window_.input.focus_cycle_index = state.focus_index;
        window_.input.camera_distance = static_cast<float>(state.distance);
        window_.input.camera_yaw = static_cast<float>(state.yaw);
        window_.input.camera_pitch = static_cast<float>(state.pitch);
        window_.input.camera_fov_y = static_cast<float>(state.fov_y);
        window_.input.camera_roll_locked = state.roll_locked;
        window_.input.mouse_aim_enabled = state.mouse_aim_enabled;
        if (state.has_target) {
            window_.input.camera_target = Float3{
                static_cast<float>(state.target[0]),
                static_cast<float>(state.target[1]),
                static_cast<float>(state.target[2])};
        }
    }

    RendererCameraState get_camera_state() const override {
        RendererCameraState state;
        state.input_mode = window_.input.input_mode == ViewerInputState::InputMode::Control ? "control" : "follow";
        state.camera_mode = window_.input.camera_mode == ViewerInputState::CameraMode::FollowObject ? "follow" : "free";
        state.target_uid = window_.input.focus_uid;
        state.focus_index = window_.input.focus_cycle_index;
        state.distance = window_.input.camera_distance;
        state.yaw = window_.input.camera_yaw;
        state.pitch = window_.input.camera_pitch;
        state.fov_y = window_.input.camera_fov_y;
        state.roll_locked = window_.input.camera_roll_locked;
        state.mouse_aim_enabled = window_.input.mouse_aim_enabled;
        state.has_target = true;
        state.target[0] = window_.input.camera_target.x;
        state.target[1] = window_.input.camera_target.y;
        state.target[2] = window_.input.camera_target.z;
        return state;
    }

    void update_input(const WorldSnapshot* snapshot, float dt_seconds) override {
        update_camera(window_.input, dt_seconds);

        window_.input.snapshot_uids.clear();
        if (snapshot) {
            for (const auto& object : snapshot->objects) {
                if (object.alive) {
                    window_.input.snapshot_uids.push_back(object.uid);
                }
            }
        }

        const int object_count = static_cast<int>(window_.input.snapshot_uids.size());
        if (object_count <= 0) {
            window_.input.focus_uid.clear();
            window_.input.focus_cycle_index = -1;
            window_.input.camera_mode = ViewerInputState::CameraMode::Free;
            window_.input.focus_cycle_requested = false;
            return;
        }

        if (window_.input.focus_cycle_requested) {
            const int slot_count = object_count + 1;
            int next_index = window_.input.focus_cycle_index + 1;
            if (next_index >= slot_count) {
                next_index = -1;
            }
            window_.input.focus_cycle_index = next_index;
            window_.input.focus_uid.clear();
            window_.input.focus_cycle_requested = false;
        }

        if (window_.input.focus_cycle_index >= 0 && window_.input.focus_cycle_index < object_count) {
            window_.input.focus_uid = window_.input.snapshot_uids[static_cast<size_t>(window_.input.focus_cycle_index)];
            window_.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
        } else if (window_.input.input_mode == ViewerInputState::InputMode::Follow
            && window_.input.camera_mode == ViewerInputState::CameraMode::FollowObject) {
            window_.input.focus_cycle_index = 0;
            window_.input.focus_uid = window_.input.snapshot_uids.front();
        }
    }

    bool render_frame(const RendererFrameInput& input, RendererFrameStats& out_stats) override {
        try {
            return render_frame_impl(input, out_stats);
        } catch (const Ogre::Exception& exc) {
            std::fprintf(stderr, "OGRE render frame failed: %s\n", exc.getFullDescription().c_str());
            return false;
        } catch (const std::exception& exc) {
            std::fprintf(stderr, "OGRE render frame failed: %s\n", exc.what());
            return false;
        }
    }

    bool render_frame_impl(const RendererFrameInput& input, RendererFrameStats& out_stats) {
        if (!initialized_ || !root_ || !manual_ || !camera_) {
            return false;
        }

        RECT rect = {};
        GetClientRect(window_.hwnd, &rect);
        const UINT width = static_cast<UINT>(std::max(1L, rect.right - rect.left));
        const UINT height = static_cast<UINT>(std::max(1L, rect.bottom - rect.top));
        window_.input.client_width = static_cast<int>(width);
        window_.input.client_height = static_cast<int>(height);

        const RenderScene scene = build_render_scene(window_.input, width, height, input.snapshot);
        camera_->setPosition(to_ogre_position(scene.camera_position));
        camera_->lookAt(to_ogre_position(Float3{
            scene.camera_position.x + scene.camera_forward.x * 10000.0f,
            scene.camera_position.y + scene.camera_forward.y * 10000.0f,
            scene.camera_position.z + scene.camera_forward.z * 10000.0f}));
        camera_->setFOVy(Ogre::Radian(static_cast<Ogre::Real>(window_.input.camera_fov_y * 3.14159265358979323846 / 180.0)));

        manual_->clear();
        manual_->begin("bvr_ogre_unlit", Ogre::OT_TRIANGLE_LIST);

        long vertex_count = 0;
        uint32_t next_index = 0;
        append_vertices(manual_, scene.ground_vertices, Float4x4::identity(), next_index);
        vertex_count += static_cast<long>(scene.ground_vertices.size());
        for (const auto& batch : scene.object_batches) {
            append_vertices(manual_, batch.vertices, batch.world, next_index);
            vertex_count += static_cast<long>(batch.vertices.size());
        }

        if (vertex_count == 0) {
            DX11Vertex a{{-100.0f, 0.0f, -100.0f}, {0.2f, 0.4f, 0.2f}, {0.0f, 1.0f, 0.0f}, {0.0f, 0.0f}};
            DX11Vertex b{{100.0f, 0.0f, -100.0f}, {0.2f, 0.4f, 0.2f}, {0.0f, 1.0f, 0.0f}, {1.0f, 0.0f}};
            DX11Vertex c{{0.0f, 0.0f, 100.0f}, {0.2f, 0.4f, 0.2f}, {0.0f, 1.0f, 0.0f}, {0.5f, 1.0f}};
            std::vector<DX11Vertex> fallback{a, b, c};
            append_vertices(manual_, fallback, Float4x4::identity(), next_index);
            vertex_count = 3;
        }

        manual_->end();

        out_stats.command_count = 1;
        out_stats.draw_calls = 1;
        out_stats.vertex_count = vertex_count;

        return root_->renderOneFrame();
    }

    bool is_window_closed() const override { return window_closed_; }
    bool get_shadows_enabled() const override { return false; }
    bool get_material_system_enabled() const override { return true; }
    void set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) override {
        command_submitter_ = std::move(submitter);
    }

private:
    Win32Window window_;
    bool initialized_ = false;
    bool window_closed_ = false;
    Ogre::Root* root_ = nullptr;
    Ogre::Window* render_window_ = nullptr;
    Ogre::SceneManager* scene_manager_ = nullptr;
    Ogre::Camera* camera_ = nullptr;
    Ogre::CompositorWorkspace* workspace_ = nullptr;
    Ogre::ManualObject* manual_ = nullptr;
    Ogre::SceneNode* manual_node_ = nullptr;
    std::function<void(const TelemetryCommand&)> command_submitter_;
};

#endif // _WIN32

std::unique_ptr<IRenderer> create_ogre_renderer() {
#ifdef _WIN32
    return std::make_unique<OgreRenderer>();
#else
    return nullptr;
#endif
}

} // namespace bvr_sim

#else

namespace bvr_sim {

std::unique_ptr<IRenderer> create_ogre_renderer() {
    return nullptr;
}

} // namespace bvr_sim

#endif // BVR_SIM_ENABLE_OGRE_NEXT
