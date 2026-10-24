#include "globals.hlsli"
#include "bvrGroundHF.hlsli"
struct GroundQueryPush { uint input_srv, output_uav, count, atlas_metadata; };
PUSHCONSTANT(query, GroundQueryPush);
[numthreads(64, 1, 1)]
void main(uint3 id : SV_DispatchThreadID)
{
    if (id.x >= query.count) return;
    float2 nw = asfloat(bindless_buffers[descriptor_index(query.input_srv)].Load2(id.x * 8));
    float h = BvrGroundHeight(query.atlas_metadata, nw);
    bindless_rwbuffers[descriptor_index(query.output_uav)].Store(id.x * 4, asuint(h));
}
