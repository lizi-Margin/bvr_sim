#include "game_dx11_internal.hxx"
#include "resource_paths.hxx"
#include "../c3utils/c3utils.hxx"
#include "../../support/json.hpp"

#include <algorithm>
#include <cstring>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <unordered_map>
#include <vector>

#ifdef _WIN32
#include <d3dcompiler.h>
#include <wincodec.h>
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
#pragma comment(lib, "windowscodecs.lib")
#endif

namespace bvr_sim {

#ifdef _WIN32

namespace {

template <typename T>
void safe_release(T*& ptr) {
    if (ptr) {
        ptr->Release();
        ptr = nullptr;
    }
}

bool ensure_dynamic_vertex_buffer(D3D11Context& d3d11, UINT required_capacity) {
    if (!d3d11.dynamic_vertex_buffer || d3d11.dynamic_vertex_capacity < required_capacity) {
        safe_release(d3d11.dynamic_vertex_buffer);
        d3d11.common_pipeline_bound = false;
        d3d11.dynamic_vertex_capacity = std::max<UINT>(required_capacity, std::max<UINT>(4096, d3d11.dynamic_vertex_capacity * 2));

        D3D11_BUFFER_DESC vb_desc = {};
        vb_desc.ByteWidth = d3d11.dynamic_vertex_capacity * sizeof(DX11Vertex);
        vb_desc.Usage = D3D11_USAGE_DYNAMIC;
        vb_desc.BindFlags = D3D11_BIND_VERTEX_BUFFER;
        vb_desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;

        HRESULT create_hr = d3d11.device->CreateBuffer(&vb_desc, nullptr, &d3d11.dynamic_vertex_buffer);
        if (FAILED(create_hr) || !d3d11.dynamic_vertex_buffer) {
            d3d11.dynamic_vertex_capacity = 0;
            return false;
        }
    }
    return true;
}

bool upload_vertices(D3D11Context& d3d11, const std::vector<DX11Vertex>& vertices) {
    if (!ensure_dynamic_vertex_buffer(d3d11, static_cast<UINT>(vertices.size()))) {
        return false;
    }
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.dynamic_vertex_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (FAILED(hr)) {
        return false;
    }
    std::memcpy(mapped.pData, vertices.data(), vertices.size() * sizeof(DX11Vertex));
    d3d11.context->Unmap(d3d11.dynamic_vertex_buffer, 0);
    return true;
}

const D3D11Context::MaterialResource* find_material(const D3D11Context& d3d11, const std::string& key) {
    const auto it = d3d11.materials.find(key);
    if (it != d3d11.materials.end()) {
        return &it->second;
    }
    const auto fallback = d3d11.materials.find("aircraft_default");
    if (key != "sky" && key != "terrain" && fallback != d3d11.materials.end()) {
        return &fallback->second;
    }
    return nullptr;
}

bool upload_scene_constants(D3D11Context& d3d11, const RenderCommand& command) {
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.constant_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (SUCCEEDED(hr)) {
        SceneConstants constants{};
        constants.world_view_proj = command.world_view_proj;
        constants.world = command.world;
        constants.shadow_world_view_proj = command.shadow_world_view_proj;
        constants.light_direction_ambient = {
            GameLightingConfig::k_sun_dir_x,
            GameLightingConfig::k_sun_dir_y,
            GameLightingConfig::k_sun_dir_z,
            0.40f
        };
        constants.light_color_intensity = {
            GameLightingConfig::k_sun_r,
            GameLightingConfig::k_sun_g,
            GameLightingConfig::k_sun_b,
            GameLightingConfig::k_sun_intensity
        };
        const D3D11Context::MaterialResource* material = command.use_material_system ? find_material(d3d11, command.material_key) : nullptr;
        const bool terrain_material = material ? material->terrain : command.terrain_material;
        const float fog_start = material ? material->fog_start : 65000.0f;
        const float fog_density = material ? material->fog_density : (terrain_material ? 0.000022f : 0.000010f);
        const std::array<float, 3> fog_color = material ? material->fog_color : std::array<float, 3>{0.74f, 0.81f, 0.85f};
        const float team_tint_strength = command.use_material_system
            ? (material ? material->team_tint_strength : 0.0f)
            : (terrain_material ? 1.0f : 1.0f);
        const float specular_strength = command.use_material_system
            ? (material ? material->specular_strength : command.specular_strength)
            : (terrain_material ? 0.02f : 0.18f);
        const float specular_power = command.use_material_system
            ? (material ? material->specular_power : command.specular_power)
            : (terrain_material ? 10.0f : 24.0f);
        constants.material_flags = {
            command.lighting_enabled ? 1.0f : 0.0f,
            terrain_material ? 1.0f : 0.0f,
            specular_strength,
            specular_power
        };
        constants.camera_position_fog_start = {
            command.camera_position.x,
            command.camera_position.y,
            command.camera_position.z,
            fog_start
        };
        constants.fog_color_density = {fog_color[0], fog_color[1], fog_color[2], fog_density};
        constants.ambient_sky_ground = {0.58f, 0.28f, 0.0f, 0.0f};
        constants.material_tint = {team_tint_strength, command.opacity, command.receive_shadows ? 1.0f : 0.0f, 0.0f};
        constants.shadow_params = {d3d11.shadow_srv ? 1.0f : 0.0f, 0.0012f, 0.48f, 0.0f};
        constants.camera_forward_fov = {
            command.camera_forward.x,
            command.camera_forward.y,
            command.camera_forward.z,
            command.camera_tan_half_fov_y
        };
        constants.camera_right_aspect = {
            command.camera_right.x,
            command.camera_right.y,
            command.camera_right.z,
            command.camera_aspect
        };
        constants.camera_up_pad = {command.camera_up.x, command.camera_up.y, command.camera_up.z, 0.0f};
        std::memcpy(mapped.pData, &constants, sizeof(constants));
        d3d11.context->Unmap(d3d11.constant_buffer, 0);
    } else {
        return false;
    }
    return true;
}

void bind_draw_state(D3D11Context& d3d11, D3D11_PRIMITIVE_TOPOLOGY topology, bool depth_enabled, bool depth_write_enabled, bool blend_enabled) {
    UINT stride = sizeof(DX11Vertex);
    UINT offset = 0;
    if (!d3d11.common_pipeline_bound) {
        d3d11.context->IASetVertexBuffers(0, 1, &d3d11.dynamic_vertex_buffer, &stride, &offset);
        d3d11.context->VSSetShader(d3d11.vertex_shader, nullptr, 0);
        d3d11.context->PSSetShader(d3d11.pixel_shader, nullptr, 0);
        d3d11.context->VSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
        d3d11.context->PSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
        d3d11.context->PSSetSamplers(0, 1, &d3d11.texture_sampler);
        d3d11.context->PSSetSamplers(1, 1, &d3d11.shadow_sampler);
        d3d11.context->IASetInputLayout(d3d11.input_layout);
        d3d11.context->RSSetState(d3d11.rasterizer_state);
        d3d11.common_pipeline_bound = true;
    }
    if (d3d11.current_topology != topology) {
        d3d11.context->IASetPrimitiveTopology(topology);
        d3d11.current_topology = topology;
    }
    ID3D11DepthStencilState* depth_state = d3d11.depth_disabled_state;
    if (depth_enabled) {
        depth_state = depth_write_enabled ? d3d11.depth_state : d3d11.depth_readonly_state;
    }
    if (d3d11.current_depth_state != depth_state) {
        d3d11.context->OMSetDepthStencilState(depth_state, 0);
        d3d11.current_depth_state = depth_state;
    }
    if (d3d11.blend_enabled != blend_enabled) {
        const float blend_factor[4] = {0.0f, 0.0f, 0.0f, 0.0f};
        d3d11.context->OMSetBlendState(blend_enabled ? d3d11.alpha_blend_state : nullptr, blend_factor, 0xffffffff);
        d3d11.blend_enabled = blend_enabled;
    }
}

void bind_material_texture(D3D11Context& d3d11, const RenderCommand& command) {
    d3d11.context->PSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
    d3d11.context->PSSetSamplers(0, 1, &d3d11.texture_sampler);

    const std::string cache_key = command.use_material_system ? command.material_key : "__simple__:" + command.material_key;
    if (d3d11.material_textures_bound && d3d11.current_material_key == cache_key) {
        return;
    }

    const D3D11Context::MaterialResource* material = command.use_material_system ? find_material(d3d11, command.material_key) : nullptr;
    ID3D11ShaderResourceView* srvs[4] = {
        d3d11.white_texture_srv,
        d3d11.flat_normal_texture_srv,
        d3d11.white_texture_srv,
        d3d11.black_texture_srv,
    };
    if (!command.use_material_system) {
        if (command.terrain_material) {
            srvs[0] = d3d11.terrain_texture_srv ? d3d11.terrain_texture_srv : d3d11.white_texture_srv;
        } else {
            srvs[0] = d3d11.object_texture_srv ? d3d11.object_texture_srv : d3d11.white_texture_srv;
            srvs[1] = d3d11.flat_normal_texture_srv;
            srvs[2] = d3d11.white_texture_srv;
            srvs[3] = d3d11.black_texture_srv;
        }
    } else if (material) {
        srvs[0] = material->albedo_srv ? material->albedo_srv : srvs[0];
        srvs[1] = material->normal_srv ? material->normal_srv : srvs[1];
        srvs[2] = material->roughness_srv ? material->roughness_srv : srvs[2];
        srvs[3] = material->metallic_srv ? material->metallic_srv : srvs[3];
    } else if (command.material_key == "terrain") {
        srvs[0] = d3d11.terrain_texture_srv ? d3d11.terrain_texture_srv : d3d11.white_texture_srv;
    }
    d3d11.context->PSSetShaderResources(0, 4, srvs);
    ID3D11ShaderResourceView* shadow_srv[1] = {d3d11.shadow_srv};
    d3d11.context->PSSetShaderResources(4, 1, shadow_srv);
    d3d11.current_material_key = cache_key;
    d3d11.material_textures_bound = true;
}

bool upload_and_draw(
    D3D11Context& d3d11,
    const RenderCommand& command,
    RenderFrameStats& stats) {
    const std::vector<DX11Vertex>& vertices = command.vertices;
    if (vertices.empty()) {
        return true;
    }
    if (!upload_vertices(d3d11, vertices) || !upload_scene_constants(d3d11, command)) {
        return false;
    }
    bind_draw_state(d3d11, command.topology, command.depth_enabled, command.depth_write_enabled, command.blend_enabled);
    bind_material_texture(d3d11, command);
    d3d11.context->Draw(static_cast<UINT>(vertices.size()), 0);

    ++stats.draw_calls;
    stats.vertex_count += static_cast<long>(vertices.size());
    return true;
}

bool execute_hud_pass(D3D11Context& d3d11, const std::vector<RenderCommand>& hud_commands, RenderFrameStats& out_stats) {
    if (hud_commands.empty()) {
        return true;
    }

    ID3D11RenderTargetView* render_targets[1] = {d3d11.rtv};
    d3d11.context->OMSetRenderTargets(1, render_targets, d3d11.dsv);
    d3d11.common_pipeline_bound = false;
    d3d11.current_topology = D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
    d3d11.current_depth_state = nullptr;
    d3d11.blend_enabled = false;
    d3d11.current_material_key.clear();
    d3d11.material_textures_bound = false;

    for (const RenderCommand& command : hud_commands) {
        if (command.type == RenderCommandType::Clear) {
            continue;
        }

        RenderCommand hud_command = command;
        hud_command.depth_enabled = false;
        hud_command.depth_write_enabled = false;
        hud_command.blend_enabled = true;
        hud_command.lighting_enabled = false;
        hud_command.receive_shadows = false;
        if (!upload_and_draw(d3d11, hud_command, out_stats)) {
            return false;
        }
    }

    return true;
}

bool create_depth_buffer(D3D11Context& d3d11, int width, int height, std::string& error) {
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);

