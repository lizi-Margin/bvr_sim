"""Opt-in lighting basis for registered source-volume tree cards.

Source normals encode a volume projected onto a plane, rather than the normal
of a thin leaf. Reflect the depth component when viewing the back of that
plane, retaining the image's horizontal and vertical components. In particular
an upward-facing branch cannot become downward-facing solely because its
supporting card is viewed from behind. This remains an impostor approximation;
it cannot recover an unbaked view or actual opposite-side source geometry.
"""


def patch_source_card_basis(shader):
    anchor='\thalf3 bitangent = cross(surface.T.xyz, input.nor) * surface.T.w;'
    if shader.count(anchor)!=1:raise ValueError('Pinned object shader tangent basis changed')
    hook='''
    // A source tree volume projected onto a two-sided vertical card keeps its
    // upward tangent-normal component on the back. Mirror depth across the
    // card instead of turning its crowns toward the ground. Other materials
    // retain the engine's standard two-sided normal mapping.
#if !defined(PREPASS) && !defined(DEPTHONLY)
    if (material.userdata.x == 0x42565256u && !is_frontface)
        bitangent = -bitangent;
#endif
'''
    if hook in shader:raise ValueError('Source card basis already patched')
    return shader.replace(anchor,anchor+hook)


def patch_source_card_rgb_normals(shader):
    """Decode the original RGB vector only when the renderer preserved it.

    Averaged source normals are not unit length before normalization. Recovering
    Z from RG with sqrt(1-x*x-y*y) would invent a different mean direction.
    """
    anchor='\t\tsurface.bumpColor = half3(material.textures[NORMALMAP].Sample(sampler_objectshader, uvsets).rg, 1);'
    if shader.count(anchor)!=1:raise ValueError('Pinned object shader normal sample changed')
    return shader.replace(anchor,'''\t\thalf4 source_normal_sample = material.textures[NORMALMAP].Sample(sampler_objectshader, uvsets);
        surface.bumpColor = half3(source_normal_sample.rg, 1);
        // Explicit source-volume RGB texture, kept linear and uncompressed by
        // the renderer. All other normal maps retain the standard RG path.
        if (material.userdata.x == 0x42565256u && material.userdata.y == 0x5247424eu)
            surface.bumpColor = source_normal_sample.rgb;''')


def patch_source_tree_grounding(shader):
    """Use one source-anchor deformation in color, depth, and shadow passes."""
    include='#include "globals.hlsli"'
    anchor='\t\tposition = mul(inst.transform.GetMatrix(), position);'
    if shader.count(include)!=1 or shader.count(anchor)!=1:
        raise ValueError('Pinned object shader vertex transform changed')
    shader=shader.replace(include,include+'\n#include "bvrGroundHF.hlsli"')
    return shader.replace(anchor,anchor+'''
        // Every vertex in one source tree carries the same UV1 base anchor.
        // The shared function is also executed by the GPU readback inspector.
        float3 source_ground_base;
        position.xyz = BvrGroundPosition(material, inst, uvsets, position.xyz, source_ground_base);
''')


def patch_source_tree_surface_grounding(shader):
    """Keep visibility depth reconstruction and previous positions consistent.

    Registered static groves have upright, identity mesh nodes and constant
    UV1 on every tree/triangle. Their packed local Y scale is the matrix's
    vertical diagonal, including mesh position decompression. Moving roots,
    skinning, wind and previous-position streams are deliberately unsupported.
    """
    include='#include "globals.hlsli"'
    anchor='\t\tdata2 = buf[i2];'
    if shader.count(include)!=1 or shader.count(anchor)!=1:
        raise ValueError('Pinned surface shader triangle preload changed')
    shader=shader.replace(include,include+'\n#include "bvrGroundHF.hlsli"')
    return shader.replace(anchor,anchor+'''
        if (material.userdata.w == 0x47524e44u)
        {
            float4 source_uv = lerp(geometry.uv_range_min.xyxy, geometry.uv_range_max.xyxy,
                bindless_buffers_float4[MakeUniformResourceIndex(geometry.vb_uvs)][i0]);
            if (BvrGroundInactive(material, inst, source_uv)) return false;
            float3 packed_delta = BvrGroundPackedTranslation(material, inst, source_uv);
            // Both current triangle reconstruction and static previous
            // positions consume these values. Do not shift only the raster VS.
            data0.xyz += packed_delta;
            data1.xyz += packed_delta;
            data2.xyz += packed_delta;
        }
''')
