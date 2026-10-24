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
