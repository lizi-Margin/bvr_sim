"""Source-exact card mip0 and area-filtered, straight-alpha DDS sidecars."""
from pathlib import Path
import hashlib,io,json,shutil,struct
import numpy as np
from PIL import Image
from .content import ASSETS,sha,write_json


def source_mips(rgba,*,srgb,maximum_alpha=False):
    rgba=np.asarray(rgba,dtype=np.uint8)
    if rgba.ndim!=3 or rgba.shape[2]!=4 or any(s<1 or s&(s-1) for s in rgba.shape[:2]):raise ValueError('Power-of-two RGBA dimensions required')
    color=rgba[:,:,:3].astype(float)/255;alpha=rgba[:,:,3].astype(float)/255
    if srgb:color=np.where(color<=.04045,color/12.92,((color+.055)/1.055)**2.4)
    premult=color*alpha[:,:,None];max_alpha=alpha.copy();levels=[rgba.copy()];stats=[]
    while max(alpha.shape)>1:
        h,w=alpha.shape;fy=min(2,h);fx=min(2,w);shape=(h//fy,fy,w//fx,fx)
        alpha=alpha.reshape(shape).mean(axis=(1,3));premult=premult.reshape((*shape,3)).mean(axis=(1,3));max_alpha=max_alpha.reshape(shape).max(axis=(1,3))
        color=np.divide(premult,alpha[:,:,None],out=np.zeros_like(premult),where=alpha[:,:,None]>0)
        if srgb:color=np.where(color<=.0031308,color*12.92,1.055*np.maximum(color,0)**(1/2.4)-.055)
        output_alpha=max_alpha if maximum_alpha else alpha
        level=np.concatenate([color,output_alpha[:,:,None]],axis=2);levels.append(np.rint(np.clip(level,0,1)*255).astype(np.uint8))
    for index,level in enumerate(levels):
        a=level[:,:,3]/255;stats.append({'mip':index,'size':level.shape[0],'width':level.shape[1],'height':level.shape[0],'mean_alpha':float(a.mean()),'alpha_test_point4_coverage':float((a>=.4).mean())})
    return levels,stats


def dds_bytes(levels,*,srgb):
    if not levels or levels[-1].shape!=(1,1,4):raise ValueError('Complete RGBA mip chain required')
    height,width=levels[0].shape[:2]
    header=[124,0x2100f,height,width,width*4,0,len(levels)]+[0]*11+[32,4,0x30315844,0,0,0,0,0]+[0x401008,0,0,0,0]
    assert len(header)==31
    # DX10 RGBA8; source color uses an sRGB view, normal vectors stay linear.
    return b'DDS '+struct.pack('<31I',*header)+struct.pack('<5I',29 if srgb else 28,3,0,1,1)+b''.join(level.tobytes() for level in levels)


def derive(source_id,asset_id,*,maximum_alpha=False,crop_transparent=False):
    for name in [source_id,asset_id]:
        if not name.replace('_','').replace('-','').isalnum():raise ValueError('Invalid registered asset id')
    source=ASSETS/'registered'/source_id;out=ASSETS/'registered'/asset_id
    if out.exists():raise FileExistsError(out)
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    if manifest['license']!='CC0-1.0' or manifest.get('source_card_mips'):raise ValueError('Use an original registered CC0 source-card asset')
    out.mkdir(parents=True);mapping={};audit=[];crop_audits=[]
    for lod in manifest['lods']:
        path=source/lod['file']
        if sha(path)!=lod['sha256']:raise ValueError('Source GLB was changed')
        data=path.read_bytes()
        if crop_transparent:
            from .card_crop import crop_glb
            data,cropped=crop_glb(data);crop_audits.append({'file':lod['file'],**cropped});lod['sha256']=hashlib.sha256(data).hexdigest()
        (out/lod['file']).write_bytes(data);length=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+length]);blob=data[28+length:];materials={}
        for material in doc['materials']:
            name=material.get('name','')
            if not name.startswith('source_impostor_'):continue
            slots={}
            for slot,index in [('base_color',material['pbrMetallicRoughness']['baseColorTexture']['index']),('normal',material['normalTexture']['index'])]:
                view=doc['bufferViews'][doc['images'][doc['textures'][index]['source']]['bufferView']];start=view.get('byteOffset',0);png=blob[start:start+view['byteLength']]
                rgba=np.asarray(Image.open(io.BytesIO(png)).convert('RGBA'));srgb=slot=='base_color';levels,stats=source_mips(rgba,srgb=srgb,maximum_alpha=maximum_alpha and srgb)
                encoded=dds_bytes(levels,srgb=srgb);digest=hashlib.sha256(encoded).hexdigest();file=digest+'.dds';(out/file).write_bytes(encoded)
                slots[slot]={'file':file,'sha256':digest,'source_png_sha256':hashlib.sha256(png).hexdigest(),'mip0_rgba_sha256':hashlib.sha256(rgba.tobytes()).hexdigest(),'mip_levels':len(levels),'width':rgba.shape[1],'height':rgba.shape[0],'srgb':srgb}
                audit.append({'lod':lod['level'],'material':name,'slot':slot,'source_png_sha256':slots[slot]['source_png_sha256'],'mips':stats})
            materials[name]=slots
        if not materials:raise ValueError('Source has no explicitly marked source-card materials')
        mapping[lod['file']]=materials
    manifest.update(id=asset_id,name=manifest['name']+' / '+('cropped transparent source margins / ' if crop_transparent else '')+('maximum-alpha diagnostic control' if maximum_alpha else 'source-area mip filtering'))
    if crop_transparent:
        from . import card_crop
        manifest['glb_sha256']=manifest['lods'][0]['sha256']
        manifest['source_card_crop']={'schema_version':1,'source_asset':source_id,'source_manifest_sha256':sha(source/'manifest.json'),'converter_sha256':sha(card_crop.__file__),'lod_audits':crop_audits,
            'scope':'Exact original RGBA subrectangles, all nonzero albedo and normal alpha retained, no resampling. Quad/UV affine reparameterization preserves source pixel world locations. Tree poses, anchors, wood, faces and conservative bounds preserved. Oblique crossed-card shape limitations remain.'}
    manifest['source_card_mips']={'schema_version':1,'alpha_filter':'maximum_control' if maximum_alpha else 'area_mean','materials_by_lod_file':mapping,
        'source_asset':source_id,'source_manifest_sha256':sha(source/'manifest.json'),'converter_sha256':sha(__file__),
        'method':('Mip0 RGBA is an exact source subrectangle; quad/UV crop preserves source pixel spatial locations; ' if crop_transparent else 'Mip0 RGBA bytes and GLB bytes exact; ')+'linear-light alpha-weighted source RGB, arithmetic area-mean alpha. Normal vectors averaged in linear encoded space. Control differs only in albedo mip alpha, using descendant maximum.',
        'scope':'Area opacity for temporal/MSAA alpha coverage; hard alpha-test modes have different minification coverage. No painted colors or forced brightness.'}
    write_json(out/'manifest.json',manifest);write_json(out/'source-card-mip-audit.json',audit)
    return manifest
