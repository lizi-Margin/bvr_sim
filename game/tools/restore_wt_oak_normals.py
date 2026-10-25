"""Restore original packed oak normals by exact source OBJ vertex indices."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import sha,write_json

def restore(source,payload,output):
    lines=source.read_text(encoding='utf8').splitlines()
    original_positions=np.array([[float(x) for x in line.split()[1:4]] for line in lines if line.startswith('v ')])
    original_uv=np.array([[float(x) for x in line.split()[1:3]] for line in lines if line.startswith('vt ')])
    arrays=np.load(payload);positions=[];uvs=[];normals=[];blocks=set()
    for key in arrays.files:
        data=arrays[key];identity=hashlib.sha256(data.tobytes()).hexdigest()
        if identity in blocks:continue
        blocks.add(identity)
        if data.shape[1] not in (24,36):raise ValueError('Only verified oak FLOAT3/packed normal/FLOAT2 layouts supported')
        p=data[:,:12].copy().view('<f4').reshape(-1,3);p[:,2]*=-1;positions.append(p)
        uv=data[:,16:24].copy().view('<f4').reshape(-1,2);uv[:,1]*=-1;uvs.append(uv)
        n=data[:,[14,13,12]].astype(float)/127.5-1;n[:,2]*=-1;n/=np.linalg.norm(n,axis=1)[:,None];normals.append(n)
    positions=np.concatenate(positions);uvs=np.concatenate(uvs);normals=np.concatenate(normals)
    if len(positions)!=len(original_positions) or len(uvs)!=len(original_uv):raise ValueError('Source vertex/UV count differs from original OBJ')
    error=float(np.linalg.norm(positions-original_positions,axis=1).max());uv_error=float(np.linalg.norm(uvs-original_uv,axis=1).max())
    if error>.00012 or uv_error>.00015:raise ValueError('Source vertex/UV order mismatch: '+str((error,uv_error)))
    count=0;result=[]
    for line in lines:
        if line.startswith('vn '):line='vn '+' '.join(format(float(v),'.9g') for v in normals[count]);count+=1
        result.append(line)
    if count!=len(normals):raise ValueError('Normal indexing is not one-to-one with source vertices')
    assert [s for s in result if not s.startswith('vn ')]==[s for s in lines if not s.startswith('vn ')]
    output.write_text('\n'.join(result)+'\n',encoding='utf8');shutil.copy2(source.with_suffix('.mtl'),output.with_suffix('.mtl'))
    pack=json.loads((payload.parent/'report.json').read_text(encoding='utf8'))
    if sha(pack['source'])!=pack['source_sha256']:raise ValueError('Original source pack changed')
    return {'name':source.stem.removesuffix('_0'),'status':'exported','lod':0,'obj':str(output.resolve()),'obj_sha256':sha(output),
        'pack':pack['source'],'pack_sha256':pack['source_sha256'],
        'mtl':str(output.with_suffix('.mtl').resolve()),'mtl_sha256':sha(output.with_suffix('.mtl')),
        'vertices':len(positions),'triangles':sum(line.startswith('f ') for line in result),
        'source_native_normals':{'original_obj_sha256':sha(source),'payload':str(payload),'payload_sha256':sha(payload),
            'exact_vertex_index_mapping':True,'maximum_position_order_error_m':error,'maximum_uv_order_error':uv_error,
            'encoding':'Original packed BGR bytes12..14 mapped to xyz;source Z reflected into OBJ. Unit direction normalized;all vertex/UV/face/material lines unchanged.',
            'scope':'Source geometry and authored vertex-normal directions. Wind,tangent normal maps and back-view shader remain separate.'}}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source-root',type=Path,required=True)
    p.add_argument('--payload-root',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False);rows=[]
    for name in ['large','medium']:
        file='tree_oak_'+name+'_a_0.obj'
        rows.append(restore(a.source_root/file,a.payload_root/('tree_oak_'+name+'_a.npz'),a.output/file))
    write_json(a.output/'report.json',{'tool_sha256':sha(__file__),'models':rows});print(json.dumps(rows),flush=True)
if __name__=='__main__':main()
