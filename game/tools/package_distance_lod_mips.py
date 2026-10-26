"""Package source-derived tree distance LODs with alpha-weighted mip filtering.

Near GLB and far GLB bytes remain exact. No brightness or coverage boost is used.
"""
from pathlib import Path
import argparse,copy,hashlib,io,json,shutil,struct,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
import numpy as np
from PIL import Image
from bvr_game.card_mips import source_mips,dds_bytes
from bvr_game.content import sha,write_json


def package(parent_path,output,asset_id):
    parent_path=Path(parent_path);output=Path(output)
    manifest=json.loads(parent_path.read_text(encoding='utf8'))
    if not manifest.get('source_distance_lod'):raise ValueError('A verified source-derived distance LOD is required')
    output.mkdir(parents=True,exist_ok=False)
    mapping={};audit=[]
    for lod in manifest['lods']:
        source=parent_path.parent/lod['file']
        if sha(source)!=lod['sha256']:raise ValueError('LOD source changed')
        shutil.copy2(source,output/lod['file'])
        data=source.read_bytes();length=struct.unpack_from('<I',data,12)[0]
        doc=json.loads(data[20:20+length]);blob=data[28+length:];materials={}
        for material in doc.get('materials',[]):
            name=material.get('name','')
            if not name.startswith('source_impostor_'):continue
            slots={}
            for slot,index in [('base_color',material['pbrMetallicRoughness']['baseColorTexture']['index']),('normal',material['normalTexture']['index'])]:
                view=doc['bufferViews'][doc['images'][doc['textures'][index]['source']]['bufferView']]
                first=view.get('byteOffset',0);png=blob[first:first+view['byteLength']]
                rgba=np.array(Image.open(io.BytesIO(png)).convert('RGBA'))
                levels,stats=source_mips(rgba,srgb=slot=='base_color')
                assert np.array_equal(levels[0],rgba)
                encoded=dds_bytes(levels,srgb=slot=='base_color');digest=hashlib.sha256(encoded).hexdigest()
                file=digest+'.dds';(output/file).write_bytes(encoded)
                slots[slot]={'file':file,'sha256':digest,'source_png_sha256':hashlib.sha256(png).hexdigest(),
                    'width':rgba.shape[1],'height':rgba.shape[0],'mip_levels':len(levels)}
                audit.append({'lod':lod['level'],'material':name,'slot':slot,'mip0_exact':True,'mips':stats})
            materials[name]=slots
        mapping[lod['file']]=materials
    if not any(mapping.values()):raise ValueError('No source distance cards found')
    manifest['id']=asset_id
    manifest['source_card_mips']={'schema_version':1,'alpha_filter':'area_mean','materials_by_lod_file':mapping,
        'source_manifest_sha256':sha(parent_path),'tool_sha256':sha(__file__),
        'method':'Exact source mip0, linear-light alpha-weighted RGB, area-mean opacity, linear encoded source normals. No forced brightness.'}
    write_json(output/'manifest.json',manifest);write_json(output/'mip-audit.json',audit)
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--id',required=True)
    args=parser.parse_args();package(args.parent,args.output,args.id)
