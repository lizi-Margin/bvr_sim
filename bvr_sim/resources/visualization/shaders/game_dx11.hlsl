cbuffer SceneConstants : register(b0) {
    row_major float4x4 u_world_view_proj;
    row_major float4x4 u_world;
    row_major float4x4 u_shadow_world_view_proj;
    float4 u_light_direction_ambient;
    float4 u_light_color_intensity;
    float4 u_material_flags;
    float4 u_camera_position_fog_start;
    float4 u_fog_color_density;
    float4 u_ambient_sky_ground;
    float4 u_material_tint;
    float4 u_shadow_params;
    float4 u_camera_forward_fov;
    float4 u_camera_right_aspect;
    float4 u_camera_up_pad;
};

Texture2D u_albedo_texture : register(t0);
Texture2D u_normal_texture : register(t1);
Texture2D u_roughness_texture : register(t2);
Texture2D u_metallic_texture : register(t3);
Texture2D u_shadow_texture : register(t4);
SamplerState u_albedo_sampler : register(s0);
SamplerComparisonState u_shadow_sampler : register(s1);

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
    float3 local_position : TEXCOORD2;
    float4 shadow_position : TEXCOORD3;
};

PSInput vs_main(VSInput input) {
    PSInput output;
    float4 world_position = mul(float4(input.position, 1.0), u_world);
    output.position = mul(float4(input.position, 1.0), u_world_view_proj);
    output.color = input.color;
    output.normal = normalize(mul(float4(input.normal, 0.0), u_world).xyz);
    output.world_position = world_position.xyz;
    output.uv = input.uv;
    output.local_position = input.position;
    output.shadow_position = mul(float4(input.position, 1.0), u_shadow_world_view_proj);
    return output;
}

float4 vs_shadow_main(VSInput input) : SV_POSITION {
    return mul(float4(input.position, 1.0), u_world_view_proj);
}

float terrain_noise(float2 p) {
    p *= 0.000055;
    float2 i = floor(p);
    float2 f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    float a = frac(sin(dot(i, float2(127.1, 311.7))) * 43758.5453);
    float b = frac(sin(dot(i + float2(1.0, 0.0), float2(127.1, 311.7))) * 43758.5453);
    float c = frac(sin(dot(i + float2(0.0, 1.0), float2(127.1, 311.7))) * 43758.5453);
    float d = frac(sin(dot(i + float2(1.0, 1.0), float2(127.1, 311.7))) * 43758.5453);
    return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
}

