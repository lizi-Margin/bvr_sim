"""Audit registered source normals/UVs without rewriting geometry or textures."""
from pathlib import Path
import argparse,hashlib,json,struct,sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json,sha

def inspect(path):
    data=path.read_bytes();length=struct.unpack_from('<I',data,12)[0]
    doc=json.loads(data[20:20+length]);offset=20+length
    size,kind=struct.unpack_from('<II',data,offset);assert kind==0x004e4942
    blob=data[offset+8:offset+8+size]
    def accessor(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        dtype=np.dtype({5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']])
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        return np.ndarray((a['count'],width),dtype,blob,v.get('byteOffset',0)+a.get('byteOffset',0),
            strides=(v.get('byteStride',width*dtype.itemsize),dtype.itemsize)).copy()
    rows=[];geometry_hash=hashlib.sha256()
    for mesh in doc['meshes']:
        for p in mesh['primitives']:
            a=p['attributes'];pos=accessor(a['POSITION']);indices=accessor(p['indices']).ravel().reshape(-1,3)
            uv=accessor(a['TEXCOORD_0']) if 'TEXCOORD_0' in a else None
            for value in [pos,indices,uv]:
                if value is not None:geometry_hash.update(value.tobytes())
            normals=accessor(a['NORMAL']) if 'NORMAL' in a else None
            face=np.cross(pos[indices[:,1]]-pos[indices[:,0]],pos[indices[:,2]]-pos[indices[:,0]])
            area=np.linalg.norm(face,axis=1);valid=area>1e-9
            unit=face[valid]/area[valid,None]
            dots=np.einsum('ij,ikj->ik',unit,normals[indices[valid]]) if normals is not None else None
            row={'mesh':mesh.get('name'),'material':doc['materials'][p['material']].get('name'),
                'vertices':len(pos),'triangles':len(indices),'degenerate_triangles':int((~valid).sum()),
                'finite_positions':bool(np.isfinite(pos).all()),'has_uv':uv is not None,
                'uv_range':[uv.min(axis=0).tolist(),uv.max(axis=0).tolist()] if uv is not None else None,
                'normal_length_range':[float(np.linalg.norm(normals,axis=1).min()),float(np.linalg.norm(normals,axis=1).max())] if normals is not None else None,
                'face_corner_normal_dot_percentiles':np.percentile(dots,[0,1,50,99,100]).tolist() if dots is not None and len(dots) else None,
                'reversed_corner_normal_fraction':float((dots<-.01).mean()) if dots is not None and len(dots) else None}
            rows.append(row)
    return {'file':str(path.resolve()),'source_glb_sha256':sha(path),'position_index_uv_sha256':geometry_hash.hexdigest(),
        'materials':doc['materials'],'primitives':rows,
        'scope':'Object-space source triangle/normal and UV audit; not proof of pixel appearance. Normals at thin two-sided surfaces may oppose back faces; do not blindly recompute all smoothing.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    for id in ['F22','F16']:
        folder=ROOT/'game/assets/registered'/id;m=json.loads((folder/'manifest.json').read_text())
        result=inspect(folder/m['file']);write_json(a.output/(id+'.json'),result)
        rows=result['primitives'];print(id,'primitives',len(rows),'bad_normal_lengths',sum(r['normal_length_range'] is None or r['normal_length_range'][0]<.9 for r in rows),
            'reversed_majority',[(r['mesh'],r['reversed_corner_normal_fraction']) for r in rows if (r['reversed_corner_normal_fraction'] or 0)>.5])
if __name__=='__main__':main()
