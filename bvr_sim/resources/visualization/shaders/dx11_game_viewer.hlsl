cbuffer SceneConstants : register(b0) {
    row_major float4x4 u_world_view_proj;
    row_major float4x4 u_world;
    float4 u_light_direction_ambient;
    float4 u_light_color_intensity;
    float4 u_material_flags;
    float4 u_camera_position_fog_start;
    float4 u_fog_color_density;
    float4 u_ambient_sky_ground;
    float4 u_material_tint;
};

Texture2D u_albedo_texture : register(t0);
Texture2D u_normal_texture : register(t1);
Texture2D u_roughness_texture : register(t2);
Texture2D u_metallic_texture : register(t3);
SamplerState u_albedo_sampler : register(s0);

struct VSInput {
    float3 position : POSITION;
    float3 color : COLOR;
    float3 normal : NORMAL;
    float2 uv : TEXCOORD0;
};

struct PSInput {
    float4 position : SV_POSITION;
    float3 color : COLOR;
    float3 normal : NORMAL;
    float3 world_position : TEXCOORD0;
    float2 uv : TEXCOORD1;
};

PSInput vs_main(VSInput input) {
    PSInput output;
    float4 world_position = mul(float4(input.position, 1.0), u_world);
    output.position = mul(float4(input.position, 1.0), u_world_view_proj);
    output.color = input.color;
    output.normal = normalize(mul(float4(input.normal, 0.0), u_world).xyz);
    output.world_position = world_position.xyz;
    output.uv = input.uv;
    return output;
}

float terrain_noise(float2 p) {
    float n = sin(p.x * 0.00019 + p.y * 0.00031) * 0.5 + 0.5;
    n += (sin(p.x * 0.00073 - p.y * 0.00041) * 0.5 + 0.5) * 0.45;
    n += (sin((p.x + p.y) * 0.0017) * 0.5 + 0.5) * 0.18;
    return saturate(n / 1.63);
}

float3 apply_normal_map(float3 geometric_normal, float3 world_position, float2 uv, float normal_enabled) {
    if (normal_enabled < 0.5) {
        return geometric_normal;
    }

    float3 tangent_normal = u_normal_texture.Sample(u_albedo_sampler, uv).xyz * 2.0 - 1.0;
    float3 dp1 = ddx(world_position);
    float3 dp2 = ddy(world_position);
    float2 duv1 = ddx(uv);
    float2 duv2 = ddy(uv);
    float3 tangent = normalize(dp1 * duv2.y - dp2 * duv1.y);
    float3 bitangent = normalize(-dp1 * duv2.x + dp2 * duv1.x);

    if (dot(tangent, tangent) < 0.001 || dot(bitangent, bitangent) < 0.001) {
        return geometric_normal;
    }

    tangent = normalize(tangent - geometric_normal * dot(geometric_normal, tangent));
    bitangent = normalize(cross(geometric_normal, tangent));
    float3x3 tbn = float3x3(tangent, bitangent, geometric_normal);
    return normalize(mul(tangent_normal, tbn));
}

float4 ps_main(PSInput input) : SV_TARGET {
    if (u_material_flags.x < 0.5) {
        return float4(saturate(input.color), 1.0);
    }

    float3 texture_color = u_albedo_texture.Sample(u_albedo_sampler, input.uv).rgb;
    texture_color = max(texture_color, float3(0.18, 0.18, 0.18));
    float team_tint_strength = saturate(u_material_tint.x);
    float3 base_color = texture_color * lerp(float3(1.0, 1.0, 1.0), input.color, team_tint_strength);
    if (u_material_flags.y > 0.5) {
        base_color = input.color * texture_color;
        float terrain = terrain_noise(input.world_position.xz);
        float2 cell = abs(frac(input.uv * 64.0) - 0.5);
        float field_line = 1.0 - smoothstep(0.475, 0.5, max(cell.x, cell.y));
        base_color *= lerp(0.82, 1.22, terrain);
        base_color = lerp(base_color, base_color * 0.68, field_line * 0.18);
    }

    float3 normal = normalize(input.normal);
    normal = apply_normal_map(normal, input.world_position, input.uv, u_material_flags.y < 0.5 ? 1.0 : 0.0);
    float3 light_dir = normalize(u_light_direction_ambient.xyz);
    float ndotl = saturate(dot(normal, light_dir));

    float hemisphere = normal.y * 0.5 + 0.5;
    float ambient = lerp(u_ambient_sky_ground.y, u_ambient_sky_ground.x, hemisphere);
    float3 diffuse = base_color * max(0.22, ambient + ndotl * u_light_color_intensity.w) * u_light_color_intensity.rgb;

    float3 view_dir = normalize(u_camera_position_fog_start.xyz - input.world_position);
    float3 half_dir = normalize(light_dir + view_dir);
    float roughness = saturate(u_roughness_texture.Sample(u_albedo_sampler, input.uv).r);
    float metallic = saturate(u_metallic_texture.Sample(u_albedo_sampler, input.uv).r);
    if (u_material_flags.y > 0.5) {
        roughness = 0.85;
        metallic = 0.0;
    }
    float specular_strength = u_material_flags.z * lerp(0.55, 1.55, metallic);
    float specular_power = max(2.0, lerp(96.0, 12.0, roughness) + u_material_flags.w * 0.25);
    float specular = pow(saturate(dot(normal, half_dir)), specular_power) * specular_strength * (1.0 - roughness * 0.55);

    float3 lit_color = diffuse + specular * u_light_color_intensity.rgb;
    float3 final_color = lerp(base_color, lit_color, saturate(u_material_flags.x));
    final_color = max(final_color, input.color * 0.18);

    float distance_to_camera = distance(u_camera_position_fog_start.xyz, input.world_position);
    float fog_distance = max(0.0, distance_to_camera - u_camera_position_fog_start.w);
    float fog_factor = saturate(1.0 - exp(-fog_distance * u_fog_color_density.w));
    final_color = lerp(final_color, u_fog_color_density.rgb, fog_factor);

    return float4(saturate(final_color), 1.0);
}
