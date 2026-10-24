#include "globals.hlsli"
#include "bvrGroundHF.hlsli"
struct GroundVertexPush {
    uint input_srv, output_uav, count, instance_srv;
    uint geometry_srv, material_srv, padding0, padding1;
};
PUSHCONSTANT(query, GroundVertexPush);
[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= query.count) return;
    uint4 item = bindless_buffers[descriptor_index(query.input_srv)].Load4(id.x * 16);
    ShaderMeshInstance inst = bindless_structured_meshinstance[descriptor_index(query.instance_srv)][item.x];
    ShaderGeometry geo = bindless_structured_geometry[descriptor_index(query.geometry_srv)][item.y];
    ShaderMaterial material = bindless_structured_material[descriptor_index(query.material_srv)][geo.materialIndex];
    float3 position = bindless_buffers_float4[descriptor_index(geo.vb_pos_wind)][item.z].xyz;
    float4 uv = lerp(geo.uv_range_min.xyxy, geo.uv_range_max.xyxy,
        bindless_buffers_float4[descriptor_index(geo.vb_uvs)][item.z]);
    float3 world = mul(inst.transform.GetMatrix(), float4(position, 1)).xyz;
    float3 base;
    world = BvrGroundPosition(material, inst, uv, world, base);
    bool inactive = BvrGroundInactive(material, inst, uv);
    float3 packed_shifted = position;
    packed_shifted += BvrGroundPackedTranslation(material, inst, uv);
    float3 surface_position = mul(inst.transform.GetMatrix(), float4(packed_shifted, 1)).xyz;
    float3 previous_position = mul(inst.transformPrev.GetMatrix(), float4(packed_shifted, 1)).xyz;
    if (inactive) { surface_position = base; previous_position = base; }
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store4(id.x * 80, asuint(float4(world, inactive ? 0 : 1)));
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store4(id.x * 80 + 16, asuint(float4(base, 1)));
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store4(id.x * 80 + 32, asuint(float4(surface_position, 1)));
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store4(id.x * 80 + 48, asuint(float4(previous_position, 1)));
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store4(id.x * 80 + 64, asuint(float4(inst.center, inst.radius)));
}