    D3D11_TEXTURE2D_DESC depth_desc = {};
    depth_desc.Width = static_cast<UINT>(std::max(1, width));
    depth_desc.Height = static_cast<UINT>(std::max(1, height));
    depth_desc.MipLevels = 1;
    depth_desc.ArraySize = 1;
    depth_desc.Format = DXGI_FORMAT_D24_UNORM_S8_UINT;
    depth_desc.SampleDesc.Count = 1;
    depth_desc.Usage = D3D11_USAGE_DEFAULT;
    depth_desc.BindFlags = D3D11_BIND_DEPTH_STENCIL;

    HRESULT hr = d3d11.device->CreateTexture2D(&depth_desc, nullptr, &d3d11.depth_texture);
    if (FAILED(hr) || !d3d11.depth_texture) {
        error = "CreateTexture2D(depth) failed";
        return false;
    }

    hr = d3d11.device->CreateDepthStencilView(d3d11.depth_texture, nullptr, &d3d11.dsv);
    if (FAILED(hr) || !d3d11.dsv) {
        error = "CreateDepthStencilView failed";
        return false;
    }
    return true;
}

bool create_render_targets_from_swap_chain(D3D11Context& d3d11, HWND hwnd, std::string& error) {
    safe_release(d3d11.rtv);

    ID3D11Texture2D* back_buffer = nullptr;
    HRESULT hr = d3d11.swap_chain->GetBuffer(0, __uuidof(ID3D11Texture2D), reinterpret_cast<void**>(&back_buffer));
    if (FAILED(hr) || !back_buffer) {
        error = "IDXGISwapChain::GetBuffer failed";
        return false;
    }

    hr = d3d11.device->CreateRenderTargetView(back_buffer, nullptr, &d3d11.rtv);
    safe_release(back_buffer);
    if (FAILED(hr) || !d3d11.rtv) {
        error = "CreateRenderTargetView failed";
        return false;
    }

    RECT rect = {};
    GetClientRect(hwnd, &rect);
    return create_depth_buffer(d3d11, rect.right - rect.left, rect.bottom - rect.top, error);
}

std::string load_shader_source(std::string& error) {
    try {
        const auto path = resource_paths::get_resource_path("visualization/shaders/game_dx11.hlsl");
        std::ifstream input(path);
        if (!input.is_open()) {
            error = "failed to open shader: " + path.string();
            return "";
        }
        std::ostringstream buffer;
        buffer << input.rdbuf();
        return buffer.str();
    } catch (const std::exception& exc) {
        error = std::string("failed to resolve shader path: ") + exc.what();
        return "";
    }
}

std::uint32_t pack_rgba8(float r, float g, float b, float a = 1.0f) {
    const auto clamp_to_byte = [](float value) {
        return static_cast<std::uint32_t>(std::max(0.0f, std::min(255.0f, value * 255.0f + 0.5f)));
    };
    return clamp_to_byte(r)
         | (clamp_to_byte(g) << 8)
         | (clamp_to_byte(b) << 16)
         | (clamp_to_byte(a) << 24);
}

bool create_texture_srv_from_pixels(
    D3D11Context& d3d11,
    UINT width,
    UINT height,
    const std::vector<std::uint32_t>& pixels,
    ID3D11ShaderResourceView** out_srv,
    std::string& error) {
    D3D11_TEXTURE2D_DESC texture_desc = {};
    texture_desc.Width = width;
    texture_desc.Height = height;
    texture_desc.MipLevels = 1;
    texture_desc.ArraySize = 1;
    texture_desc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    texture_desc.SampleDesc.Count = 1;
    texture_desc.Usage = D3D11_USAGE_IMMUTABLE;
    texture_desc.BindFlags = D3D11_BIND_SHADER_RESOURCE;

    D3D11_SUBRESOURCE_DATA initial_data = {};
    initial_data.pSysMem = pixels.data();
    initial_data.SysMemPitch = width * sizeof(std::uint32_t);

    ID3D11Texture2D* texture = nullptr;
    HRESULT hr = d3d11.device->CreateTexture2D(&texture_desc, &initial_data, &texture);
    if (FAILED(hr) || !texture) {
        error = "CreateTexture2D(albedo) failed";
        return false;
    }

    D3D11_SHADER_RESOURCE_VIEW_DESC srv_desc = {};
    srv_desc.Format = texture_desc.Format;
    srv_desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
    srv_desc.Texture2D.MipLevels = 1;
    hr = d3d11.device->CreateShaderResourceView(texture, &srv_desc, out_srv);
    safe_release(texture);
    if (FAILED(hr) || !*out_srv) {
        error = "CreateShaderResourceView(albedo) failed";
        return false;
    }
    return true;
}

bool create_texture_srv_from_wic_file(
    D3D11Context& d3d11,
    const std::filesystem::path& path,
    ID3D11ShaderResourceView** out_srv,
    std::string& error) {
    HRESULT co_hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    const bool should_uninitialize = SUCCEEDED(co_hr);
    if (FAILED(co_hr) && co_hr != RPC_E_CHANGED_MODE) {
        error = "CoInitializeEx failed";
        return false;
    }

    IWICImagingFactory* factory = nullptr;
    IWICBitmapDecoder* decoder = nullptr;
    IWICBitmapFrameDecode* frame = nullptr;
    IWICFormatConverter* converter = nullptr;

    auto cleanup = [&]() {
        safe_release(converter);
        safe_release(frame);
        safe_release(decoder);
        safe_release(factory);
        if (should_uninitialize) {
            CoUninitialize();
        }
    };

    HRESULT hr = CoCreateInstance(
        CLSID_WICImagingFactory,
        nullptr,
        CLSCTX_INPROC_SERVER,
        IID_PPV_ARGS(&factory)
    );
    if (FAILED(hr) || !factory) {
        cleanup();
        error = "CoCreateInstance(WICImagingFactory) failed";
        return false;
    }

    const std::wstring wide_path = path.wstring();
    hr = factory->CreateDecoderFromFilename(
        wide_path.c_str(),
        nullptr,
        GENERIC_READ,
        WICDecodeMetadataCacheOnLoad,
        &decoder
    );
    if (FAILED(hr) || !decoder) {
        cleanup();
        error = "WIC CreateDecoderFromFilename failed: " + path.string();
        return false;
    }

    hr = decoder->GetFrame(0, &frame);
    if (FAILED(hr) || !frame) {
        cleanup();
        error = "WIC GetFrame failed: " + path.string();
        return false;
    }

    hr = factory->CreateFormatConverter(&converter);
    if (FAILED(hr) || !converter) {
        cleanup();
        error = "WIC CreateFormatConverter failed";
        return false;
    }

    hr = converter->Initialize(
        frame,
        GUID_WICPixelFormat32bppRGBA,
        WICBitmapDitherTypeNone,
        nullptr,
        0.0,
        WICBitmapPaletteTypeCustom
    );
    if (FAILED(hr)) {
        cleanup();
        error = "WIC format conversion to RGBA failed: " + path.string();
        return false;
    }

    UINT width = 0;
    UINT height = 0;
    hr = converter->GetSize(&width, &height);
    if (FAILED(hr) || width == 0 || height == 0) {
        cleanup();
        error = "WIC GetSize failed: " + path.string();
        return false;
    }

    std::vector<std::uint32_t> pixels(width * height);
    hr = converter->CopyPixels(
        nullptr,
        width * sizeof(std::uint32_t),
        static_cast<UINT>(pixels.size() * sizeof(std::uint32_t)),
        reinterpret_cast<BYTE*>(pixels.data())
    );
    if (FAILED(hr)) {
        cleanup();
        error = "WIC CopyPixels failed: " + path.string();
        return false;
    }

    const bool created = create_texture_srv_from_pixels(d3d11, width, height, pixels, out_srv, error);
    cleanup();
    return created;
}

bool create_procedural_textures(D3D11Context& d3d11, std::string& error) {
    std::vector<std::uint32_t> white_pixels(1, pack_rgba8(1.0f, 1.0f, 1.0f));
    if (!create_texture_srv_from_pixels(d3d11, 1, 1, white_pixels, &d3d11.white_texture_srv, error)) {
        return false;
    }
    std::vector<std::uint32_t> flat_normal_pixels(1, pack_rgba8(0.5f, 0.5f, 1.0f));
    if (!create_texture_srv_from_pixels(d3d11, 1, 1, flat_normal_pixels, &d3d11.flat_normal_texture_srv, error)) {
        return false;
    }
    std::vector<std::uint32_t> black_pixels(1, pack_rgba8(0.0f, 0.0f, 0.0f));
    if (!create_texture_srv_from_pixels(d3d11, 1, 1, black_pixels, &d3d11.black_texture_srv, error)) {
        return false;
    }

    constexpr UINT terrain_size = 2048;
    std::vector<std::uint32_t> terrain_pixels(terrain_size * terrain_size);

    auto saturate = [](float value) {
        return std::max(0.0f, std::min(1.0f, value));
    };
    auto smoothstep = [&](float edge0, float edge1, float value) {
        const float t = saturate((value - edge0) / std::max(0.0001f, edge1 - edge0));
        return t * t * (3.0f - 2.0f * t);
    };
    auto hash2 = [](float x, float y) {
        const float value = std::sin(x * 127.1f + y * 311.7f) * 43758.5453f;
        return value - std::floor(value);
    };
    auto road_presence = [](float world_axis, float lane) {
        const float t = (world_axis + 480000.0f) / 960000.0f;
        const float broken = std::sin(t * 17.0f + lane * 2.37f) * 0.5f + 0.5f;
        const float broad = std::sin(t * 5.0f + lane * 1.13f) * 0.5f + 0.5f;
        return std::max(0.72f, std::min(1.0f, broad * 0.82f + broken * 0.32f));
    };
    auto road_width_scale = [](float world_axis, float lane) {
        const float t = (world_axis + 480000.0f) / 960000.0f;
        const float width_noise = std::sin(t * 23.0f + lane * 3.11f) * 0.5f + 0.5f;
        const float broad_noise = std::sin(t * 7.0f + lane * 1.63f) * 0.5f + 0.5f;
        return 0.2f + 0.3f * std::min(1.0f, width_noise * 0.65f + broad_noise * 0.45f);
    };
    auto road_center_z = [](float world_x, float lane) {
        const float t = (world_x + 480000.0f) / 960000.0f;
        return std::sin(t * 5.7f + lane * 1.37f) * 52000.0f
            + std::sin(t * 13.0f + lane * 0.53f) * 18000.0f
            + std::sin(t * 29.0f + lane * 2.10f) * 6200.0f
            + (lane - 1.0f) * 145000.0f;
    };
    auto road_center_x = [](float world_z, float lane) {
        const float t = (world_z + 480000.0f) / 960000.0f;
        return std::sin(t * 4.8f + lane * 1.91f) * 47000.0f
            + std::sin(t * 11.0f + lane * 0.74f) * 16000.0f
            + std::sin(t * 23.0f + lane * 1.60f) * 5200.0f
            + (lane - 1.0f) * 180000.0f;
    };

    for (UINT y = 0; y < terrain_size; ++y) {
        for (UINT x = 0; x < terrain_size; ++x) {
            const float u = static_cast<float>(x) / static_cast<float>(terrain_size - 1);
            const float v = static_cast<float>(y) / static_cast<float>(terrain_size - 1);
            const float world_x = (u - 0.5f) * 960000.0f;
            const float world_z = (v - 0.5f) * 960000.0f;

            float road_mask = 0.0f;
            for (int lane = 0; lane < 3; ++lane) {
                const float center_z = road_center_z(world_x, static_cast<float>(lane));
                const float width_scale = road_width_scale(world_x, static_cast<float>(lane));
                const float width = (lane == 1 ? 300.0f : 240.0f) * width_scale;
                const float mask = 1.0f - smoothstep(width, width + 360.0f * width_scale, std::abs(world_z - center_z));
                road_mask = std::max(road_mask, mask * road_presence(world_x, static_cast<float>(lane)));
            }
            for (int lane = 0; lane < 2; ++lane) {
                const float center_x = road_center_x(world_z, static_cast<float>(lane));
                const float width_scale = road_width_scale(world_z, static_cast<float>(lane) + 3.0f);
                const float mask = 1.0f - smoothstep(220.0f * width_scale, 520.0f * width_scale, std::abs(world_x - center_x));
                road_mask = std::max(road_mask, mask * road_presence(world_z, static_cast<float>(lane) + 3.0f));
            }
            for (int lane = 0; lane < 2; ++lane) {
                const float t = ((world_x * 0.72f + world_z * 0.28f) + 620000.0f) / 1240000.0f;
                const float slope = lane == 0 ? 0.42f : -0.36f;
                const float offset = lane == 0 ? -94000.0f : 118000.0f;
                const float center_z = world_x * slope + offset
                    + std::sin(t * 8.5f + static_cast<float>(lane) * 1.4f) * 26000.0f
                    + std::sin(t * 21.0f + static_cast<float>(lane) * 2.2f) * 7200.0f;
                const float width_scale = road_width_scale(world_x + world_z, static_cast<float>(lane) + 5.0f);
                const float mask = 1.0f - smoothstep(190.0f * width_scale, 440.0f * width_scale, std::abs(world_z - center_z));
                road_mask = std::max(road_mask, mask * road_presence(world_x + world_z, static_cast<float>(lane) + 5.0f) * 0.86f);
            }

            float water_mask = 0.0f;
            for (int lake = 0; lake < 6; ++lake) {
                const float seed = static_cast<float>(lake);
                const float cx = -305000.0f + seed * 118000.0f + (hash2(seed, 8.0f) - 0.5f) * 42000.0f;
                const float cz = (hash2(seed, 21.0f) - 0.5f) * 340000.0f;
                const float rx = 15000.0f + hash2(seed, 3.0f) * 26000.0f;
                const float rz = 9000.0f + hash2(seed, 5.0f) * 21000.0f;
                const float dx = (world_x - cx) / rx;
                const float dz = (world_z - cz) / rz;
                water_mask = std::max(water_mask, 1.0f - smoothstep(0.82f, 1.08f, dx * dx + dz * dz));
            }

            float village_mask = 0.0f;
            for (int village = 0; village < 9; ++village) {
                const float seed = static_cast<float>(village);
                const float cx = -330000.0f + seed * 82000.0f + (hash2(seed, 31.0f) - 0.5f) * 26000.0f;
                const float cz = road_center_z(cx, std::fmod(seed, 3.0f)) + (hash2(seed, 32.0f) - 0.5f) * 24000.0f;
                const float dx = std::abs(world_x - cx);
                const float dz = std::abs(world_z - cz);
                const float town = (1.0f - smoothstep(2600.0f, 5200.0f, std::max(dx, dz))) * (0.76f + hash2(seed, 37.0f) * 0.24f);
                village_mask = std::max(village_mask, town);
            }

            const float grove_noise = std::sin(world_x * 0.000037f + world_z * 0.000053f)
                * std::sin(world_x * 0.000071f - world_z * 0.000029f);
            const float forest_mask = smoothstep(0.28f, 0.74f, grove_noise) * (1.0f - road_mask) * (1.0f - water_mask);

            const float road = saturate(road_mask * (1.0f - water_mask));
            const float water = saturate(water_mask);
            const float village = saturate(village_mask * (1.0f - water_mask));
            const float forest = saturate(forest_mask);
            terrain_pixels[y * terrain_size + x] = pack_rgba8(road, water, village, forest);
        }
    }
    if (!create_texture_srv_from_pixels(d3d11, terrain_size, terrain_size, terrain_pixels, &d3d11.terrain_texture_srv, error)) {
        return false;
    }

    constexpr UINT object_size = 64;
    std::vector<std::uint32_t> object_pixels(object_size * object_size);
    for (UINT y = 0; y < object_size; ++y) {
        for (UINT x = 0; x < object_size; ++x) {
            const bool panel_line = (x % 16 == 0) || (y % 16 == 0);
            const float diagonal = std::sin((static_cast<float>(x) + static_cast<float>(y)) * 0.35f) * 0.5f + 0.5f;
            const float shade = panel_line ? 0.62f : 0.88f + diagonal * 0.10f;
            object_pixels[y * object_size + x] = pack_rgba8(shade, shade, shade * 0.96f);
        }
    }
    if (!create_texture_srv_from_pixels(d3d11, object_size, object_size, object_pixels, &d3d11.object_texture_srv, error)) {
        return false;
    }

    return true;
}

std::string read_text_file(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input.is_open()) {
        return "";
    }
    std::ostringstream buffer;
    buffer << input.rdbuf();
    return buffer.str();
}

