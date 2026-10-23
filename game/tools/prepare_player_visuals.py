"""Daylight variant from the pinned registered beta, without editing upstream."""
from pathlib import Path
import hashlib,json,shutil,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_changed(path,text):
    if not path.exists() or path.read_text(encoding='utf-8')!=text:path.write_text(text,encoding='utf-8')
def main():
    before=json.loads((ROOT/'game/recipes/visual_beta.json').read_text(encoding='utf-8'))
    cache=ROOT/'game/assets/cache/player-daylight';source=cache/'shader-source';binary=cache/'shaders'
    source.mkdir(parents=True,exist_ok=True);binary.mkdir(parents=True,exist_ok=True)
    for src,dest in [(Path(before['shader_source']),source),(Path(before['shader_cache']),binary)]:
        for p in src.rglob('*'):
            if p.is_file():
                d=dest/p.relative_to(src);d.parent.mkdir(parents=True,exist_ok=True)
                if not d.exists():shutil.copy2(p,d)
    sky_source=(Path(before['shader_source'])/'skyHF.hlsli').read_text(encoding='utf-8')
    start=sky_source.index('    // Local NWU terrain is flat and finite, whereas the physical sky planet')
    end=sky_source.index('\treturn totalColor;',start)
    sky_source=sky_source[:start]+sky_source[end:]
    anchor='bool intersectGround = RaySphereIntersectNearest(worldPosition, worldDirection, float3(0, 0, 0), atmosphere.bottomRadius) >= 0.0f;'
    hook='''
        // The finite flat NWU landscape has no curved planet ground disc.
        // Extend the physical sky LUT's last sky ray below the curved horizon,
        // instead of crossfading a screen-space fog color at worldDirection.y=0.
        // This changes background lookup only; real geometry/AP is untouched.
        if (!stationary)
        {
            float ratio = atmosphere.bottomRadius / viewHeight;
            float planetHorizon = -sqrt(saturate(1.0 - ratio * ratio));
            viewZenithCosAngle = max(viewZenithCosAngle, planetHorizon + 0.0002);
            intersectGround = false;
        }
'''
    assert sky_source.count(anchor)==1;sky_source=sky_source.replace(anchor,anchor+hook)
    sky=source/'skyHF.hlsli';changed=not sky.exists() or sky.read_text(encoding='utf-8')!=sky_source
    write_changed(sky,sky_source)
    if changed:
        for pattern in ['skyPS*','envMap_skyPS*']:
            for p in (binary/'hlsl6').glob(pattern):
                if p.is_file():p.unlink()
    scene=json.loads((ROOT/'game/maps/river_valley_airfield/generated-map.json').read_text(encoding='utf-8'));grass=scene['materials']['grass']
    rgb=np.asarray(Image.open(grass['base_color']).convert('RGB'),dtype=np.float64)/255
    linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
    mean=float((linear@np.array([.2126,.7152,.0722])).mean())
    profile={**before,'name':'player_daylight','shader_source':str(source),'shader_cache':str(binary),
        'sun_rotation':[-.4,-.65,0],'ambient':[.13,.14,.15],
        'exposure':1.,'sky_exposure':1.,'sun_energy':4.,'temporal_aa':True,'fxaa':False,
        'horizon_height_fog':{'enabled':False,'start_m':100000,'density_per_m':0.,'base_m':0,'top_m':16000,
            'approximation':'No additional height fog; retain actual physical aerial perspective'},
        'terrain_detail':{**before['terrain_detail'],'base_color':grass['base_color'],'normal':grass['normal'],'roughness_map':grass['roughness_map'],
            'tile_m':3.,'mean_linear_luminance':mean,'strength':.45}}
    for key in ['base_color','normal','roughness_map']:profile['terrain_detail'][key+'_sha256']=sha(grass[key])
    profile['shader_patch']={**before['shader_patch'],'patched_skyHF_sha256':sha(sky),
        'flat_nwu_horizon_haze':'Removed world-horizontal farAP crossfade. Nonstationary background lookup clamps to last physical sky ray above the curved planet horizon; geometry and AP remain actual.'}
    profile['provenance']={**before['provenance'],'detail_textures':'Existing registered CC0 grass color/normal/roughness; exact unchanged source hashes',
        'daylight':'Same exposure1/sun energy4/ACES; higher sun elevation and neutralized ambient after inspecting local+Y sun-direction transform',
        'anti_aliasing':'Pinned engine temporalAA was disabled; explicit TAA candidate replaces FXAA, subject to actual motion/ghosting review'}
    write_changed(ROOT/'game/recipes/player_daylight.json',json.dumps(profile,indent=2)+'\n')
    print(json.dumps({'profile':str(ROOT/'game/recipes/player_daylight.json'),'shader_changed':changed,'source_sha256':sha(sky)},indent=2))
if __name__=='__main__':main()
