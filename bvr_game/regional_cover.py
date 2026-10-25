"""Seeded outer land-use appearance from registered source albedos.

Uses the existing Baker/material pipeline. No height, placement, collision or
mission edit; far land-use is an authored visual approximation, not GIS data.
"""
from pathlib import Path
import math
import numpy as np
from PIL import Image
from .content import ASSETS,sha
from .heightfield import sample_grid


def cell_noise(n,w,seed):
    x=np.asarray(n,dtype=np.int64);y=np.asarray(w,dtype=np.int64)
    h=(x*73856093+y*19349663+int(seed)*83492791)&0xffffffff
    h=((h^(h>>13))*1274126177)&0xffffffff
    return (h^(h>>16)).astype(np.float64)/4294967295.


def smooth_noise(n,w,scale,seed):
    u=n/scale;v=w/scale;x=np.floor(u).astype(np.int64);y=np.floor(v).astype(np.int64)
    a=u-x;b=v-y;a=a*a*(3-2*a);b=b*b*(3-2*b)
    return ((1-a)*cell_noise(x,y,seed)+a*cell_noise(x+1,y,seed))*(1-b)+((1-a)*cell_noise(x,y+1,seed)+a*cell_noise(x+1,y+1,seed))*b


def mean_albedo(material,sources):
    p=Path(material['base_color']);assert sha(p)==material['base_color_sha256'];sources[str(p)]=sha(p)
    image=np.asarray(Image.open(p).convert('RGB'),dtype=np.float32)/255
    linear=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
    return linear.mean(axis=(0,1))*np.asarray(material['color'][:3])