std::string extract_json_string(const std::string& block, const std::string& field_name) {
    const std::string marker = "\"" + field_name + "\"";
    const size_t marker_pos = block.find(marker);
    if (marker_pos == std::string::npos) {
        return "";
    }
    const size_t colon_pos = block.find(':', marker_pos + marker.size());
    if (colon_pos == std::string::npos) {
        return "";
    }
    const size_t quote_start = block.find('"', colon_pos + 1);
    if (quote_start == std::string::npos) {
        return "";
    }
    const size_t quote_end = block.find('"', quote_start + 1);
    if (quote_end == std::string::npos) {
        return "";
    }
    return block.substr(quote_start + 1, quote_end - quote_start - 1);
}

float extract_json_float(const std::string& block, const std::string& field_name, float fallback) {
    const std::string marker = "\"" + field_name + "\"";
    const size_t marker_pos = block.find(marker);
    if (marker_pos == std::string::npos) {
        return fallback;
    }
    const size_t colon_pos = block.find(':', marker_pos + marker.size());
    if (colon_pos == std::string::npos) {
        return fallback;
    }
    const size_t value_start = block.find_first_of("-0123456789.", colon_pos + 1);
    if (value_start == std::string::npos) {
        return fallback;
    }
    const size_t value_end = block.find_first_not_of("-0123456789.eE+", value_start);
    try {
        return std::stof(block.substr(value_start, value_end == std::string::npos ? std::string::npos : value_end - value_start));
    } catch (...) {
        return fallback;
    }
}

