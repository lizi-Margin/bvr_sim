#include "dx11_game_viewer_internal.hxx"

#include <algorithm>
#include <cstring>
#include <string>
#include <vector>

#ifdef _WIN32
#include <d3dcompiler.h>
#pragma comment(lib, "d3d11.lib")
#pragma comment(lib, "dxgi.lib")
#pragma comment(lib, "d3dcompiler.lib")
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
        vb_desc.ByteWidth = d3d11.dynamic_vertex_capacity * sizeof(Vertex);
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

bool upload_vertices(D3D11Context& d3d11, const std::vector<Vertex>& vertices) {
    if (!ensure_dynamic_vertex_buffer(d3d11, static_cast<UINT>(vertices.size()))) {
        return false;
    }
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.dynamic_vertex_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (FAILED(hr)) {
        return false;
    }
    std::memcpy(mapped.pData, vertices.data(), vertices.size() * sizeof(Vertex));
    d3d11.context->Unmap(d3d11.dynamic_vertex_buffer, 0);
    return true;
}

bool upload_scene_constants(D3D11Context& d3d11, const Float4x4& world_view_proj) {
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.constant_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (SUCCEEDED(hr)) {
        SceneConstants constants{};
        constants.world_view_proj = world_view_proj;
        std::memcpy(mapped.pData, &constants, sizeof(constants));
        d3d11.context->Unmap(d3d11.constant_buffer, 0);
    } else {
        return false;
    }
    return true;
}

void bind_draw_state(D3D11Context& d3d11, D3D11_PRIMITIVE_TOPOLOGY topology, bool depth_enabled) {
    UINT stride = sizeof(Vertex);
    UINT offset = 0;
    if (!d3d11.common_pipeline_bound) {
        d3d11.context->IASetVertexBuffers(0, 1, &d3d11.dynamic_vertex_buffer, &stride, &offset);
        d3d11.context->VSSetShader(d3d11.vertex_shader, nullptr, 0);
        d3d11.context->PSSetShader(d3d11.pixel_shader, nullptr, 0);
        d3d11.context->VSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
        d3d11.context->IASetInputLayout(d3d11.input_layout);
        d3d11.context->RSSetState(d3d11.rasterizer_state);
        d3d11.common_pipeline_bound = true;
    }
    if (d3d11.current_topology != topology) {
        d3d11.context->IASetPrimitiveTopology(topology);
        d3d11.current_topology = topology;
    }
    ID3D11DepthStencilState* depth_state = depth_enabled ? d3d11.depth_state : d3d11.depth_disabled_state;
    if (d3d11.current_depth_state != depth_state) {
        d3d11.context->OMSetDepthStencilState(depth_state, 0);
        d3d11.current_depth_state = depth_state;
    }
}

bool upload_and_draw(
    D3D11Context& d3d11,
    const std::vector<Vertex>& vertices,
    D3D11_PRIMITIVE_TOPOLOGY topology,
    const Float4x4& world_view_proj,
    bool depth_enabled,
    RenderFrameStats& stats) {
    if (vertices.empty()) {
        return true;
    }
    if (!upload_vertices(d3d11, vertices) || !upload_scene_constants(d3d11, world_view_proj)) {
        return false;
    }
    bind_draw_state(d3d11, topology, depth_enabled);
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

} // namespace

void destroy_d3d11(D3D11Context& d3d11) {
    safe_release(d3d11.depth_disabled_state);
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

    const char* shader_source =
        "cbuffer SceneConstants : register(b0) {\n"
        "    float4x4 u_world_view_proj;\n"
        "};\n"
        "struct VSInput {\n"
        "    float3 position : POSITION;\n"
        "    float3 color : COLOR;\n"
        "};\n"
        "struct PSInput {\n"
        "    float4 position : SV_POSITION;\n"
        "    float3 color : COLOR;\n"
        "};\n"
        "PSInput vs_main(VSInput input) {\n"
        "    PSInput output;\n"
        "    output.position = mul(float4(input.position, 1.0), u_world_view_proj);\n"
        "    output.color = input.color;\n"
        "    return output;\n"
        "}\n"
        "float4 ps_main(PSInput input) : SV_TARGET {\n"
        "    return float4(input.color, 1.0);\n"
        "}\n";

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
        {"POSITION", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(Vertex, position)), D3D11_INPUT_PER_VERTEX_DATA, 0},
        {"COLOR", 0, DXGI_FORMAT_R32G32B32_FLOAT, 0, static_cast<UINT>(offsetof(Vertex, color)), D3D11_INPUT_PER_VERTEX_DATA, 0},
    };
    hr = d3d11.device->CreateInputLayout(
        input_layout_desc,
        2,
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

    D3D11_DEPTH_STENCIL_DESC depth_disabled_desc = {};
    depth_disabled_desc.DepthEnable = FALSE;
    depth_disabled_desc.DepthWriteMask = D3D11_DEPTH_WRITE_MASK_ZERO;
    depth_disabled_desc.DepthFunc = D3D11_COMPARISON_ALWAYS;
    hr = d3d11.device->CreateDepthStencilState(&depth_disabled_desc, &d3d11.depth_disabled_state);
    if (FAILED(hr) || !d3d11.depth_disabled_state) {
        error = "CreateDepthStencilState(depth_disabled) failed";
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

        if (!upload_and_draw(d3d11, command.vertices, command.topology, command.world_view_proj, command.depth_enabled, out_stats)) {
            return false;
        }
    }

    return true;
}

#endif

} // namespace bvr_sim