def bake_outer_cover(baker,document,arrays,out):
    cfg=baker.r['landscape'].get('outer_surface')
    if not cfg:return
    out=Path(out);meta=document['terrain']['base'];extent=[meta['spacing']*(meta['columns']-1),meta['spacing']*(meta['rows']-1)]
    resolution=int(cfg['resolution']);seed=baker.r['seed'];field=float(cfg['field_size_m']);forest_scale=float(cfg['forest_scale_m'])
    if not 256<=resolution<=8192 or not 200<=field<=2000 or not 1000<=forest_scale<=10000 or extent[0]!=extent[1]:raise ValueError('Invalid outer surface resolution/scale/extent')
    sources={};grass=mean_albedo(document['materials']['grass'],sources);soil=mean_albedo(document['materials']['farmland'],sources)
    rock=mean_albedo(document['materials']['rock'],sources)
    proxy=document['materials']['forest'].get('canopy_proxy');forest=mean_albedo(document['materials']['forest'],sources)
    woodland=baker.r['landscape'].get('reference_woodland')
    if woodland and not document['materials']['forest'].get('aerial_canopy_albedo'):
        file=woodland['crown_color_source_file'];assert sha(file)==woodland['crown_color_source_sha256'];sources[file]=sha(file)
        fraction=woodland['aerial_crown_color_fraction']
        forest=forest*(1-fraction)+np.asarray(woodland['crown_mean_linear'])*fraction
    if proxy:
        p=ASSETS/'registered'/proxy['asset']/'source_albedo_view_3.png';assert sha(p)==proxy['source_sha256'];sources[str(p)]=sha(p)
        image=np.asarray(Image.open(p).convert('RGBA'),dtype=np.float32)/255;a=image[...,3]
        rgb=np.where(image[...,:3]<=.04045,image[...,:3]/12.92,((image[...,:3]+.055)/1.055)**2.4)
        forest=(rgb*a[...,None]).sum(axis=(0,1))/max(a.sum(),1)
    color=np.empty((resolution,resolution,3),dtype=np.uint8);pixel=extent[0]/resolution
    photographic={}
    for name in ('grass','farmland','forest'):
        mat=document['materials'][name]
        if not mat.get('macro_tile_m'):continue
        file=mat['base_color'];assert sha(file)==mat['base_color_sha256'];sources[file]=sha(file)
        rgb=np.asarray(Image.open(file).convert('RGB'),dtype=np.float32)/255
        linear=np.where(rgb<=.04045,rgb/12.92,((rgb+.055)/1.055)**2.4)
        h,w0=linear.shape[:2];target=min(h,w0,2**math.ceil(math.log2(max(1,float(mat['macro_tile_m'])/pixel))))
        if h%target==0 and w0%target==0:linear=linear.reshape(target,h//target,target,w0//target,3).mean(axis=(1,3))
        photographic[name]=(linear,float(mat['macro_tile_m']),np.asarray(mat['color'][:3]))
    def surface(name,mean,n,w):
        if name not in photographic:return mean
        from scipy.ndimage import map_coordinates
        image,tile,tint=photographic[name]
        u=np.mod(n/tile+.08*np.sin(w/370),1)*image.shape[1]
        v=np.mod(w/tile+.08*np.cos(n/410),1)*image.shape[0]
        return np.stack([map_coordinates(image[...,i],[v,u],order=1,mode='grid-wrap') for i in range(3)],axis=2)*tint
    for row in range(0,resolution,128):
        stop=min(resolution,row+128)
        n,w=np.meshgrid(meta['origin_north']+(np.arange(resolution)+.5)*pixel,meta['origin_west']+(np.arange(row,stop)+.5)*pixel)
        warp_n=n+field*.23*np.sin(w/(field*2.1))+field*.16*np.sin((n+w)/(field*3.7))
        warp_w=w+field*.27*np.sin(n/(field*1.8))+field*.15*np.cos((n-w)/(field*4.1))
        parcel=cell_noise(np.floor(warp_n/field),np.floor(warp_w/field),seed+11)
        cover=.2+.8*cell_noise(np.floor(warp_n/field),np.floor(warp_w/field),seed+17)
        h=sample_grid(arrays['base'],meta,n,w)
        dn=(sample_grid(arrays['base'],meta,n+1000,w)-sample_grid(arrays['base'],meta,n-1000,w))/2000
        dw=(sample_grid(arrays['base'],meta,n,w+1000)-sample_grid(arrays['base'],meta,n,w-1000))/2000
        slope=np.hypot(dn,dw);distance=baker.distance_river(n,w)
        fields=(smooth_noise(n,w,forest_scale*1.4,seed+23)>.39)&(slope<.17)&(distance>180)&(h<700)
        wood=np.clip((smooth_noise(n,w,forest_scale,seed+31)-.43)*5+(h-450)/500,0,1)
        wood*=np.clip((distance-130)/250,0,1)
        ground=surface('grass',grass,n,w);woods=surface('forest',forest,n,w);bare=surface('farmland',soil,n,w)
        farmland=bare*(1-cover[...,None])+ground*cover[...,None]
        base=np.where(fields[...,None],farmland,ground)*(0.9+.2*parcel[...,None])
        if woodland:
            # The reference landscape is mostly woodland with irregular open
            # country. Avoid carrying the old square agricultural cells into
            # the distant hemisphere of the same map.
            wood=np.clip(.55+1.1*smooth_noise(n,w,forest_scale,seed+31),0,1)
            wood*=np.clip((distance-80)/180,0,1)
            base=ground*(.9+.15*smooth_noise(n,w,800,seed+17)[...,None])
        base=base*(1-wood[...,None])+woods*wood[...,None]
        stone=np.clip((slope-.28)*3+(h-950)/450,0,1)
        base=base*(1-stone[...,None])+rock*stone[...,None]
        base*=.92+.16*smooth_noise(n,w,14000,seed+41)[...,None]
        srgb=np.where(base<=.0031308,12.92*base,1.055*np.maximum(base,0)**(1/2.4)-.055)
        color[row:stop]=np.clip(srgb*255,0,255).astype(np.uint8)
    color_file=out/'outer_color.png';Image.fromarray(color).save(color_file)
    normal_file=out/'outer_normal.png';rough_file=out/'outer_roughness.png'
    Image.new('RGB',(2,2),(128,128,255)).save(normal_file);Image.new('RGB',(2,2),(235,235,235)).save(rough_file)
    document['materials']['outer_1']={'provider':'offline source-albedo land-use blend','id':'outer_continuous_cover','tile_m':extent[0],
        'color':[1,1,1,1],'roughness':.92,'base_color':str(color_file.resolve()),'base_color_sha256':sha(color_file),
        'normal':str(normal_file.resolve()),'normal_sha256':sha(normal_file),'roughness_map':str(rough_file.resolve()),'roughness_map_sha256':sha(rough_file),
        'world_uv':True,'uv_origin_north':meta['origin_north'],'uv_origin_west':meta['origin_west'],'repeat_detail':True,
        'license':'CC0 source albedos; authored land-use recipe follows project license','source_url':'derived:registered ambientCG/Poly Haven sources','source_files':sources}
    meta['material']='outer_1'
    local_sources=[m for m in document['materials'].values() if m.get('distribution_allowed') is False]
    if local_sources:document['materials']['outer_1'].update(license='user-local source material blend',distribution_allowed=False,
        source_url='derived:hash-pinned source textures',source_licenses=sorted({m['license'] for m in local_sources}))
    document['outer_surface']={**cfg,'seed':seed,'pixel_m':pixel,'extent_m':extent,'source_files':sources,
        'method':'Warped seeded parcels, continuous woodland/height/slope masks, linear-light source means, sRGB storage; no geometry or physical environmental edit',
        'normal_roughness_note':'Flat macro placeholders; runtime applies the same registered metre-scale normal/roughness detail as the focus tile',
        'provenance':'Authored land-use appearance, not measured agriculture, satellite imagery or GIS data'}