float terrain_fbm(float2 p) {
    float value = 0.0;
    float amp = 0.52;
    float norm = 0.0;
    float2 q = p;
    for (int i = 0; i < 5; ++i) {
        value += terrain_noise(q) * amp;
        norm += amp;
        q = q * 2.07 + float2(913.5, -271.9);
        amp *= 0.52;
    }
    return value / max(norm, 0.0001);
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

float aircraft_structure_occlusion(float3 local_position, float3 normal, float lit_amount) {
    float3 p = local_position;
    float span = abs(p.x);
    float length = abs(p.z);
    float height = abs(p.y);

    float belly = smoothstep(-0.03, -0.42, normal.y) * smoothstep(0.10, 1.20, height);
    float center_trench = 1.0 - smoothstep(0.32, 1.35, span);
    center_trench *= 1.0 - smoothstep(0.55, 2.20, height);
    center_trench *= 1.0 - smoothstep(4.00, 9.50, length);

    float wing_root = smoothstep(0.75, 2.10, span) * (1.0 - smoothstep(3.40, 6.70, span));
    wing_root *= 1.0 - smoothstep(0.34, 1.80, height);
    wing_root *= 1.0 - smoothstep(2.20, 7.20, length);

    float tail_root = smoothstep(5.10, 10.80, length) * (1.0 - smoothstep(0.24, 1.70, height));
    tail_root *= 1.0 - smoothstep(1.60, 4.80, span);

    float backlight = 1.0 - smoothstep(0.18, 0.82, lit_amount);
    float occlusion = wing_root * 0.58 + center_trench * 0.28 + tail_root * 0.38 + belly * 0.24;
    occlusion += backlight * (wing_root * 0.30 + tail_root * 0.18 + center_trench * 0.14);
    return saturate(occlusion);
}

float sample_shadow(float4 shadow_position, float receive_shadow) {
    if (u_shadow_params.x < 0.5 || receive_shadow < 0.5) {
        return 1.0;
    }

    float3 projected = shadow_position.xyz / max(0.0001, shadow_position.w);
    float2 uv = projected.xy * float2(0.5, -0.5) + float2(0.5, 0.5);
    if (uv.x <= 0.001 || uv.x >= 0.999 || uv.y <= 0.001 || uv.y >= 0.999 || projected.z <= 0.0 || projected.z >= 1.0) {
        return 1.0;
    }

    float bias = u_shadow_params.y;
    float2 texel = float2(1.0 / 2048.0, 1.0 / 2048.0);
    float shadow = 0.0;
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2(-1.0, -1.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 0.0, -1.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 1.0, -1.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2(-1.0,  0.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 0.0,  0.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 1.0,  0.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2(-1.0,  1.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 0.0,  1.0), projected.z - bias);
    shadow += u_shadow_texture.SampleCmpLevelZero(u_shadow_sampler, uv + texel * float2( 1.0,  1.0), projected.z - bias);
    return lerp(1.0 - u_shadow_params.z, 1.0, shadow / 9.0);
}

float4 ps_main(PSInput input) : SV_TARGET {
    float opacity = saturate(u_material_tint.y);
    if (u_material_flags.x < 0.5) {
        if (opacity > 0.95 && dot(input.color, input.color) > 0.05) {
            float2 p = input.local_position.xy;
            float3 sky_ray = normalize(
                u_camera_forward_fov.xyz +
                u_camera_right_aspect.xyz * (p.x * u_camera_right_aspect.w * u_camera_forward_fov.w) +
                u_camera_up_pad.xyz * (p.y * u_camera_forward_fov.w)
            );
            float horizon = saturate(sky_ray.y * 0.5 + 0.5);
            float3 zenith = float3(0.08, 0.25, 0.54);
            float3 mid_sky = float3(0.24, 0.48, 0.73);
            float3 haze = float3(0.82, 0.85, 0.78);
            float3 sunset = float3(0.98, 0.70, 0.38);
            float3 sun_dir = normalize(u_light_direction_ambient.xyz);
            float sun_dot = saturate(dot(sky_ray, sun_dir));
            float sun_glow = pow(sun_dot, 18.0);
            float sun_disc = smoothstep(0.9991, 0.9998, sun_dot);
            float low_haze = pow(1.0 - horizon, 2.8);
            float high_blend = smoothstep(0.18, 1.0, horizon);
            float3 sky = lerp(haze, mid_sky, high_blend);
            sky = lerp(sky, zenith, saturate((horizon - 0.62) * 1.9));
            sky += sunset * sun_glow * (0.55 + low_haze * 0.25);
            sky = lerp(sky, float3(1.0, 0.94, 0.68), sun_disc);
            float azimuth = atan2(sky_ray.z, sky_ray.x);
            float streak = sin(azimuth * 7.0 + sky_ray.y * 31.0) * 0.5 + 0.5;
            streak *= sin(azimuth * 3.2 - sky_ray.y * 17.0) * 0.5 + 0.5;
            float cloud_band = smoothstep(0.70, 0.91, streak) * smoothstep(0.06, 0.28, sky_ray.y) * (1.0 - smoothstep(0.58, 0.86, sky_ray.y));
            float low_cloud_noise = sin(azimuth * 13.0 + sky_ray.y * 46.0) * 0.5 + 0.5;
            low_cloud_noise *= sin(azimuth * 5.0 - sky_ray.y * 29.0 + 1.7) * 0.5 + 0.5;
            float low_clouds = smoothstep(0.48, 0.82, low_cloud_noise) * smoothstep(-0.02, 0.14, sky_ray.y) * (1.0 - smoothstep(0.26, 0.44, sky_ray.y));
            sky = lerp(sky, float3(0.86, 0.89, 0.88), saturate(cloud_band * 0.11 + low_clouds * 0.16));
            sky = max(sky, input.color * 0.72);
            return float4(saturate(sky), opacity);
        }
        return float4(saturate(input.color), opacity);
    }

    bool simple_material = (u_material_flags.z < 0.2 && u_material_flags.w < 30.0 && u_material_flags.y < 0.5);
    float3 texture_color = u_albedo_texture.Sample(u_albedo_sampler, input.uv).rgb;
    texture_color = max(texture_color, float3(0.18, 0.18, 0.18));
    float team_tint_strength = saturate(u_material_tint.x);
    float3 paint_color = lerp(float3(0.50, 0.54, 0.56), input.color, team_tint_strength * 0.72);
    float3 base_color = lerp(paint_color, texture_color * paint_color, 0.38);
    if (simple_material) {
        base_color = input.color;
    }
    if (u_material_flags.y > 0.5) {
        float2 terrain_position = input.world_position.xz * 20.0;
        float2 mask_uv = saturate(input.world_position.xz / 960000.0 + 0.5);
        float4 terrain_mask = u_albedo_texture.Sample(u_albedo_sampler, mask_uv);
        float road_mask = saturate(terrain_mask.r);
        float water_mask = saturate(terrain_mask.g);
        float village_mask = saturate(terrain_mask.b);
        float forest_mask = saturate(terrain_mask.a);
        float2 road_world = input.world_position.xz;
        float road_center_z = sin(road_world.x * 0.000075 + 1.2) * 18000.0
            + sin(road_world.x * 0.00019 + 0.4) * 5200.0;
        float road_center_x = sin(road_world.y * 0.000066 + 2.1) * 22000.0
            + sin(road_world.y * 0.00016 + 1.7) * 6200.0 + 64000.0;
        float diagonal_center_z = road_world.x * -0.34 + 112000.0
            + sin((road_world.x + road_world.y) * 0.000048) * 19000.0;
        float road_width_z = lerp(0.2, 0.5, saturate(sin(road_world.x * 0.00023 + 1.9) * 0.35 + sin(road_world.x * 0.000071 + 0.6) * 0.28 + 0.5));
        float road_width_x = lerp(0.2, 0.5, saturate(sin(road_world.y * 0.00021 + 3.1) * 0.35 + sin(road_world.y * 0.000069 + 1.4) * 0.28 + 0.5));
        float road_width_d = lerp(0.2, 0.5, saturate(sin((road_world.x + road_world.y) * 0.00019 + 2.4) * 0.35 + sin((road_world.x + road_world.y) * 0.000061) * 0.28 + 0.5));
        float shader_road = 1.0 - smoothstep(360.0 * road_width_z, 960.0 * road_width_z, abs(road_world.y - road_center_z));
        shader_road = max(shader_road, 1.0 - smoothstep(320.0 * road_width_x, 860.0 * road_width_x, abs(road_world.x - road_center_x)));
        shader_road = max(shader_road, (1.0 - smoothstep(280.0 * road_width_d, 760.0 * road_width_d, abs(road_world.y - diagonal_center_z))) * 0.82);
        road_mask = max(road_mask, shader_road * (1.0 - water_mask));
        float terrain = terrain_fbm(terrain_position * 0.42 + 7000.0);
        float macro = terrain_fbm(terrain_position * 0.13 + 17000.0);
        float biome = terrain_fbm(terrain_position * 0.045 - 42000.0);
        float height_blend = saturate((input.world_position.y + 180.0) / 980.0);
        float slope = saturate(1.0 - normalize(input.normal).y);
        float3 grass = float3(0.16, 0.28, 0.15);
        float3 forest = float3(0.06, 0.18, 0.08);
        float3 scrub = float3(0.34, 0.34, 0.20);
        float3 dry = float3(0.47, 0.43, 0.25);
        float3 rock = float3(0.38, 0.37, 0.32);
        base_color = lerp(grass, scrub, terrain);
        base_color = lerp(base_color, forest, smoothstep(0.58, 0.82, biome) * (1.0 - slope));
        base_color = lerp(base_color, forest * 0.82, forest_mask * (1.0 - slope) * 0.55);
        base_color = lerp(base_color, dry, macro * 0.22);
        base_color = lerp(base_color, rock, saturate(height_blend * 0.72 + slope * 0.45));
        base_color *= lerp(0.88, 1.12, terrain);
        base_color *= lerp(0.92, 1.08, terrain_fbm(terrain_position * 0.85 + 9000.0));
        float3 road_color = float3(0.39, 0.34, 0.22) * lerp(0.84, 1.12, terrain);
        float3 village_color = float3(0.43, 0.38, 0.30) * lerp(0.88, 1.10, macro);
        float3 water_color = float3(0.04, 0.18, 0.24) + float3(0.02, 0.07, 0.09) * terrain_fbm(terrain_position * 1.7 + 33000.0);
        base_color = lerp(base_color, village_color, village_mask * 0.82);
        base_color = lerp(base_color, road_color, road_mask);
        base_color = lerp(base_color, water_color, water_mask * 0.94);
    } else if (!simple_material) {
        float2 uv_panel_cell = abs(frac(input.uv * float2(18.0, 10.0)) - 0.5);
        float uv_panel_line = 1.0 - smoothstep(0.455, 0.5, max(uv_panel_cell.x, uv_panel_cell.y));
        float2 world_panel_cell = abs(frac(input.world_position.xz * 0.018) - 0.5);
        float world_panel_line = 1.0 - smoothstep(0.465, 0.5, max(world_panel_cell.x, world_panel_cell.y));
        float panel_line = max(uv_panel_line, world_panel_line);
        float uv_stripe = 1.0 - smoothstep(0.035, 0.070, abs(frac(input.uv.y * 3.0 + 0.12) - 0.5));
        float world_stripe = 1.0 - smoothstep(0.025, 0.055, abs(frac(input.world_position.x * 0.006 + 0.2) - 0.5));
        float stripe = max(uv_stripe, world_stripe);
        float worn = terrain_noise(input.world_position.xz * 0.35 + input.uv * 9000.0);
        float3 marking_color = lerp(float3(0.88, 0.91, 0.90), input.color, 0.82);
        base_color = lerp(base_color, base_color * 0.54, panel_line * 0.48);
        base_color = lerp(base_color, marking_color, stripe * team_tint_strength * 0.58);
        base_color *= lerp(0.88, 1.14, worn);
    }

    float3 normal = normalize(input.normal);
    if (u_material_flags.y > 0.5) {
        normal = normalize(lerp(float3(0.0, 1.0, 0.0), normal, 0.12));
    }
    float3 light_dir = normalize(u_light_direction_ambient.xyz);
    float ndotl = saturate(dot(normal, light_dir));
    float non_terrain_material = (u_material_flags.y < 0.5 && !simple_material) ? 1.0 : 0.0;
    normal = apply_normal_map(normal, input.world_position, input.uv, 0.0);
    float lit_amount = ndotl;
    float rim = pow(1.0 - saturate(dot(normal, normalize(u_camera_position_fog_start.xyz - input.world_position))), 2.2);

    float hemisphere = normal.y * 0.5 + 0.5;
    float ambient = lerp(u_ambient_sky_ground.y, u_ambient_sky_ground.x, hemisphere);
    ambient *= lerp(1.0, 0.72, non_terrain_material);
    float material_floor = (u_material_flags.y > 0.5) ? 0.48 : (simple_material ? 0.34 : 0.28);
    float3 diffuse = base_color * max(material_floor, ambient + lit_amount * u_light_color_intensity.w) * u_light_color_intensity.rgb;

    float3 view_dir = normalize(u_camera_position_fog_start.xyz - input.world_position);
    float3 half_dir = normalize(light_dir + view_dir);
    float roughness = saturate(u_roughness_texture.Sample(u_albedo_sampler, input.uv).r);
    float metallic = saturate(u_metallic_texture.Sample(u_albedo_sampler, input.uv).r);
    if (u_material_flags.y > 0.5) {
        roughness = 0.85;
        metallic = 0.0;
    } else if (simple_material) {
        roughness = 0.72;
        metallic = 0.0;
    } else {
        roughness = lerp(0.26, 0.66, roughness);
        metallic = max(metallic, 0.18);
    }
    float specular_strength = u_material_flags.z * lerp(0.55, 1.55, metallic);
    float specular_power = max(2.0, lerp(96.0, 12.0, roughness) + u_material_flags.w * 0.25);
    float specular = pow(saturate(dot(normal, half_dir)), specular_power) * specular_strength * (1.0 - roughness * 0.55);

    float shadow_floor = lerp(0.72, 0.38, non_terrain_material);
    float self_shadow = lerp(shadow_floor, 1.0, smoothstep(0.02, 0.86, lit_amount));
    float structure_shadow = aircraft_structure_occlusion(input.local_position, normal, lit_amount) * non_terrain_material;
    float cast_shadow = sample_shadow(input.shadow_position, u_material_tint.z);
    float3 sky_fill = base_color * (ambient * lerp(0.24, 0.10, non_terrain_material));
    float3 lit_color = diffuse * self_shadow * cast_shadow + sky_fill + specular * u_light_color_intensity.rgb * cast_shadow + base_color * rim * lerp(0.12, 0.06, non_terrain_material);
    lit_color *= lerp(1.0, 0.38, structure_shadow);
    float3 final_color = lerp(base_color, lit_color, saturate(u_material_flags.x));
    final_color = max(final_color, base_color * lerp(0.46, 0.24, non_terrain_material) + input.color * 0.04);

    float distance_to_camera = distance(u_camera_position_fog_start.xyz, input.world_position);
    float fog_distance = max(0.0, distance_to_camera - u_camera_position_fog_start.w);
    float fog_factor = saturate(1.0 - exp(-fog_distance * u_fog_color_density.w));
    final_color = lerp(final_color, u_fog_color_density.rgb, fog_factor);

    return float4(saturate(final_color), opacity);
}
