#include "game_dx11_internal.hxx"

#include <algorithm>
#include <cstring>
#include <string>

namespace bvr_sim {

#ifdef _WIN32

namespace {

constexpr UINT kShadowMapSize = 2048;

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

bool upload_shadow_constants(D3D11Context& d3d11, const RenderCommand& command) {
    D3D11_MAPPED_SUBRESOURCE mapped = {};
    HRESULT hr = d3d11.context->Map(d3d11.constant_buffer, 0, D3D11_MAP_WRITE_DISCARD, 0, &mapped);
    if (FAILED(hr)) {
        return false;
    }

    SceneConstants constants{};
    constants.world_view_proj = command.world_view_proj;
    constants.world = command.world;
    constants.shadow_world_view_proj = command.shadow_world_view_proj;
    std::memcpy(mapped.pData, &constants, sizeof(constants));
    d3d11.context->Unmap(d3d11.constant_buffer, 0);
    return true;
}

void bind_shadow_pipeline(D3D11Context& d3d11, D3D11_PRIMITIVE_TOPOLOGY topology) {
    UINT stride = sizeof(DX11Vertex);
    UINT offset = 0;
    d3d11.context->IASetVertexBuffers(0, 1, &d3d11.dynamic_vertex_buffer, &stride, &offset);
    d3d11.context->IASetInputLayout(d3d11.input_layout);
    d3d11.context->IASetPrimitiveTopology(topology);
    d3d11.context->VSSetShader(d3d11.shadow_vertex_shader, nullptr, 0);
    d3d11.context->PSSetShader(nullptr, nullptr, 0);
    d3d11.context->VSSetConstantBuffers(0, 1, &d3d11.constant_buffer);
    d3d11.context->RSSetState(d3d11.shadow_rasterizer_state ? d3d11.shadow_rasterizer_state : d3d11.rasterizer_state);
    d3d11.context->OMSetDepthStencilState(d3d11.depth_state, 0);
    d3d11.context->OMSetBlendState(nullptr, nullptr, 0xffffffff);
}

} // namespace

bool create_shadow_map_resources(D3D11Context& d3d11, std::string& error) {
    destroy_shadow_map_resources(d3d11);

    D3D11_TEXTURE2D_DESC texture_desc = {};
    texture_desc.Width = kShadowMapSize;
    texture_desc.Height = kShadowMapSize;
    texture_desc.MipLevels = 1;
    texture_desc.ArraySize = 1;
    texture_desc.Format = DXGI_FORMAT_R32_TYPELESS;
    texture_desc.SampleDesc.Count = 1;
    texture_desc.Usage = D3D11_USAGE_DEFAULT;
    texture_desc.BindFlags = D3D11_BIND_DEPTH_STENCIL | D3D11_BIND_SHADER_RESOURCE;

    HRESULT hr = d3d11.device->CreateTexture2D(&texture_desc, nullptr, &d3d11.shadow_texture);
    if (FAILED(hr) || !d3d11.shadow_texture) {
        error = "CreateTexture2D(shadow map) failed";
        return false;
    }

    D3D11_DEPTH_STENCIL_VIEW_DESC dsv_desc = {};
    dsv_desc.Format = DXGI_FORMAT_D32_FLOAT;
    dsv_desc.ViewDimension = D3D11_DSV_DIMENSION_TEXTURE2D;
    hr = d3d11.device->CreateDepthStencilView(d3d11.shadow_texture, &dsv_desc, &d3d11.shadow_dsv);
    if (FAILED(hr) || !d3d11.shadow_dsv) {
        error = "CreateDepthStencilView(shadow map) failed";
        return false;
    }

    D3D11_SHADER_RESOURCE_VIEW_DESC srv_desc = {};
    srv_desc.Format = DXGI_FORMAT_R32_FLOAT;
    srv_desc.ViewDimension = D3D11_SRV_DIMENSION_TEXTURE2D;
    srv_desc.Texture2D.MipLevels = 1;
    hr = d3d11.device->CreateShaderResourceView(d3d11.shadow_texture, &srv_desc, &d3d11.shadow_srv);
    if (FAILED(hr) || !d3d11.shadow_srv) {
        error = "CreateShaderResourceView(shadow map) failed";
        return false;
    }

    D3D11_SAMPLER_DESC sampler_desc = {};
    sampler_desc.Filter = D3D11_FILTER_COMPARISON_MIN_MAG_LINEAR_MIP_POINT;
    sampler_desc.AddressU = D3D11_TEXTURE_ADDRESS_BORDER;
    sampler_desc.AddressV = D3D11_TEXTURE_ADDRESS_BORDER;
    sampler_desc.AddressW = D3D11_TEXTURE_ADDRESS_BORDER;
    sampler_desc.BorderColor[0] = 1.0f;
    sampler_desc.BorderColor[1] = 1.0f;
    sampler_desc.BorderColor[2] = 1.0f;
    sampler_desc.BorderColor[3] = 1.0f;
    sampler_desc.ComparisonFunc = D3D11_COMPARISON_LESS_EQUAL;
    sampler_desc.MinLOD = 0.0f;
    sampler_desc.MaxLOD = D3D11_FLOAT32_MAX;
    hr = d3d11.device->CreateSamplerState(&sampler_desc, &d3d11.shadow_sampler);
    if (FAILED(hr) || !d3d11.shadow_sampler) {
        error = "CreateSamplerState(shadow map) failed";
        return false;
    }

    D3D11_RASTERIZER_DESC raster_desc = {};
    raster_desc.FillMode = D3D11_FILL_SOLID;
    raster_desc.CullMode = D3D11_CULL_NONE;
    raster_desc.DepthClipEnable = TRUE;
    raster_desc.DepthBias = 8;
    raster_desc.SlopeScaledDepthBias = 1.0f;
    hr = d3d11.device->CreateRasterizerState(&raster_desc, &d3d11.shadow_rasterizer_state);
    if (FAILED(hr) || !d3d11.shadow_rasterizer_state) {
        error = "CreateRasterizerState(shadow map) failed";
        return false;
    }

    return true;
}

void destroy_shadow_map_resources(D3D11Context& d3d11) {
    safe_release(d3d11.shadow_sampler);
    safe_release(d3d11.shadow_rasterizer_state);
    safe_release(d3d11.shadow_srv);
    safe_release(d3d11.shadow_dsv);
    safe_release(d3d11.shadow_texture);
}

bool render_shadow_map(D3D11Context& d3d11, const RenderCommandList& command_list) {
    if (!command_list.shadow_map_enabled || command_list.shadow_commands.empty() || !d3d11.shadow_dsv) {
        return true;
    }

    ID3D11ShaderResourceView* null_srv[1] = {nullptr};
    d3d11.context->PSSetShaderResources(4, 1, null_srv);
    d3d11.context->OMSetRenderTargets(0, nullptr, d3d11.shadow_dsv);
    d3d11.context->ClearDepthStencilView(d3d11.shadow_dsv, D3D11_CLEAR_DEPTH, 1.0f, 0);

    D3D11_VIEWPORT viewport = {};
    viewport.TopLeftX = 0.0f;
    viewport.TopLeftY = 0.0f;
    viewport.Width = static_cast<float>(kShadowMapSize);
    viewport.Height = static_cast<float>(kShadowMapSize);
    viewport.MinDepth = 0.0f;
    viewport.MaxDepth = 1.0f;
    d3d11.context->RSSetViewports(1, &viewport);

    for (const RenderCommand& command : command_list.shadow_commands) {
        if (command.vertices.empty()) {
            continue;
        }
        if (!upload_vertices(d3d11, command.vertices) || !upload_shadow_constants(d3d11, command)) {
            return false;
        }
        bind_shadow_pipeline(d3d11, command.topology);
        d3d11.context->Draw(static_cast<UINT>(command.vertices.size()), 0);
    }

    d3d11.common_pipeline_bound = false;
    d3d11.current_topology = D3D11_PRIMITIVE_TOPOLOGY_UNDEFINED;
    d3d11.current_depth_state = nullptr;
    d3d11.blend_enabled = false;
    d3d11.material_textures_bound = false;
    return true;
}

#endif

} // namespace bvr_sim