bool extract_json_bool(const std::string& block, const std::string& field_name, bool fallback) {
    const std::string marker = "\"" + field_name + "\"";
    const size_t marker_pos = block.find(marker);
    if (marker_pos == std::string::npos) {
        return fallback;
    }
    const size_t colon_pos = block.find(':', marker_pos + marker.size());
    if (colon_pos == std::string::npos) {
        return fallback;
    }
    const size_t value_start = block.find_first_not_of(" \t\r\n", colon_pos + 1);
    if (value_start == std::string::npos) {
        return fallback;
    }
    if (block.compare(value_start, 4, "true") == 0) {
        return true;
    }
    if (block.compare(value_start, 5, "false") == 0) {
        return false;
    }
    return fallback;
}

std::array<float, 3> extract_json_float3(
    const std::string& block,
    const std::string& field_name,
    const std::array<float, 3>& fallback) {
    const std::string marker = "\"" + field_name + "\"";
    const size_t marker_pos = block.find(marker);
    if (marker_pos == std::string::npos) {
        return fallback;
    }
    const size_t colon_pos = block.find(':', marker_pos + marker.size());
    if (colon_pos == std::string::npos) {
        return fallback;
    }
    const size_t open_pos = block.find('[', colon_pos + 1);
    const size_t close_pos = block.find(']', open_pos == std::string::npos ? colon_pos + 1 : open_pos + 1);
    if (open_pos == std::string::npos || close_pos == std::string::npos) {
        return fallback;
    }

    std::array<float, 3> values = fallback;
    size_t value_pos = open_pos + 1;
    for (int i = 0; i < 3; ++i) {
        const size_t value_start = block.find_first_of("-0123456789.", value_pos);
        if (value_start == std::string::npos || value_start > close_pos) {
            return fallback;
        }
        const size_t value_end = block.find_first_not_of("-0123456789.eE+", value_start);
        try {
            values[i] = std::stof(block.substr(
                value_start,
                value_end == std::string::npos ? std::string::npos : value_end - value_start
            ));
        } catch (...) {
            return fallback;
        }
        value_pos = value_end == std::string::npos ? close_pos : value_end;
    }
    return values;
}

std::string extract_json_object_block(const std::string& text, const std::string& key) {
    const std::string marker = "\"" + key + "\"";
    const size_t marker_pos = text.find(marker);
    if (marker_pos == std::string::npos) {
        return "";
    }
    const size_t open_pos = text.find('{', marker_pos + marker.size());
    if (open_pos == std::string::npos) {
        return "";
    }

    int depth = 0;
    for (size_t i = open_pos; i < text.size(); ++i) {
        if (text[i] == '{') {
            ++depth;
        } else if (text[i] == '}') {
            --depth;
            if (depth == 0) {
                return text.substr(open_pos, i - open_pos + 1);
            }
        }
    }
    return "";
}

ID3D11ShaderResourceView* load_optional_texture(
    D3D11Context& d3d11,
    const std::string& relative_path,
    std::string& error) {
    if (relative_path.empty()) {
        return nullptr;
    }
    const auto cached = d3d11.material_texture_cache.find(relative_path);
    if (cached != d3d11.material_texture_cache.end()) {
        return cached->second;
    }

    ID3D11ShaderResourceView* srv = nullptr;
    try {
        const auto path = resource_paths::get_resource_path(relative_path);
        if (create_texture_srv_from_wic_file(d3d11, path, &srv, error) && srv) {
            d3d11.material_texture_cache[relative_path] = srv;
        }
    } catch (...) {
        srv = nullptr;
    }
    return srv;
}

