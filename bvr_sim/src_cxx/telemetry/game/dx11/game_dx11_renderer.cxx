#include "game_dx11_internal.hxx"
#include "resource_paths.hxx"

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
        constants.light_direction_ambient = {-0.40f, 0.82f, -0.40f, 0.40f};
        constants.light_color_intensity = {1.05f, 1.00f, 0.94f, 1.08f};
        const D3D11Context::MaterialResource* material = command.use_material_system ? find_material(d3d11, command.material_key) : nullptr;
        const bool terrain_material = material ? material->terrain : command.terrain_material;
        const float fog_start = material ? material->fog_start : 65000.0f;
        const float fog_density = material ? material->fog_density : (terrain_material ? 0.000022f : 0.000010f);
        const std::array<float, 3> fog_color = material ? material->fog_color : std::array<float, 3>{0.74f, 0.81f, 0.85f};
        const float team_tint_strength = command.use_material_system
            ? 0.0f
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
        constants.material_tint = {team_tint_strength, command.opacity, 0.0f, 0.0f};
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

    constexpr UINT terrain_size = 128;
    std::vector<std::uint32_t> terrain_pixels(terrain_size * terrain_size);
    for (UINT y = 0; y < terrain_size; ++y) {
        for (UINT x = 0; x < terrain_size; ++x) {
            const float fx = static_cast<float>(x);
            const float fy = static_cast<float>(y);
            float value = std::sin(fx * 0.27f + fy * 0.15f) * 0.5f + 0.5f;
            value += (std::sin(fx * 0.07f - fy * 0.31f) * 0.5f + 0.5f) * 0.45f;
            value += (std::sin((fx + fy) * 0.49f) * 0.5f + 0.5f) * 0.15f;
            value = std::max(0.0f, std::min(1.0f, value / 1.6f));
            const bool field_line = (x % 32 == 0) || (y % 32 == 0);
            const float r = field_line ? 0.52f : 0.68f + value * 0.22f;
            const float g = field_line ? 0.56f : 0.74f + value * 0.16f;
            const float b = field_line ? 0.42f : 0.50f + value * 0.12f;
            terrain_pixels[y * terrain_size + x] = pack_rgba8(r, g, b);
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
    safe_release(d3d11.depth_disabled_state);
    safe_release(d3d11.depth_readonly_state);
    safe_release(d3d11.depth_state);
    safe_release(d3d11.rasterizer_state);
    safe_release(d3d11.dynamic_vertex_buffer);
    safe_release(d3d11.constant_buffer);
    safe_release(d3d11.input_layout);
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
    ID3DBlob* ps_blob = nullptr;
    ID3DBlob* error_blob = nullptr;
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "vs_main", "vs_4_0", 0, 0, &vs_blob, &error_blob);
    if (FAILED(hr) || !vs_blob) {
        safe_release(error_blob);
        error = "D3DCompile(vs_main) failed";
        return false;
    }
    hr = D3DCompile(shader_source, std::strlen(shader_source), nullptr, nullptr, nullptr, "ps_main", "ps_4_0", 0, 0, &ps_blob, &error_blob);
    safe_release(error_blob);
    if (FAILED(hr) || !ps_blob) {
        safe_release(vs_blob);
        error = "D3DCompile(ps_main) failed";
        return false;
    }

    hr = d3d11.device->CreateVertexShader(vs_blob->GetBufferPointer(), vs_blob->GetBufferSize(), nullptr, &d3d11.vertex_shader);
    if (FAILED(hr) || !d3d11.vertex_shader) {
        safe_release(vs_blob);
        safe_release(ps_blob);
        error = "CreateVertexShader failed";
        return false;
    }
    hr = d3d11.device->CreatePixelShader(ps_blob->GetBufferPointer(), ps_blob->GetBufferSize(), nullptr, &d3d11.pixel_shader);
    if (FAILED(hr) || !d3d11.pixel_shader) {
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
    out_stats.command_count = static_cast<long>(command_list.commands.size());

    ID3D11RenderTargetView* render_targets[1] = {d3d11.rtv};
    d3d11.context->OMSetRenderTargets(1, render_targets, d3d11.dsv);

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

    return true;
}

#endif

} // namespace bvr_sim



