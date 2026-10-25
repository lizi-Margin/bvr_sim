"""Offline linear-light mixture of two hash-checked baked ground albedos."""
import numpy as np

def filtered_landcover(mask,pixel_m,transition_m):
    """Prefilter ground-color coverage only;the planting mask is never changed."""
    from scipy.ndimage import gaussian_filter
    if not np.isfinite([pixel_m,transition_m]).all() or pixel_m<=0 or not 0<=transition_m<=100:
        raise ValueError('Invalid ground-color transition distance')
    result=np.asarray(mask,dtype=np.float32).copy()
    if transition_m:gaussian_filter(result,transition_m/pixel_m,output=result,mode='nearest',truncate=3)
    return result


def linear_ground_mix(green,dry,fraction):
    a=np.asarray(green,dtype=np.float32)/255;b=np.asarray(dry,dtype=np.float32)/255
    a=np.where(a<=.04045,a/12.92,((a+.055)/1.055)**2.4)
    b=np.where(b<=.04045,b/12.92,((b+.055)/1.055)**2.4)
    value=a*(1-fraction[...,None])+b*fraction[...,None]
    encoded=np.where(value<=.0031308,value*12.92,1.055*np.maximum(value,0)**(1/2.4)-.055)
    return np.clip(np.rint(encoded*255),0,255).astype(np.uint8)


def mix_ground_images(source,appearance,output,document,material_id,seed=164):
    from PIL import Image
    from .content import sha
    from .regional_cover import smooth_noise
    a=np.asarray(Image.open(source).convert('RGB'));b=np.asarray(Image.open(appearance).convert('RGB'))
    if a.shape!=b.shape:raise ValueError('Ground mixture requires identical baked texture dimensions')
    material=document['materials'][material_id];tile=float(material['tile_m'])
    meta=document['terrain']['base'] if material_id==document['terrain']['base']['material'] else document['terrain']['details'][0]
    origin_n=material.get('uv_origin_north',meta['origin_north']);origin_w=material.get('uv_origin_west',meta['origin_west'])
    height,width=a.shape[:2];result=np.empty_like(a)
    north=origin_n+(np.arange(width)+.5)*tile/width
    for first in range(0,height,128):
        stop=min(first+128,height);n,w=np.meshgrid(north,origin_w+(np.arange(first,stop)+.5)*tile/height)
        fraction=.25+.45*(.8*smooth_noise(n,w,600,seed)+.2*smooth_noise(n,w,90,seed+11))
        result[first:stop]=linear_ground_mix(a[first:stop],b[first:stop],fraction)
    Image.fromarray(result).save(output)
    return {'source_file':str(source),'source_sha256':sha(source),'dry_file':str(appearance),'dry_sha256':sha(appearance),
            'result_file':str(output),'result_sha256':sha(output),'seed':seed,'dry_fraction_range':[.25,.7],
            'scope':'Authored spatial albedo mixture in linear light. Existing normal/roughness retained from dry bake;not measured vegetation or BRDF.'}