void load_material_resources(D3D11Context& d3d11) {
    const std::string manifest = read_text_file(resource_paths::get_resource_path("visualization/materials/materials.json"));
    const std::vector<std::string> material_keys = {
        "sky",
        "terrain",
        "aircraft_default",
        "missile_default",
        "aircraft_dark_metal",
        "aircraft_bright_metal",
        "missile_bright_metal",
    };

    for (const std::string& key : material_keys) {
        const std::string block = extract_json_object_block(manifest, key);
        D3D11Context::MaterialResource material;
        material.key = key;
        material.terrain = key == "terrain";
        material.team_tint_strength = key == "terrain" ? 1.0f : 0.55f;
        material.specular_strength = key == "terrain" ? 0.04f : 0.28f;
        material.specular_power = key == "missile_default" ? 64.0f : 48.0f;
        material.fog_start = 65000.0f;
        material.fog_density = key == "terrain" ? 0.000022f : 0.000010f;
        material.fog_color = {0.74f, 0.81f, 0.85f};
        if (!block.empty()) {
            const std::string base_key = extract_json_string(block, "base");
            const D3D11Context::MaterialResource* base_material = base_key.empty() ? nullptr : find_material(d3d11, base_key);
            if (base_material) {
                material.terrain = base_material->terrain;
                material.team_tint_strength = base_material->team_tint_strength;
                material.specular_strength = base_material->specular_strength;
                material.specular_power = base_material->specular_power;
                material.fog_start = base_material->fog_start;
                material.fog_density = base_material->fog_density;
                material.fog_color = base_material->fog_color;
                material.albedo_srv = base_material->albedo_srv;
                material.normal_srv = base_material->normal_srv;
                material.roughness_srv = base_material->roughness_srv;
                material.metallic_srv = base_material->metallic_srv;
            }

            material.terrain = extract_json_bool(block, "terrain", material.terrain);
            material.team_tint_strength = extract_json_float(block, "team_tint_strength", material.team_tint_strength);
            material.specular_strength = extract_json_float(block, "specular_strength", material.specular_strength);
            material.specular_power = extract_json_float(block, "specular_power", material.specular_power);
            material.fog_start = extract_json_float(block, "fog_start", material.fog_start);
            material.fog_density = extract_json_float(block, "fog_density", material.fog_density);
            material.fog_color = extract_json_float3(block, "fog_color", material.fog_color);

            std::string image_error;
            const std::string albedo = extract_json_string(block, "albedo");
            const std::string normal = extract_json_string(block, "normal");
            const std::string roughness = extract_json_string(block, "roughness");
            const std::string metallic = extract_json_string(block, "metallic");
            if (!albedo.empty()) {
                material.albedo_srv = load_optional_texture(d3d11, albedo, image_error);
            }
            if (!normal.empty()) {
                material.normal_srv = load_optional_texture(d3d11, normal, image_error);
            }
            if (!roughness.empty()) {
                material.roughness_srv = load_optional_texture(d3d11, roughness, image_error);
            }
            if (!metallic.empty()) {
                material.metallic_srv = load_optional_texture(d3d11, metallic, image_error);
            }
        }

        if (key == "terrain" && !material.albedo_srv) {
            material.albedo_srv = d3d11.terrain_texture_srv;
        }
        if ((key == "aircraft_default" || key == "missile_default") && !material.albedo_srv) {
            material.albedo_srv = d3d11.object_texture_srv;
        }
        d3d11.materials[key] = material;
    }
}

bool create_texture_sampler(D3D11Context& d3d11, std::string& error) {
    D3D11_SAMPLER_DESC sampler_desc = {};
    sampler_desc.Filter = D3D11_FILTER_ANISOTROPIC;
    sampler_desc.AddressU = D3D11_TEXTURE_ADDRESS_WRAP;
    sampler_desc.AddressV = D3D11_TEXTURE_ADDRESS_WRAP;
    sampler_desc.AddressW = D3D11_TEXTURE_ADDRESS_WRAP;
    sampler_desc.MaxAnisotropy = 4;
    sampler_desc.ComparisonFunc = D3D11_COMPARISON_NEVER;
    sampler_desc.MinLOD = 0.0f;
    sampler_desc.MaxLOD = D3D11_FLOAT32_MAX;

    HRESULT hr = d3d11.device->CreateSamplerState(&sampler_desc, &d3d11.texture_sampler);
    if (FAILED(hr) || !d3d11.texture_sampler) {
        error = "CreateSamplerState(texture_sampler) failed";
        return false;
    }
    return true;
}

} // namespace

void destroy_d3d11(D3D11Context& d3d11) {
    for (auto& [_, material] : d3d11.materials) {
        if (material.owns_albedo) {
            safe_release(material.albedo_srv);
        }
        if (material.owns_normal) {
            safe_release(material.normal_srv);
        }
        if (material.owns_roughness) {
            safe_release(material.roughness_srv);
        }
        if (material.owns_metallic) {
            safe_release(material.metallic_srv);
        }
    }
    d3d11.materials.clear();
    for (auto& [_, texture_srv] : d3d11.material_texture_cache) {
        safe_release(texture_srv);
    }
    d3d11.material_texture_cache.clear();
    safe_release(d3d11.texture_sampler);
    safe_release(d3d11.object_metallic_texture_srv);
    safe_release(d3d11.object_roughness_texture_srv);
    safe_release(d3d11.object_normal_texture_srv);
    safe_release(d3d11.object_texture_srv);
    safe_release(d3d11.terrain_texture_srv);
    safe_release(d3d11.black_texture_srv);
    safe_release(d3d11.flat_normal_texture_srv);
    safe_release(d3d11.white_texture_srv);
    safe_release(d3d11.alpha_blend_state);
    destroy_shadow_map_resources(d3d11);
    safe_release(d3d11.depth_disabled_state);
    safe_release(d3d11.depth_readonly_state);
    safe_release(d3d11.depth_state);
    safe_release(d3d11.rasterizer_state);
    safe_release(d3d11.dynamic_vertex_buffer);
    safe_release(d3d11.constant_buffer);
    safe_release(d3d11.input_layout);
    safe_release(d3d11.shadow_vertex_shader);
    safe_release(d3d11.pixel_shader);
    safe_release(d3d11.vertex_shader);
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);
    safe_release(d3d11.rtv);
    safe_release(d3d11.swap_chain);
    safe_release(d3d11.context);
    safe_release(d3d11.device);
}

