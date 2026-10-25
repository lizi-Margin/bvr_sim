"""Prepare opt-in direct64 visibility shading, preserving BVR material hooks."""
from pathlib import Path
import argparse,json,shutil,hashlib

def prepare(profile_path,output):
    profile_path=Path(profile_path).resolve();output=Path(output).resolve();output.mkdir(parents=True,exist_ok=False)
    profile=json.loads(profile_path.read_text(encoding='utf8'))
    if not profile.get('wide_primitive_id_raster'):raise ValueError('Requires the prepared direct64 indexed-raster profile')
    source=Path(profile['shader_source']);dest=output/'shader-source';shutil.copytree(source,dest)
    changes=[]
    def patch(name,old,new):
        path=dest/name;text=path.read_text(encoding='utf8')
        if text.count(old)!=1:raise ValueError('Pinned shader anchor changed: '+name+':'+old[:70])
        path.write_text(text.replace(old,new),encoding='utf8');changes.append(name)
    patch('globals.hlsli','''		materialIndex = 0;
		shaderType = 0;
		maybe_clustered = false;
	}

	inline uint3 tri()''','''		materialIndex = 0;
		shaderType = 0;
		maybe_clustered = false;
        // Direct IDs do not carry the meshlet material/shader shortcut.
        // Resolve the actual material before visibility material binning.
        if (instanceIndex < GetScene().instanceCount)
        {
            ShaderMeshInstance instance = load_instance(instanceIndex);
            uint geometry_index = instance.geometryOffset + subsetIndex;
            if (geometry_index < GetScene().geometryCount)
            {
                ShaderGeometry part = load_geometry(geometry_index);
                materialIndex = part.materialIndex;
                if (materialIndex < GetScene().materialCount)
                {
                    ShaderMaterial actual_material = load_material(materialIndex);
                    shaderType = actual_material.GetShaderType();
                }
            }
        }
	}

	inline uint3 tri()''')
    patch('surfaceHF.hlsli','''			half3 bitangent = cross(T.xyz, Nunnormalized) * T.w;''','''			half3 bitangent = cross(T.xyz, Nunnormalized) * T.w;
            if (material.userdata.x == 0x42565256u && is_backface)
                bitangent = -bitangent;''')
    for sampler in ['Grad(sam, uvsets, uvsets_dx, uvsets_dy)','Level(sam, uvsets, lod)']:
        old='bumpColor = half3(material.textures[NORMALMAP].Sample'+sampler+'.rg, 1);'
        new='''half4 source_normal_sample = material.textures[NORMALMAP].Sample'''+sampler+''';
                bumpColor = half3(source_normal_sample.rg, 1);
                if (material.userdata.x == 0x42565256u && material.userdata.y == 0x5247424eu)
                    bumpColor = source_normal_sample.rgb;'''
        patch('surfaceHF.hlsli',old,new)
    patch('surfaceHF.hlsli','''				baseColor *= baseColorMap;''','''
                if (material.userdata.x == 0x42565250u)
                {
                    // Raster maps the source texture before multiplying the
                    // interpolated material/instance/vertex color from its VS.
                    float luma = dot(baseColorMap.rgb, float3(0.2126, 0.7152, 0.0722));
                    float knee = asfloat(material.userdata.y);
                    float shoulder = asfloat(material.userdata.z);
                    float floor = asfloat(material.userdata.w);
                    float mapped = min(luma, knee) + shoulder * (1.0 - exp(-max(0.0, luma - knee) * 3.0));
                    baseColorMap.rgb *= mapped / max(luma, 0.00001);
                    baseColorMap.rgb += floor * exp(-luma / max(floor, 0.00001));
                }
                baseColor *= baseColorMap;
                if (material.userdata.x == 0x42565244u && material.textures[EMISSIVEMAP].IsValid())
                {
#ifdef SURFACE_LOAD_QUAD_DERIVATIVES
                    float3 detail = material.textures[EMISSIVEMAP].SampleGrad(sam, uvsets, uvsets_dx, uvsets_dy).rgb;
#else
                    float3 detail = material.textures[EMISSIVEMAP].SampleLevel(sam, uvsets, 0).rgb;
#endif
                    float value = dot(detail, float3(0.2126, 0.7152, 0.0722)) * asfloat(material.userdata.y);
                    baseColor.rgb *= lerp(1.0, clamp(value, 0.55, 1.45), asfloat(material.userdata.z));
                }''')
    cache=output/'shader-cache';cache.mkdir()
    if profile.get('aircraft_exhaust_profiles_file'):
        profile['aircraft_exhaust_profiles_file']=str((profile_path.parent/profile['aircraft_exhaust_profiles_file']).resolve())
    profile.update(shader_source=str(dest),shader_cache=str(cache),wide_visibility_compute_v1=True,visibility_compute_shading=True)
    (output/'visual-profile.json').write_text(json.dumps(profile,indent=2)+'\n',encoding='utf8')
    digest=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
    manifest={'schema_version':1,'source_profile':str(profile_path),'source_profile_sha256':digest(profile_path),
        'changed_files':[{'file':name,'sha256':digest(dest/name),'parent_sha256':digest(source/name)} for name in sorted(set(changes))],
        'scope':'Opt-in candidate: actual material-type binning for direct64 IDs and parity hooks for source RGB normals/backfaces,F22 paint and ground detail. No geometry or source resource changes; actual runtime comparison required.'}
    (output/'preparation.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
    return manifest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();print(json.dumps(prepare(a.profile,a.output),indent=2))
