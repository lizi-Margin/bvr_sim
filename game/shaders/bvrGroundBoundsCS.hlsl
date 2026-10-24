#include "globals.hlsli"
struct GroundBoundsPush { uint input_srv, output_uav, count, instance_stride; uint center_offset, padding_offset, p1, p2; };
PUSHCONSTANT(update, GroundBoundsPush);
[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= update.count) return;
    ByteAddressBuffer source = bindless_buffers[descriptor_index(update.input_srv)];
    uint instance_index = source.Load(id.x * 32);
    uint4 sphere = source.Load4(id.x * 32 + 16);
    bindless_rwbuffers[descriptor_index(update.output_uav)].Store4(instance_index * update.instance_stride + update.center_offset, sphere);
    bindless_rwbuffers[descriptor_index(update.output_uav)].Store2(instance_index * update.instance_stride + update.padding_offset, source.Load2(id.x * 32 + 4));
}