bool create_d3d11(HWND hwnd, D3D11Context& d3d11, std::string& error) {
    DXGI_SWAP_CHAIN_DESC swap_desc = {};
    swap_desc.BufferCount = 2;
    swap_desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    swap_desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    swap_desc.OutputWindow = hwnd;
    swap_desc.SampleDesc.Count = 1;
    swap_desc.Windowed = TRUE;
    swap_desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;

    UINT create_flags = 0;
#if defined(_DEBUG)
    create_flags |= D3D11_CREATE_DEVICE_DEBUG;
#endif

    D3D_FEATURE_LEVEL feature_level = D3D_FEATURE_LEVEL_11_0;
    HRESULT hr = D3D11CreateDeviceAndSwapChain(
        nullptr,
        D3D_DRIVER_TYPE_HARDWARE,
        nullptr,
        create_flags,
        nullptr,
        0,
        D3D11_SDK_VERSION,
        &swap_desc,
        &d3d11.swap_chain,
        &d3d11.device,
        &feature_level,
        &d3d11.context
    );
    if (FAILED(hr) && (create_flags & D3D11_CREATE_DEVICE_DEBUG)) {
        create_flags &= ~D3D11_CREATE_DEVICE_DEBUG;
        hr = D3D11CreateDeviceAndSwapChain(
            nullptr,
            D3D_DRIVER_TYPE_HARDWARE,
            nullptr,
            create_flags,
            nullptr,
            0,
            D3D11_SDK_VERSION,
            &swap_desc,
            &d3d11.swap_chain,
            &d3d11.device,
            &feature_level,
            &d3d11.context
        );
    }
    if (FAILED(hr) || !d3d11.device || !d3d11.context || !d3d11.swap_chain) {
        error = "D3D11CreateDeviceAndSwapChain failed";
        return false;
    }

    if (!create_render_targets_from_swap_chain(d3d11, hwnd, error)) {
        return false;
    }

    std::string shader_source_storage = load_shader_source(error);
    if (shader_source_storage.empty()) {
        return false;
    }
    const char* shader_source = shader_source_storage.c_str();

    ID3DBlob* vs_blob = nullptr;
    ID3DBlob* shadow_vs_blob = nullptr;
    ID3DBlob* ps_blob = nullptr;
    ID3DBlob* error_blob = nullptr;
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "vs_main", "vs_4_0", 0, 0, &vs_blob, &error_blob);
    if (FAILED(hr) || !vs_blob) {
        safe_release(error_blob);
        error = "D3DCompile(vs_main) failed";
        return false;
    }
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "vs_shadow_main", "vs_4_0", 0, 0, &shadow_vs_blob, &error_blob);
    if (FAILED(hr) || !shadow_vs_blob) {
        safe_release(error_blob);
        safe_release(vs_blob);
        error = "D3DCompile(vs_shadow_main) failed";
        return false;
    }
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "ps_main", "ps_4_0", 0, 0, &ps_blob, &error_blob);
    safe_release(error_blob);
    if (FAILED(hr) || !ps_blob) {
        safe_release(shadow_vs_blob);
        safe_release(vs_blob);
        error = "D3DCompile(ps_main) failed";
        return false;
    }

    hr = d3d11.device->CreateVertexShader(vs_blob->GetBufferPointer(), vs_blob->GetBufferSize(), nullptr, &d3d11.vertex_shader);
    if (FAILED(hr) || !d3d11.vertex_shader) {
        safe_release(shadow_vs_blob);
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreateVertexShader failed";
        return false;
    }
    hr = d3d11.device->CreateVertexShader(shadow_vs_blob->GetBufferPointer(), shadow_vs_blob->GetBufferSize(), nullptr, &d3d11.shadow_vertex_shader);
    if (FAILED(hr) || !d3d11.shadow_vertex_shader) {
        safe_release(shadow_vs_blob);
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreateVertexShader(shadow) failed";
        return false;
    }
    hr = d3d11.device->CreatePixelShader(ps_blob->GetBufferPointer(), ps_blob->GetBufferSize(), nullptr, &d3d11.pixel_shader);
    if (FAILED(hr) || !d3d11.pixel_shader) {
        safe_release(shadow_vs_blob);
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreatePixelShader failed";
        return false;
    }

    D3D11_INPUT_ELEMENT_DESC input_layout_desc[] = {
        {"POSITION", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(DX11Vertex, position)), D3D11_INPUT_PER_VERTEX_DATA, 0},
        {"COLOR", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(DX11Vertex, color)), D3D11_INPUT_PER_VERTEX_DATA, 0},
        {"NORMAL", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(DX11Vertex, normal)), D3D11_INPUT_PER_VERTEX_DATA, 0},
        {"TEXCOORD", 0, DXGI_FORMAT_R32G32_FLOAT, 0, static_cast<UINT>(offsetof(DX11Vertex, uv)), D3D11_INPUT_PER_VERTEX_DATA, 0},
    };
    hr = d3d11.device->CreateInputLayout(
        input_layout_desc,
        4,
        vs_blob->GetBufferPointer(),
        vs_blob->GetBufferSize(),
        &d3d11.input_layout
    );
    safe_release(vs_blob);
    safe_release(shadow_vs_blob);
    safe_release(ps_blob);
    if (FAILED(hr) || !d3d11.input_layout) {
        error = "CreateInputLayout failed";
        return false;
    }

    D3D11_BUFFER_DESC cb_desc = {};
    cb_desc.ByteWidth = sizeof(SceneConstants);
    cb_desc.Usage = D3D11_USAGE_DYNAMIC;
    cb_desc.BindFlags = D3D11_BIND_CONSTANT_BUFFER;
    cb_desc.CPUAccessFlags = D3D11_CPU_ACCESS_WRITE;
    hr = d3d11.device->CreateBuffer(&cb_desc, nullptr, &d3d11.constant_buffer);
    if (FAILED(hr) || !d3d11.constant_buffer) {
        error = "CreateBuffer(constant_buffer) failed";
        return false;
    }

    D3D11_RASTERIZER_DESC raster_desc = {};
    raster_desc.FillMode = D3D11_FILL_SOLID;
    raster_desc.CullMode = D3D11_CULL_BACK;
    raster_desc.DepthClipEnable = TRUE;
    hr = d3d11.device->CreateRasterizerState(&raster_desc, &d3d11.rasterizer_state);
    if (FAILED(hr) || !d3d11.rasterizer_state) {
        error = "CreateRasterizerState failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_desc = {};
    depth_desc.DepthEnable = TRUE;
    depth_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ALL;
    depth_desc.DepthFunc = D3D11_COMPARISON_LESS_EQUAL;
    hr = d3d11.device->CreateDepthStencilState(&depth_desc, &d3d11.depth_state);
    if (FAILED(hr) || !d3d11.depth_state) {
        error = "CreateDepthStencilState failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_readonly_desc = depth_desc;
    depth_readonly_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    hr = d3d11.device->CreateDepthStencilState(&depth_readonly_desc, &d3d11.depth_readonly_state);
    if (FAILED(hr) || !d3d11.depth_readonly_state) {
        error = "CreateDepthStencilState(depth_readonly) failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_DESC depth_disabled_desc = {};
    depth_disabled_desc.DepthEnable = FALSE;
    depth_disabled_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    depth_disabled_desc.DepthFunc = D3D11_COMPARISON_ALWAYS;
    hr = d3d11.device->CreateDepthStencilState(&depth_disabled_desc, &d3d11.depth_disabled_state);
    if (FAILED(hr) || !d3d11.depth_disabled_state) {
        error = "CreateDepthStencilState(depth_disabled) failed";
        return false;
    }

    D3D11_BLEND_DESC blend_desc = {};
    blend_desc.RenderTarget[0].BlendEnable = TRUE;
    blend_desc.RenderTarget[0].SrcBlend = D3D11_BLEND_SRC_ALPHA;
    blend_desc.RenderTarget[0].DestBlend = D3D11_BLEND_INV_SRC_ALPHA;
    blend_desc.RenderTarget[0].BlendOp = D3D11_BLEND_OP_ADD;
    blend_desc.RenderTarget[0].SrcBlendAlpha = D3D11_BLEND_ONE;
    blend_desc.RenderTarget[0].DestBlendAlpha = D3D11_BLEND_INV_SRC_ALPHA;
    blend_desc.RenderTarget[0].BlendOpAlpha = D3D11_BLEND_OP_ADD;
    blend_desc.RenderTarget[0].RenderTargetWriteMask = D3D11_COLOR_WRITE_ENABLE_ALL;
    hr = d3d11.device->CreateBlendState(&blend_desc, &d3d11.alpha_blend_state);
    if (FAILED(hr) || !d3d11.alpha_blend_state) {
        error = "CreateBlendState(alpha) failed";
        return false;
    }

    if (!create_procedural_textures(d3d11, error)) {
        return false;
    }
    load_material_resources(d3d11);
    if (!create_texture_sampler(d3d11, error)) {
        return false;
    }
    if (!create_shadow_map_resources(d3d11, error)) {
        return false;
    }

    return true;
}

bool resize_swap_chain_if_needed(D3D11Context& d3d11, HWND hwnd, UINT width, UINT height, std::string& error) {
    if (width == 0 || height == 0) {
        return true;
    }
    if (d3d11.back_buffer_width == width && d3d11.back_buffer_height == height && d3d11.rtv && d3d11.dsv) {
        return true;
    }

    safe_release(d3d11.rtv);
    safe_release(d3d11.dsv);
    safe_release(d3d11.depth_texture);
    HRESULT hr = d3d11.swap_chain->ResizeBuffers(0, width, height, DXGI_FORMAT_UNKNOWN, 0);
    if (FAILED(hr)) {
        error = "ResizeBuffers failed";
        return false;
    }
    if (!create_render_targets_from_swap_chain(d3d11, hwnd, error)) {
        return false;
    }
    d3d11.back_buffer_width = width;
    d3d11.back_buffer_height = height;
    return true;
}

void update_viewport_from_client_rect(HWND hwnd, ID3D11DeviceContext* context, UINT& out_width, UINT& out_height) {
    RECT rect = {};
    GetClientRect(hwnd, &rect);
    out_width = static_cast<UINT>(std::max(1L, rect.right - rect.left));
    out_height = static_cast<UINT>(std::max(1L, rect.bottom - rect.top));

    D3D11_VIEWPORT viewport = {};
    viewport.TopLeftX = 0.0f;
    viewport.TopLeftY = 0.0f;
    viewport.Width = static_cast<float>(out_width);
    viewport.Height = static_cast<float>(out_height);
    viewport.MinDepth = 0.0f;
    viewport.MaxDepth = 1.0f;
    context->RSSetViewports(1, &viewport);
}

bool execute_render_commands(D3D11Context& d3d11, const RenderCommandList& command_list, RenderFrameStats& out_stats) {
    out_stats = {};
    out_stats.command_count = static_cast<long>(command_list.commands.size() + command_list.hud_commands.size());

    if (!render_shadow_map(d3d11, command_list)) {
        return false;
    }

    ID3D11RenderTargetView* render_targets[1] = {d3d11.rtv};
    d3d11.context->OMSetRenderTargets(1, render_targets, d3d11.dsv);
    d3d11.common_pipeline_bound = false;
    D3D11_VIEWPORT viewport = {};
    viewport.TopLeftX = 0.0f;
    viewport.TopLeftY = 0.0f;
    viewport.Width = static_cast<float>(std::max<UINT>(1, d3d11.back_buffer_width));
    viewport.Height = static_cast<float>(std::max<UINT>(1, d3d11.back_buffer_height));
    viewport.MinDepth = 0.0f;
    viewport.MaxDepth = 1.0f;
    d3d11.context->RSSetViewports(1, &viewport);

    for (const RenderCommand& command : command_list.commands) {
        if (command.type == RenderCommandType::Clear) {
            d3d11.context->ClearRenderTargetView(d3d11.rtv, command.clear_color.data());
            d3d11.context->ClearDepthStencilView(d3d11.dsv, D3D11_CLEAR_DEPTH | D3D11_CLEAR_STENCIL, 1.0f, 0);
            continue;
        }

        if (!upload_and_draw(d3d11, command, out_stats)) {
            return false;
        }
    }

    if (!execute_hud_pass(d3d11, command_list.hud_commands, out_stats)) {
        return false;
    }

    return true;
}

// ---------------------------------------------------------------------------
// DX11Renderer implementation
// ---------------------------------------------------------------------------

DX11Renderer::DX11Renderer() = default;
DX11Renderer::~DX11Renderer() { destroy(); }

bool DX11Renderer::initialize(std::string& error) {
    if (!create_window(window_, error)) {
        return false;
    }
    if (!create_d3d11(window_.hwnd, d3d11_, error)) {
        destroy_window(window_);
        return false;
    }
    initialized_ = true;
    return true;
}

void DX11Renderer::destroy() {
    if (initialized_) {
        destroy_d3d11(d3d11_);
        destroy_window(window_);
        initialized_ = false;
    }
}

bool DX11Renderer::process_messages() {
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

void DX11Renderer::submit_command(const TelemetryCommand& command) {
    if (command_submitter_) {
        command_submitter_(command);
    }
}

void DX11Renderer::set_command_submitter(std::function<void(const TelemetryCommand&)> submitter) {
    command_submitter_ = std::move(submitter);
}

bool DX11Renderer::get_shadows_enabled() const {
    return window_.input.shadows_enabled;
}

bool DX11Renderer::get_material_system_enabled() const {
    return window_.input.material_system_enabled;
}

void DX11Renderer::apply_camera_state(const RendererCameraState& state) {
    window_.input.input_mode = state.input_mode == "control"
        ? ViewerInputState::InputMode::Control
        : ViewerInputState::InputMode::Follow;

    if (state.camera_mode == "follow") {
        window_.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
        window_.input.focus_uid = state.target_uid;
        window_.input.focus_cycle_index = state.target_uid.empty() ? state.focus_index : -1;
    } else {
        window_.input.camera_mode = ViewerInputState::CameraMode::Free;
        window_.input.focus_uid.clear();
        window_.input.focus_cycle_index = -1;
    }

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

RendererCameraState DX11Renderer::get_camera_state() const {
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

void DX11Renderer::update_input(const WorldSnapshot* snapshot, float dt_seconds) {
    update_camera(window_.input, dt_seconds);
    constexpr int kGameModeActionPenalty = -1;

    // Update snapshot UIDs for focus cycling
    window_.input.snapshot_uids.clear();
    if (snapshot) {
        window_.input.snapshot_uids.reserve(snapshot->objects.size());
        for (const auto& object : snapshot->objects) {
            if (object.alive) {
                window_.input.snapshot_uids.push_back(object.uid);
            }
        }
    }

    const int object_count = static_cast<int>(window_.input.snapshot_uids.size());
    if (object_count <= 0) {
        window_.input.focus_cycle_index = -1;
        window_.input.focus_uid.clear();
        window_.input.camera_mode = ViewerInputState::CameraMode::Free;
        window_.input.focus_cycle_requested = false;
    } else {
        if (!window_.input.focus_uid.empty()) {
            auto it = std::find(window_.input.snapshot_uids.begin(), window_.input.snapshot_uids.end(), window_.input.focus_uid);
            if (it != window_.input.snapshot_uids.end()) {
                window_.input.focus_cycle_index = static_cast<int>(std::distance(window_.input.snapshot_uids.begin(), it));
            } else {
                window_.input.focus_cycle_index = -1;
                window_.input.focus_uid.clear();
            }
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
            window_.input.camera_mode = ViewerInputState::CameraMode::FollowObject;
        } else {
            window_.input.focus_cycle_index = -1;
            window_.input.focus_uid.clear();
            window_.input.camera_mode = ViewerInputState::CameraMode::Free;
        }
    }

    if (!window_.input.mouse_aim_enabled
        || window_.input.input_mode != ViewerInputState::InputMode::Control
        || window_.input.camera_mode != ViewerInputState::CameraMode::FollowObject
        || window_.input.focus_uid.empty()) {
        if (!action_control_uid_.empty()) {
            auto submit_clear = [this, kGameModeActionPenalty](const std::string& uid, const char* key) {
                json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
                kv[key] = json::JSON();
                TelemetryCommand command;
                command.kind = TelemetryCommandKind::Command;
                command.target_uid = uid;
                command.payload = json::String("setp " + uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
                submit_command(command);
            };
            submit_clear(action_control_uid_, "aileron_cmd");
            submit_clear(action_control_uid_, "elevator_cmd");
            submit_clear(action_control_uid_, "rudder_cmd");
            submit_clear(action_control_uid_, "fire");
            action_control_uid_.clear();
        }
        window_.input.fire_once_requested = false;
        window_.input.pylon_cycle_requested = false;
        return;
    }

    auto submit_action = [this, kGameModeActionPenalty](const char* key, double value) {
        json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
        kv[key] = json::Float(value);
        TelemetryCommand command;
        command.kind = TelemetryCommandKind::Command;
        command.target_uid = window_.input.focus_uid;
        command.payload = json::String("setp " + window_.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
        submit_command(command);
    };
    auto submit_action_null = [this, kGameModeActionPenalty](const char* key) {
        json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
        kv[key] = json::JSON();
        TelemetryCommand command;
        command.kind = TelemetryCommandKind::Command;
        command.target_uid = window_.input.focus_uid;
        command.payload = json::String("setp " + window_.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
        submit_command(command);
    };
    auto submit_action_json = [this, kGameModeActionPenalty](const char* key, const json::JSON& value) {
        json::JSON kv = json::JSON::Make(json::JSON::Class::Object);
        kv[key] = value;
        TelemetryCommand command;
        command.kind = TelemetryCommandKind::Command;
        command.target_uid = window_.input.focus_uid;
        command.payload = json::String("setp " + window_.input.focus_uid + " " + std::to_string(kGameModeActionPenalty) + " " + kv.dump(1, "", ""));
        submit_command(command);
    };

    float delta_heading = 0.0f;
    float delta_altitude = 0.0f;
    if (snapshot) {
        auto focused_it = std::find_if(snapshot->objects.begin(), snapshot->objects.end(),
            [this](const TelemetryObjectState& obj) { return obj.uid == window_.input.focus_uid; });
        if (focused_it != snapshot->objects.end()) {
            const float cy = std::cos(window_.input.aim_yaw);
            const float sy = std::sin(window_.input.aim_yaw);
            const float cp = std::cos(window_.input.aim_pitch);
            const float sp = std::sin(window_.input.aim_pitch);
            const float fwd_n = -cp * cy;
            const float fwd_w = -cp * sy;
            const float fwd_u = -sp;
            const float desired_heading = std::atan2(fwd_w, fwd_n);
            const float desired_pitch = -std::atan2(fwd_u, std::sqrt(fwd_n * fwd_n + fwd_w * fwd_w));
            const float current_yaw = static_cast<float>(focused_it->orientation[2]);
            const float heading_err = static_cast<float>(c3utils::norm_pi(desired_heading - current_yaw));
            const float max_heading = static_cast<float>(c3utils::deg2rad(85.0));
            const float max_pitch = static_cast<float>(c3utils::deg2rad(45));
            delta_heading = std::clamp(heading_err / max_heading, -1.0f, 1.0f);
            delta_altitude = std::clamp(-(desired_pitch / max_pitch), -1.0f, 1.0f);
        }
    }

    const float aileron_cmd = window_.input.ctrl_aileron_right ? (window_.input.ctrl_aileron_left ? 0.0f : 1.0f)
                                                               : (window_.input.ctrl_aileron_left ? -1.0f : 0.0f);
    const float elevator_cmd = window_.input.ctrl_elevator_up ? (window_.input.ctrl_elevator_down ? 0.0f : 1.0f)
                                                              : (window_.input.ctrl_elevator_down ? -1.0f : 0.0f);
    const float rudder_cmd = window_.input.ctrl_rudder_right ? (window_.input.ctrl_rudder_left ? 0.0f : -1.0f)
                                                             : (window_.input.ctrl_rudder_left ? 1.0f : 0.0f);
    const bool any_surface_key = window_.input.ctrl_aileron_left || window_.input.ctrl_aileron_right
        || window_.input.ctrl_elevator_up || window_.input.ctrl_elevator_down
        || window_.input.ctrl_rudder_left || window_.input.ctrl_rudder_right;

    action_control_uid_ = window_.input.focus_uid;
    submit_action("delta_heading", delta_heading);
    submit_action("delta_altitude", delta_altitude);
    submit_action("delta_speed", 0.0);

    if (any_surface_key) {
        if (snapshot) {
            auto focused_it = std::find_if(snapshot->objects.begin(), snapshot->objects.end(),
                [this](const TelemetryObjectState& obj) { return obj.uid == window_.input.focus_uid; });
            if (focused_it != snapshot->objects.end()) {
                window_.input.aim_yaw = static_cast<float>(c3utils::norm_pi(static_cast<float>(focused_it->orientation[2]) - static_cast<float>(c3utils::pi)));
                window_.input.aim_pitch = std::clamp(static_cast<float>(focused_it->orientation[1]), -1.45f, 1.45f);
            }
        }
        submit_action("aileron_cmd", aileron_cmd);
        submit_action("elevator_cmd", elevator_cmd);
        submit_action("rudder_cmd", rudder_cmd);
    } else {
        submit_action_null("aileron_cmd");
        submit_action_null("elevator_cmd");
        submit_action_null("rudder_cmd");
    }

    // Pylon management
    std::vector<std::string> selectable_pylons;
    if (snapshot) {
        auto focused_it = std::find_if(snapshot->objects.begin(), snapshot->objects.end(),
            [this](const TelemetryObjectState& obj) { return obj.uid == window_.input.focus_uid; });
        if (focused_it != snapshot->objects.end()) {
            const json::JSON& reg = focused_it->debug_register;
            if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("pylon_mounts", json::JSON::Class::Object)) {
                for (const auto& kv : reg.at("pylon_mounts").ObjectRange()) {
                    selectable_pylons.push_back(kv.first);
                }
            }
        }
    }
    if (!selectable_pylons.empty()) {
        if (window_.input.selected_pylon_name.empty()
            || std::find(selectable_pylons.begin(), selectable_pylons.end(), window_.input.selected_pylon_name) == selectable_pylons.end()) {
            window_.input.selected_pylon_name = selectable_pylons.front();
        }
        if (window_.input.pylon_cycle_requested) {
            auto it = std::find(selectable_pylons.begin(), selectable_pylons.end(), window_.input.selected_pylon_name);
            size_t idx = it != selectable_pylons.end() ? (static_cast<size_t>(std::distance(selectable_pylons.begin(), it)) + 1) % selectable_pylons.size() : 0;
            window_.input.selected_pylon_name = selectable_pylons[idx];
        }
    } else {
        window_.input.selected_pylon_name.clear();
    }
    window_.input.pylon_cycle_requested = false;

    // Fire
    bool fire_emitted = false;
    if (window_.input.fire_once_requested && snapshot) {
        auto focused_it = std::find_if(snapshot->objects.begin(), snapshot->objects.end(),
            [this](const TelemetryObjectState& obj) { return obj.uid == window_.input.focus_uid; });
        if (focused_it != snapshot->objects.end()) {
            const json::JSON& reg = focused_it->debug_register;
            std::string weapon_spec;
            if (!window_.input.selected_pylon_name.empty()
                && reg.JSONType() == json::JSON::Class::Object
                && reg.hasKey("pylon_mounts", json::JSON::Class::Object)) {
                const auto pylon_mounts = reg.at("pylon_mounts");
                if (pylon_mounts.hasKey(window_.input.selected_pylon_name, json::JSON::Class::String)) {
                    weapon_spec = pylon_mounts.at(window_.input.selected_pylon_name).ToString();
                }
            }
            std::string target_uid;
            if (reg.JSONType() == json::JSON::Class::Object && reg.hasKey("enemies_lock", json::JSON::Class::Array)) {
                for (const auto& enm : reg.at("enemies_lock").ArrayRange()) {
                    if (enm.JSONType() == json::JSON::Class::String) {
                        target_uid = enm.ToString();
                        if (!target_uid.empty()) break;
                    }
                }
            }
            if (!weapon_spec.empty() && !target_uid.empty()) {
                json::JSON fire_obj = json::JSON::Make(json::JSON::Class::Object);
                fire_obj["target_uid"] = json::String(target_uid);
                fire_obj["weapon_spec"] = json::String(weapon_spec);
                submit_action_json("fire", fire_obj);
                fire_emitted = true;
            }
        }
    }
    if (!fire_emitted) {
        submit_action_null("fire");
    }
    window_.input.fire_once_requested = false;
}

bool DX11Renderer::render_frame(const RendererFrameInput& frame_input, RendererFrameStats& out_stats) {
    UINT width = 1;
    UINT height = 1;
    update_viewport_from_client_rect(window_.hwnd, d3d11_.context, width, height);

    std::string error;
    if (!resize_swap_chain_if_needed(d3d11_, window_.hwnd, width, height, error)) {
        return false;
    }

    const RenderScene scene = build_render_scene(window_.input, width, height, frame_input.snapshot);
    RenderCommandList command_list = record_render_commands(scene);

    RenderFrameStats hud_stats;
    for (const auto& cmd : command_list.commands) {
        if (cmd.type == RenderCommandType::Draw && !cmd.vertices.empty()) {
            ++hud_stats.draw_calls;
            hud_stats.vertex_count += static_cast<long>(cmd.vertices.size());
        }
    }

    append_hud_render_commands(command_list, width, height, window_.input,
        frame_input.snapshot, frame_input.sim_time, frame_input.object_count, hud_stats);

    RenderFrameStats frame_stats;
    if (!execute_render_commands(d3d11_, command_list, frame_stats)) {
        return false;
    }

    out_stats.command_count = frame_stats.command_count;
    out_stats.draw_calls = frame_stats.draw_calls;
    out_stats.vertex_count = frame_stats.vertex_count;

    d3d11_.swap_chain->Present(1, 0);
    return true;
}

bool DX11Renderer::is_window_closed() const {
    return window_closed_;
}

#endif

} // namespace bvr_sim

std::unique_ptr<bvr_sim::IRenderer> bvr_sim::create_dx11_renderer() {
#ifdef _WIN32
    return std::make_unique<DX11Renderer>();
#else
    return nullptr;
#endif
}



