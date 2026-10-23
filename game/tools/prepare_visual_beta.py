"""Reproducible shader/profile preparation from the pinned engine and registered CC0 maps.

Does not modify the upstream checkout, aircraft geometry, terrain heights or source images.
"""
from pathlib import Path
import hashlib,json,shutil,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    runtime=json.loads((ROOT/'game/runtime.json').read_text());scene=json.loads((ROOT/'game/maps/training_range_v3/generated-map.json').read_text())
    cache=ROOT/'game/assets/cache/visual-beta';source=cache/'shader-source';binary=cache/'shaders'
    source.mkdir(parents=True,exist_ok=True);binary.mkdir(parents=True,exist_ok=True)
    engine=Path(runtime['engine_source']);shutil.copytree(engine/'WickedEngine/shaders',source,dirs_exist_ok=True)
    for p in Path(runtime['shader_cache']).rglob('*'):
        if p.is_file() and not p.name.lower().startswith('object'):
            dest=binary/p.relative_to(runtime['shader_cache']);dest.parent.mkdir(parents=True,exist_ok=True)
            if not dest.exists():shutil.copy2(p,dest)
    hf=source/'objectHF.hlsli';original=hf.read_text(encoding='utf8')
    anchor='surface.baseColor *= material.textures[BASECOLORMAP].Sample(sampler_objectshader, uvsets);'
    hook='''
#ifndef PREPASS
        // BVR optional macro + repeated detail albedo. Both color textures use
        // the engine's sRGB descriptors; normal/surface slots remain linear.
        // EMISSIVEMAP is a storage slot only here: material emission is zero.
        if (material.userdata.x == 0x42565244u && material.textures[EMISSIVEMAP].IsValid())
        {
            float3 detail = material.textures[EMISSIVEMAP].Sample(sampler_objectshader, uvsets).rgb;
            float value = dot(detail, float3(0.2126, 0.7152, 0.0722)) * asfloat(material.userdata.y);
            surface.baseColor.rgb *= lerp(1.0, clamp(value, 0.55, 1.45), asfloat(material.userdata.z));
        }
#endif
'''
    assert original.count(anchor)==1
    hf.write_text(original.replace(anchor,anchor+hook),encoding='utf8')
    (cache/'objectHF.patch.txt').write_text(hook,encoding='utf8')
    # The stock sky LUT intentionally omits the planet surface contribution.
    # Our finite 512 km training map can expose that black disc from 8.5 km.
    # Include the engine's Lambertian planet-albedo term beyond real geometry;
    # this changes background radiance only, never contact/collision terrain.
    sky_lut=source/'skyAtmosphere_skyViewLutCS.hlsl'
    text=sky_lut.read_text();assert text.count('const bool ground = false;')==1
    sky_lut.write_text(text.replace('const bool ground = false;','const bool ground = true;'))
    sky_hf=source/'skyHF.hlsli';sky_text=sky_hf.read_text()
    sky_anchor='\treturn totalColor;'
    sky_hook="""
    // Local NWU terrain is flat and finite, whereas the physical sky planet
    // curves away. Fill downward sky-only rays with the same integrated sky
    // luminance used by distant terrain fog. Real geometry is never masked.
    float localHorizonHaze = smoothstep(-0.015, 0.015, -worldDirection.y);
    if (!stationary)
    {
        float2 screenUV = pixelPosition * GetCamera().internal_resolution_rcp;
        float4 farAP = texture_cameravolumelut.SampleLevel(sampler_linear_clamp, float3(screenUV, 1.0), 0);
        float3 farHaze = farAP.rgb / max(farAP.a, 0.025);
        totalColor = lerp(totalColor, farHaze, localHorizonHaze);
    }
"""
    assert sky_text.count(sky_anchor)==1
    sky_hf.write_text(sky_text.replace(sky_anchor,sky_hook+sky_anchor))
    for pattern in ['skyPS*','envMap_skyPS*']:
        for cached in (binary/'hlsl6').glob(pattern):
            if cached.is_file():cached.unlink()
    # Copied shader metadata names upstream dependency paths. A source-path
    # change alone therefore does not invalidate its cached binary.
    for suffix in ['cso','wishadermeta']:
        (binary/'hlsl6'/('skyAtmosphere_skyViewLutCS.'+suffix)).unlink(missing_ok=True)
    soil=scene['materials']['soil'];rgb=np.array(Image.open(soil['base_color']).convert('RGB'),dtype=float)/255
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    mean=float((linear@np.array([.2126,.7152,.0722])).mean())
    profile={'schema_version':1,'name':'visual_agent_beta','engine_revision':runtime['engine_revision'],'shader_source':str(source),'shader_cache':str(binary),
             'physical_sky':True,'aerial_perspective':True,'high_quality_sky':False,'volumetric_clouds':False,'planet_albedo':[.12,.16,.10],'legacy_distance_fog_density':0.,'horizon_height_fog':{'start_m':100000,'density_per_m':.00005,'base_m':0,'top_m':16000,'approximation':'Distant aerosol haze shared by sky and geometry; no visibility culling change'},
             'sun_energy':4.,'sun_rotation':[-.65,-.6,0.],'ambient':[.075,.095,.13],'sky_exposure':1.,'exposure':1.,'saturation':1.,
             'paint_factor':.72,'paint_roughness':.64,'canopy_roughness':.09,'canopy_alpha':.48,'canopy_transmission':.12,
             'terrain_detail':{'base_color':soil['base_color'],'normal':soil['normal'],'roughness_map':soil['roughness_map'],'tile_m':3.,'mean_linear_luminance':mean,'strength':.7},
             'shader_patch':{'upstream_objectHF_sha256':sha(engine/'WickedEngine/shaders/objectHF.hlsli'),'patched_objectHF_sha256':sha(hf),'patched_sky_lut_sha256':sha(sky_lut),'patched_skyHF_sha256':sha(sky_hf),'flat_nwu_horizon_haze':'Downward sky-only rays use the same far aerial-perspective volume as opaque terrain; no geometry mask','planet_ground_radiance':True,'material_flag':'0x42565244','pipeline':'Existing forward raster path; visibility compute shading remains off'},
             'provenance':{'geometry':'Existing registered FlightGear geometry unchanged','material_parameters':'Engineering paint/glass/metal approximations based on source material names and roles, not measured BRDFs','detail_textures':'Existing registered ambientCG Ground072 CC0 source maps; images unchanged','detail_mean':'Computed from source color in linear sRGB to preserve macro mean brightness','shader_source':'Pinned Wicked Engine MIT source copied to cache; upstream checkout not edited'}}
    for key in ['base_color','normal','roughness_map']:profile['terrain_detail'][key+'_sha256']=sha(soil[key])
    path=ROOT/'game/recipes/visual_beta.json';path.write_text(json.dumps(profile,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'profile':str(path),'detail_mean_linear':mean,'shader_source':str(source),'upstream_checkout_edited':False},indent=2))
if __name__=='__main__':main()
