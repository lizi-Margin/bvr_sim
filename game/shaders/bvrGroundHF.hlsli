#ifndef BVR_GROUND_HF
#define BVR_GROUND_HF
// R32 atlas rows are west, columns north. Use the core mesh's indexed
// triangles, not bilinear filtering (which represents a different surface).
float BvrGroundHeight(uint metadata_index, float2 north_west)
{
    ByteAddressBuffer metadata = bindless_buffers[descriptor_index(metadata_index)];
    uint4 header = metadata.Load4(0);
    float4 grid = asfloat(metadata.Load4(16));
    float2 uv = (north_west - grid.xy) / grid.z;
    if (any(uv < -0.001) || any(uv > float2(header.yz - 1) + 0.001))
        return asfloat(0x7fc00000u); // invalid coverage is visible to GPU diagnostics
    uv = clamp(uv, 0, float2(header.yz - 1));
    int2 cell = min(int2(floor(uv)), int2(header.yz) - 2);
    float2 f = uv - cell;
    Texture2D atlas = bindless_textures[descriptor_index(header.x)];
    float h00 = atlas.Load(int3(cell, 0)).r;
    float h10 = atlas.Load(int3(cell + int2(1, 0), 0)).r;
    float h01 = atlas.Load(int3(cell + int2(0, 1), 0)).r;
    float h11 = atlas.Load(int3(cell + 1, 0)).r;
    return f.x + f.y <= 1 ? h00 + f.x * (h10 - h00) + f.y * (h01 - h00)
        : h11 + (1 - f.x) * (h01 - h11) + (1 - f.y) * (h10 - h11);
}

float3 BvrGroundTranslation(ShaderMaterial material, ShaderMeshInstance inst, float4 uvsets, out float3 base)
{
    base = 0;
    if (material.userdata.w != 0x47524e44u)
        return 0;
    ByteAddressBuffer params = bindless_buffers[descriptor_index(material.userdata.z - 1)];
    uint atlas_metadata = params.Load(0);
    uint mode = params.Load(4);
    float2 xz;
    uint tree_index = 0;
    if (mode == 1)
    {
        uint count = params.Load(8);
        tree_index = min(uint(uvsets.z * count), count - 1);
        xz = asfloat(params.Load2(32 + tree_index * 8));
    }
    else
    {
        float4 range = asfloat(params.Load4(16));
        xz = range.xy + uvsets.zw * range.zw;
    }
    // transformRaw is essential: transform includes packed-position decoding,
    // whereas these source base anchors are already in physical mesh units.
    float3 source_base = mul(inst.transformRaw.GetMatrix(), float4(xz.x, 0, xz.y, 1)).xyz;
    base = source_base;
    if (mode == 1)
    {
        uint stream_srv_plus1 = bindless_buffers[descriptor_index(atlas_metadata)].Load(12);
        uint offset_plus1 = asuint(inst.padding.x);
        uint active_count = asuint(inst.padding.y);
        if (stream_srv_plus1 == 0 || offset_plus1 == 0 || active_count == 0)
        {
            base = asfloat(0x7fc00000u);
            return base;
        }
        uint lookup_index = tree_index < active_count ? tree_index : 0;
        float2 north_west = asfloat(bindless_buffers[descriptor_index(stream_srv_plus1 - 1)].Load2((offset_plus1 - 1 + lookup_index) * 8));
        base.xz = float2(-north_west.y, north_west.x);
    }
    base.y = BvrGroundHeight(atlas_metadata, float2(base.z, -base.x));
    return base - source_base;
}

bool BvrGroundInactive(ShaderMaterial material, ShaderMeshInstance inst, float4 uvsets)
{
    if (material.userdata.w != 0x47524e44u) return false;
    ByteAddressBuffer params = bindless_buffers[descriptor_index(material.userdata.z - 1)];
    return params.Load(4) == 1 && uint(uvsets.z * params.Load(8)) >= asuint(inst.padding.y);
}

float3 BvrGroundPosition(ShaderMaterial material, ShaderMeshInstance inst, float4 uvsets, float3 world, out float3 base)
{
    float3 translation = BvrGroundTranslation(material, inst, uvsets, base);
    // A short spatial batch keeps all its actual trees and collapses unused
    // source slots to one existing base point. Zero-area triangles cannot add
    // foliage/depth/shadows; no NaN clipping or hidden extra tree placements.
    return BvrGroundInactive(material, inst, uvsets) ? base : world + translation;
}

float3 BvrGroundPackedTranslation(ShaderMaterial material, ShaderMeshInstance inst, float4 uvsets)
{
    float3 base;
    float3 world = BvrGroundTranslation(material, inst, uvsets, base);
    // Upright static source nodes: solve the yaw/scale/position-decompression
    // matrix without a per-pixel general4x4inverse in visibility reconstruction.
    float a=inst.transform.mat0.x, b=inst.transform.mat0.z;
    float d=inst.transform.mat2.x, e=inst.transform.mat2.z;
    float determinant = a * e - b * d;
    return float3((e * world.x - b * world.z) / determinant,
        world.y / inst.transform.mat1.y, (a * world.z - d * world.x) / determinant);
}
#endif
