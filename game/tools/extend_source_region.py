"""Build a larger shared terrain from mirrored retained source samples.

Original base/focus/sample heights remain bitwise identical. A four kilometre
transition outside the source rectangle meets the regional four kilometre grid.
This reuses a finite fictional source landscape; it adds no geographic survey.
"""
from pathlib import Path
import argparse,copy,hashlib,json,sys
import numpy as np
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.scene_runtime import BakedScene
from bvr_game.content import sha,write_json,ASSETS
from bvr_game.heightfield import sample_grid
from bvr_game.worldgen import deterministic_npz

def reflect(value,origin,span):
    phase=(np.asarray(value)-origin)%(2*span)
    return origin+np.where(phase<=span,phase,2*span-phase)

def region(source,meta,half=1024000,spacing=4000,band=4000):
    n0,w0=meta['origin_north'],meta['origin_west'];nspan=(meta['columns']-1)*meta['spacing'];wspan=(meta['rows']-1)*meta['spacing']
    assert -n0==nspan/2 and -w0==wspan/2 and half%spacing==0
    assert (nspan/2+band)%spacing==0 and (wspan/2+band)%spacing==0 and band%meta['spacing']==0
    outer={'origin_north':-half,'origin_west':-half,'spacing':spacing,'columns':2*half//spacing+1,'rows':2*half//spacing+1,'material':'source_far_macro'}
    n,w=np.meshgrid(-half+np.arange(outer['columns'])*spacing,-half+np.arange(outer['rows'])*spacing)
    base=sample_grid(source,meta,reflect(n,n0,nspan),reflect(w,w0,wspan)).astype(np.float32)
    tmeta={'origin_north':n0-band,'origin_west':w0-band,'spacing':meta['spacing'],'columns':meta['columns']+2*band//meta['spacing'],'rows':meta['rows']+2*band//meta['spacing'],'material':'source_far_macro','array_key':'regional_transition'}
    tile=np.empty((tmeta['rows'],tmeta['columns']),dtype=np.float32);north=tmeta['origin_north']+np.arange(tmeta['columns'])*tmeta['spacing']
    for first in range(0,tmeta['rows'],64):
        n,w=np.meshgrid(north,tmeta['origin_west']+np.arange(first,min(first+64,tmeta['rows']))*tmeta['spacing'])
        original=sample_grid(source,meta,reflect(n,n0,nspan),reflect(w,w0,wspan))
        t=np.clip(np.maximum(np.abs(n)-nspan/2,np.abs(w)-wspan/2)/band,0,1);t=t*t*(3-2*t)
        tile[first:first+len(w)]=(original*(1-t)+sample_grid(base,outer,n,w)*t).astype(np.float32)
    offset=int(band/meta['spacing']);tile[offset:offset+meta['rows'],offset:offset+meta['columns']]=source
    assert np.array_equal(tile[offset:offset+meta['rows'],offset:offset+meta['columns']],source)
    return base,outer,tile,tmeta

def macro(source,material,base_meta,extent,output,resolution=8192,authored_source=None):
    image=Image.open(source).convert('RGB');size=resolution;half=extent
    lo=base_meta['origin_north'];hi=lo+(base_meta['columns']-1)*base_meta['spacing'];span=hi-lo
    wlo=base_meta['origin_west'];whi=wlo+(base_meta['rows']-1)*base_meta['spacing'];wspan=whi-wlo
    def boundaries(origin,span):
        values=[-half,half];first=int(np.floor((-half-origin)/span))
        values.extend(origin+i*span for i in range(first,first+int(2*half/span)+3) if -half<origin+i*span<half)
        return sorted(set(values))
    ns=boundaries(lo,span);ws=boundaries(wlo,wspan);mesh=[]
    def pixel(n,w):
        n=float(reflect(n,lo,span));w=float(reflect(w,wlo,wspan))
        return ((n-material['uv_origin_north'])/material['tile_m']*image.width,(w-material['uv_origin_west'])/material['tile_m']*image.height)
    for n0,n1 in zip(ns,ns[1:]):
        for w0,w1 in zip(ws,ws[1:]):
            box=tuple(int(round((v+half)/(2*half)*size)) for v in [n0,w0,n1,w1])
            quad=(*pixel(n0,w0),*pixel(n0,w1),*pixel(n1,w1),*pixel(n1,w0));mesh.append((box,quad))
    result=image.transform((size,size),Image.Transform.MESH,mesh,resample=Image.Resampling.BILINEAR)
    if authored_source is not None:
        authored=Image.open(authored_source).convert('RGB');band=4000
        box=tuple(int(round((v+half)/(2*half)*size)) for v in [lo-band,wlo-band,hi+band,whi+band]);width=box[2]-box[0];height=box[3]-box[1]
        ns0=[lo-band,lo,hi,hi+band];ws0=[wlo-band,wlo,whi,whi+band];pieces=[]
        def authored_pixel(n,w):return ((np.clip(n,lo,hi)-material['uv_origin_north'])/material['tile_m']*authored.width,(np.clip(w,wlo,whi)-material['uv_origin_west'])/material['tile_m']*authored.height)
        for n0,n1 in zip(ns0,ns0[1:]):
            for w0,w1 in zip(ws0,ws0[1:]):
                patch=tuple(int(round((v-origin)/(span+2*band)*count)) for v,origin,span,count in [(n0,lo-band,span,width),(w0,wlo-band,wspan,height),(n1,lo-band,span,width),(w1,wlo-band,wspan,height)])
                pieces.append((patch,(*authored_pixel(n0,w0),*authored_pixel(n0,w1),*authored_pixel(n1,w1),*authored_pixel(n1,w0))))
        local=np.asarray(authored.transform((width,height),Image.Transform.MESH,pieces,resample=Image.Resampling.BILINEAR),dtype=float)/255
        far=np.asarray(result.crop(box),dtype=float)/255
        n,w=np.meshgrid(lo-band+(np.arange(width)+.5)*(span+2*band)/width,wlo-band+(np.arange(height)+.5)*(wspan+2*band)/height)
        t=np.clip(np.maximum(np.abs(n)-(hi-lo)/2,np.abs(w)-(whi-wlo)/2)/band,0,1);t=t*t*(3-2*t)
        linear=lambda x:np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
        value=linear(local)*(1-t[:,:,None])+linear(far)*t[:,:,None]
        value=np.where(value<=.0031308,value*12.92,1.055*np.maximum(value,0)**(1/2.4)-.055)
        result.paste(Image.fromarray(np.rint(np.clip(value,0,1)*255).astype(np.uint8)),box[:2])
    result.save(output)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--map',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--macro-report',type=Path,required=True);a=p.parse_args()
    output=a.output.resolve();output.mkdir(exist_ok=False,parents=True);scene=BakedScene(a.map);doc=scene.document;arrays=scene.arrays
    print('REGION_SOURCE_LOADED',flush=True);old_meta=copy.deepcopy(doc['terrain']['base']);old_source=arrays['base'];old_height_sha=doc['terrain']['sha256']
    base,meta,transition,tmeta=region(old_source,old_meta);arrays['retained_source_base']=old_source;arrays['regional_transition']=transition;arrays['base']=base
    retained={**old_meta,'array_key':'retained_source_base'};doc['terrain']['base']=meta;doc['terrain']['details']=[tmeta,retained,*doc['terrain']['details']]
    deterministic_npz(output/'terrain.npz',arrays);doc['terrain']['file']='terrain.npz';doc['terrain']['sha256']=sha(output/'terrain.npz')
    if 'ground_atlas' in doc['terrain']:
        atlas=doc['terrain']['ground_atlas'];atlas['file']=str((a.map.parent/atlas['file']).resolve());atlas['source_height_archive_sha256']=doc['terrain']['sha256']
    material=copy.deepcopy(doc['materials']['source_macro']);authored_macro=Path(material['base_color']);macro_report=json.loads(a.macro_report.read_text());source_macro=Path(macro_report['macro'])
    if sha(source_macro)!=macro_report['macro_sha256'] or macro_report['macro_sha256']!=doc['source_terrain_bake']['macro_sha256']:raise ValueError('Original source macro provenance mismatch')
    macro(source_macro,material,old_meta,1024000,output/'regional-macro.png',authored_source=authored_macro)
    material.pop('ground_detail',None);material.pop('repeat_detail',None)
    material.update(base_color=str(output/'regional-macro.png'),base_color_sha256=sha(output/'regional-macro.png'),tile_m=2048000,uv_origin_north=-1024000,uv_origin_west=-1024000,world_uv=True)
    doc['materials']['source_far_macro']=material
    cloud=doc.get('baked_environment',{}).get('profile',{}).get('cloud_weather_map')
    if cloud:cloud['file']=str((a.map.parent/cloud['file']).resolve())
    bridge=doc.get('source_bridge_mesh_binding')
    if bridge and bridge.get('source_deck'):bridge['source_deck']=str((a.map.parent/bridge['source_deck']).resolve())
    bridge=doc.get('source_road_bake',{}).get('bridge')
    if bridge and bridge.get('source_deck'):
        bridge['source_deck']=str((a.map.parent/bridge['source_deck']).resolve())
        if sha(bridge['source_deck'])!=bridge['source_deck_sha256']:raise ValueError('Original bridge deck provenance mismatch')
    report={'method':__doc__,'source_map_sha256':sha(a.map),'source_height_archive_sha256':old_height_sha,'source_macro_sha256':sha(source_macro),'authored_macro_sha256':sha(authored_macro),'tool_sha256':sha(__file__),'extent_km':[2048,2048],'original_base_heights_bitwise_unchanged':True,'original_focus_and_sample_arrays_unchanged':True,'regional_spacing_m':4000,'transition_band_m':4000,'scope':'Mirrored finite source landscape, not additional real-world elevation. Original mission area, tree positions and contact data retained.'}
    doc['name']='source_smolensk_regional_horizon_candidate';doc['regional_terrain_extension']=report
    doc['required_renderer_capabilities']=list(set(doc.get('required_renderer_capabilities',[])+['TERRAIN_CONTINUATION_V1']))
    recipe={'schema_version':1,'kind':'retained_source_regional_terrain','extension':report,'resource_use':{'mode':'local_private','asset_manifest_sha256':{asset:sha(ASSETS/'registered'/asset/'manifest.json') for asset in doc['resource_versions']}}}
    doc['recipe_sha256']=hashlib.sha256(json.dumps(recipe,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    write_json(output/'generated-map.json',doc);write_json(output/'extension-report.json',{**report,'map_sha256':sha(output/'generated-map.json')});write_json(output/'scene-recipe.json',recipe)
    print('REGION_COMPLETE',str(output/'generated-map.json'),flush=True)

if __name__=='__main__':main()
