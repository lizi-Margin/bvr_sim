"""Extract one addressed source tree with exact geometry/material/texture bytes."""
import copy,json,struct
import numpy as np

def extract(source,target,slot,count):
    raw=source.read_bytes();length=struct.unpack_from('<I',raw,12)[0]
    doc=json.loads(raw[20:20+length]);blob=bytearray(raw[28+length:])
    if len(doc['meshes'])!=1 or len(doc['nodes'])!=1:raise ValueError('Expected one registered joined grove mesh')
    types={5121:'u1',5123:'<u2',5125:'<u4',5126:'<f4'};widths={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}
    def read(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        if 'sparse' in a or 'byteStride' in v or a.get('normalized'):raise ValueError('Unsupported grove accessor')
        return np.frombuffer(blob,dtype=types[a['componentType']],count=a['count']*widths[a['type']],offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],-1).copy()
    def append(array,original,component=None):
        while len(blob)%4:blob.append(0)
        data=array.tobytes();view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':len(blob),'byteLength':len(data)});blob.extend(data)
        a=copy.deepcopy(original);a['bufferView']=view;a.pop('byteOffset',None);a['count']=len(array)
        if component:a['componentType']=component
        if 'min' in a:a['min']=array.min(axis=0).tolist();a['max']=array.max(axis=0).tolist()
        index=len(doc['accessors']);doc['accessors'].append(a);return index
    primitives=[]
    for p in doc['meshes'][0]['primitives']:
        if p.get('mode',4)!=4 or 'targets' in p:raise ValueError('Expected static source triangles')
        addresses=read(p['attributes']['TEXCOORD_1']);triangles=read(p['indices']).reshape(-1,3)
        slots=np.floor(addresses[:,0]*count).astype(int);selected=triangles[np.all(slots[triangles]==slot,axis=1)]
        if not len(selected):continue
        vertices=np.unique(selected);result=copy.deepcopy(p)
        for name,index in p['attributes'].items():
            original=read(index);subset=original[vertices];result['attributes'][name]=append(subset,doc['accessors'][index])
            np.testing.assert_array_equal(subset,original[vertices])
        remapped=np.searchsorted(vertices,selected).astype('<u4').reshape(-1,1)
        result['indices']=append(remapped,doc['accessors'][p['indices']],5125);primitives.append(result)
    if not primitives:raise ValueError('Source tree slot has no triangles')
    doc['meshes'][0]['primitives']=primitives;doc['buffers'][0]['byteLength']=len(blob)
    encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4);blob.extend(b'\0'*((-len(blob))%4))
    target.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(blob))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(blob),0x004e4942)+blob)
