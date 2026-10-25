"""Offline local ground repaint for an additive meadow-fragmentation policy.

Reuse the reviewed bundle outside the finite policy support; normal maps,
physical terrain and all unrelated color texels remain unchanged.
"""
from pathlib import Path
import argparse,copy,json,math,sys
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from shapely import from_wkb,contains_xy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.scene_runtime import BakedScene
from bvr_game.authored_canopy import woodland_mask,validate_policy
from bvr_game.source_woodland import protected_footprints
from bvr_game.source_macro import to_linear,to_srgb
from bvr_game.open_ground import OpenGround
from bvr_game.ground_color_mix import filtered_landcover
from game.tools.author_woodland_materials import geometry


def patch_rectangle(origin,size,pixels,bounds,transition):
    step=size/pixels;padding=math.ceil(3*transition/step)+2
    n0,w0,n1,w1=bounds
    x0=max(0,math.floor((n0-origin[0])/step)-padding);x1=min(pixels,math.ceil((n1-origin[0])/step)+padding)
    y0=max(0,math.floor((w0-origin[1])/step)-padding);y1=min(pixels,math.ceil((w1-origin[1])/step)+padding)
    return x0,y0,x1,y1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ['source','bundle','policy','output']:p.add_argument('--'+key,type=Path,required=True)
    a=p.parse_args();old=json.loads(a.bundle.read_text(encoding='utf8'));policy=json.loads(a.policy.read_text(encoding='utf8'));validate_policy(policy)
    if policy.get('parent_policy_sha256')!=old['biome_policy_sha256']:raise ValueError('New policy must identify the exact parent bundle policy')
    base={k:v for k,v in policy.items()if k not in ('meadow_fragmentation','scope','parent_policy_sha256')}
    prior={k:v for k,v in old['biome_policy'].items()if k not in ('scope','parent_policy_sha256')}
    if base!=prior or 'meadow_fragmentation' in old['biome_policy']:raise ValueError('Only a new local meadow fragmentation may differ')
    scene=BakedScene(a.source);doc=scene.document
    if geometry(doc)!=old['geometry']:raise ValueError('Source physical geometry changed')
    ground=OpenGround(Path(old['open_ground']['policy_file']))
    if ground.provenance['policy_sha256']!=old['open_ground']['policy_sha256']:raise ValueError('Ground source mixture changed')
    large=ASSETS/'registered'/old['large_asset']/'manifest.json'
    if sha(large)!=old['large_manifest_sha256']:raise ValueError('Source grove changed')
    forest_input=old['source_colors'][-1]
    if sha(forest_input['file'])!=forest_input['sha256']:raise ValueError('Original forest albedo changed')
    forest=to_linear(Image.open(forest_input['file']).convert('RGB'));radius=old['clearance_radius_m']
    forbidden=protected_footprints(dict(doc,instances=[i for i in doc['instances']if 'ground_stems'not in i]),
        from_wkb((a.source.parent/'water-footprint.wkb').read_bytes()),radius,
        shore_root_clearance_m=policy.get('shore_root_clearance_m'),road_root_clearance_m=policy.get('road_root_clearance_m'))
    a.output.mkdir(parents=True,exist_ok=False);result=copy.deepcopy(old);audits=[];changed_paths={}
    bounds=policy['meadow_fragmentation']['bounds_nw'];transition=old['forest_transition_m'];half=old['half_m']
    for name in ['source_macro','source_focus']:
        mat=result['materials'][name];source=Path(mat['base_color'])
        if sha(source)!=mat['base_color_sha256']:raise ValueError('Reviewed macro color changed')
        image=np.asarray(Image.open(source).convert('RGB'));height,width=image.shape[:2]
        if height!=width:raise ValueError('Square source macro required')
        origin=[mat['uv_origin_north'],mat['uv_origin_west']];size=mat['tile_m'];step=size/width
        x0,y0,x1,y1=patch_rectangle(origin,size,width,bounds,transition)
        if x1<=x0 or y1<=y0:continue
        n,w=np.meshgrid(origin[0]+(np.arange(x0,x1)+.5)*step,origin[1]+(np.arange(y0,y1)+.5)*step)
        mask=woodland_mask(n,w,policy)&(abs(n)<half)&(abs(w)<half)&~contains_xy(forbidden,n,w)
        coverage=filtered_landcover(mask,step,transition)
        u=np.mod(-w/2048,1)*forest.shape[1]-.5;v=np.mod(-n/2048,1)*forest.shape[0]-.5
        color=np.stack([map_coordinates(forest[...,c],[v,u],order=1,mode='grid-wrap',prefilter=False)for c in range(3)],axis=-1)
        original=image[y0:y1,x0:x1].copy();updated=to_srgb(color*coverage[...,None]+ground.color_linear(n,w)*(1-coverage[...,None]))
        # The filter support is contained inside this padded rectangle. Retain
        # its outermost border exactly, avoiding any finite-window seam.
        updated[[0,-1]]=original[[0,-1]];updated[:,[0,-1]]=original[:,[0,-1]]
        out=image.copy();out[y0:y1,x0:x1]=updated
        assert np.array_equal(out[:y0],image[:y0])and np.array_equal(out[y1:],image[y1:])
        assert np.array_equal(out[y0:y1,:x0],image[y0:y1,:x0])and np.array_equal(out[y0:y1,x1:],image[y0:y1,x1:])
        path=a.output/(name+'-local-meadow-patch.png');Image.fromarray(out).save(path)
        changed_paths[str(source)]=(str(path.resolve()),sha(path))
        audits.append({'material':name,'rectangle_xyxy':[x0,y0,x1,y1],'changed_texels':int(np.any(original!=updated,axis=2).sum()),
            'source_sha256':sha(source),'output_sha256':sha(path),'outside_rectangle_pixels_identical':True})
    for mat in result['materials'].values():
        if mat['base_color']in changed_paths:mat['base_color'],mat['base_color_sha256']=changed_paths[mat['base_color']]
    result.update(biome_policy=policy,biome_policy_sha256=sha(a.policy),biome_helper_sha256=sha(ROOT/'bvr_game/authored_canopy.py'),
        footprint_helper_sha256=sha(ROOT/'bvr_game/source_woodland.py'),tool_sha256=sha(__file__))
    result['local_patch']={'parent_bundle':str(a.bundle.resolve()),'parent_bundle_sha256':sha(a.bundle),'policy':str(a.policy.resolve()),
        'audits':audits,'scope':'Finite-support additive woodland policy only. Original source ground/forest colors and texture UVs; all other macro pixels retained exactly.'}
    write_json(a.output/'materials.json',result);print('LOCAL_MEADOW_GROUND_PATCHED',audits,flush=True)

if __name__=='__main__':main()
