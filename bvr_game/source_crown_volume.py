"""Source-supported crown volumes for distant foliage, without whole-tree cards.

Cell-local convex aggregates retain the volume of the original dense needles.
They are an explicit opaque foliage approximation, not original source triangles
or an exact botanical surface. Every aggregate vertex is a real source vertex.
"""
from pathlib import Path
import copy,json,math,struct
import numpy as np
from PIL import Image
from scipy.spatial import ConvexHull,QhullError
from .content import ASSETS,sha,write_json


def source_points(manifest):
    source=Path(manifest['source']);doc=json.loads(source.read_text(encoding='utf8'))
    if sha(source)!=manifest['source_sha256']:raise ValueError('Source glTF changed')
    for item in manifest['source_files']:
        if sha(source.parent/item['path'])!=item['sha256']:raise ValueError('Source dependency changed')
    name=manifest['conversion_recipe']['policy']['select_object']
    index=next(i for i,n in enumerate(doc['nodes']) if n.get('name')==name)
    node=doc['nodes'][index]
    if any(k in node for k in ['matrix','rotation','translation','scale']) or any(index in n.get('children',[]) for n in doc['nodes']):
        raise ValueError('Source point reader requires the declared identity source node')
    buffers=[(source.parent/b['uri']).read_bytes() for b in doc['buffers']]
    def accessor(index):
        a=doc['accessors'][index];v=doc['bufferViews'][a['bufferView']]
        dtype={5126:'<f4',5125:'<u4',5123:'<u2'}[a['componentType']]
        width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4}[a['type']]
        offset=v.get('byteOffset',0)+a.get('byteOffset',0)
        return np.ndarray((a['count'],width),dtype=dtype,buffer=buffers[v['buffer']],offset=offset,
                          strides=(v.get('byteStride',np.dtype(dtype).itemsize*width),np.dtype(dtype).itemsize))
    positions=[];colors=[]
    for primitive in doc['meshes'][node['mesh']]['primitives']:
        p=accessor(primitive['attributes']['POSITION']).copy()
        p=p[:,[0,2,1]];p[:,1]*=-1 # glTF Y-up to Blender Z-up
        uv=accessor(primitive['attributes']['TEXCOORD_0'])
        material=doc['materials'][primitive['material']]['pbrMetallicRoughness']
        texture=doc['textures'][material['baseColorTexture']['index']]
        file=source.parent/doc['images'][texture['source']]['uri']
        image=np.asarray(Image.open(file).convert('RGB'),dtype=np.float32)/255
        image=np.where(image<=.04045,image/12.92,((image+.055)/1.055)**2.4)
        u=np.floor(np.mod(uv[:,0],1)*image.shape[1]).astype(int)%image.shape[1]
        v=np.floor(np.mod(uv[:,1],1)*image.shape[0]).astype(int)%image.shape[0]
        positions.append(p);colors.append(image[v,u]*np.asarray(material.get('baseColorFactor',[1]*4)[:3]))
    points=np.concatenate(positions);colors=np.concatenate(colors)
    lo=points.min(axis=0);hi=points.max(axis=0)
    points-=np.array([(lo[0]+hi[0])/2,(lo[1]+hi[1])/2,lo[2]])
    return points,colors


def crown(points,colors,cell):
    bins=np.floor((points-points.min(axis=0))/cell).astype(np.int64)
    spans=bins.max(axis=0)+1;keys=(bins[:,0]*spans[1]+bins[:,1])*spans[2]+bins[:,2]
    order=np.argsort(keys,kind='stable');keys=keys[order]
    boundaries=np.r_[0,np.flatnonzero(np.diff(keys))+1,len(order)]
    vertices=[];normals=[];tints=[];kept=0
    for begin,end in zip(boundaries[:-1],boundaries[1:]):
        if end-begin<4:continue
        ids=order[begin:end]
        # Bound hull work while retaining deterministic actual source points.
        sample=ids[np.linspace(0,len(ids)-1,min(24,len(ids))).astype(int)]
        value=points[sample]
        try:hull=ConvexHull(value)
        except QhullError:continue
        if hull.volume<1e-9:continue
        triangles=hull.simplices.copy();normal=hull.equations[:,:3].copy()
        tri=value[triangles];winding=np.einsum('ij,ij->i',np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),normal)
        triangles[winding<0]=triangles[winding<0][:,[0,2,1]]
        vertices.append(value[triangles].reshape(-1,3));normals.append(np.repeat(normal,3,axis=0))
        # Actual linear-light source albedo, averaged inside this source cell.
        tint=np.mean(colors[ids],axis=0);tints.append(np.tile(np.r_[tint,1.],(len(triangles)*3,1)));kept+=1
    if not vertices:raise ValueError('Source crown volume is empty')
    return np.concatenate(vertices),np.concatenate(normals),np.concatenate(tints),kept


def export_cluster(file,mesh,cluster):
    vertices,normals,colors,_=mesh;all_p=[];all_n=[];all_c=[];all_uv=[]
    center=np.asarray(cluster['recentering']);poses=cluster['poses_before_recentering']
    for index,pose in enumerate(poses):
        c,s=math.cos(pose['yaw']),math.sin(pose['yaw']);rotation=np.array([[c,s,0],[-s,c,0],[0,0,1]])
        p=vertices@rotation*pose['scale']+np.asarray(pose['position'])-center
        n=normals@rotation
        p=p[:,[0,2,1]];p[:,2]*=-1;n=n[:,[0,2,1]];n[:,2]*=-1
        all_p.append(p);all_n.append(n);all_c.append(colors)
        all_uv.append(np.tile([(index+.5)/len(poses),0.],(len(vertices),1)))
    p=np.concatenate(all_p).astype('<f4');n=np.concatenate(all_n).astype('<f4')
    color=np.concatenate(all_c).astype('<f4');uv1=np.concatenate(all_uv).astype('<f4')
    uv0=np.zeros_like(uv1);indices=np.arange(len(p),dtype='<u4')
    doc={'asset':{'version':'2.0','generator':'BVR source-supported foliage volume'},'scene':0,
         'scenes':[{'nodes':[0]}],'nodes':[{'mesh':0}], 'meshes':[{'primitives':[]}],
         'materials':[{'name':'source_supported_crown_albedo','pbrMetallicRoughness':{'baseColorFactor':[1,1,1,1],'metallicFactor':0,'roughnessFactor':.95}}],
         'bufferViews':[],'accessors':[],'buffers':[]}
    data=bytearray()
    def add(array,type_name,component=5126,position=False):
        while len(data)%4:data.append(0)
        view={'buffer':0,'byteOffset':len(data),'byteLength':array.nbytes};data.extend(array.tobytes());doc['bufferViews'].append(view)
        a={'bufferView':len(doc['bufferViews'])-1,'componentType':component,'count':len(array),'type':type_name}
        if position:a.update(min=array.min(axis=0).tolist(),max=array.max(axis=0).tolist())
        doc['accessors'].append(a);return len(doc['accessors'])-1
    attrs={'POSITION':add(p,'VEC3',position=True),'NORMAL':add(n,'VEC3'),'TEXCOORD_0':add(uv0,'VEC2'),
           'TEXCOORD_1':add(uv1,'VEC2'),'COLOR_0':add(color,'VEC4')}
    doc['meshes'][0]['primitives']=[{'attributes':attrs,'indices':add(indices,'SCALAR',5125),'material':0}]
    doc['buffers']=[{'byteLength':len(data)}];encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
    data.extend(b'\0'*((-len(data))%4))
    file.write_bytes(struct.pack('<III',0x46546c67,2,28+len(encoded)+len(data))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(data),0x004e4942)+data)
    return len(p)//3,len(p)


def derive(source_id,target_id,near_cell=.8,far_cell=1.6):
    if not .2<=near_cell<far_cell<=2:raise ValueError('Invalid source crown cell sizes')
    source=ASSETS/'registered'/source_id/'manifest.json';original=json.loads(source.read_text(encoding='utf8'))
    if original.get('license')!='CC0-1.0' or not original.get('distribution_allowed'):raise ValueError('Uncleared source crown')
    out=ASSETS/'registered'/target_id
    if out.exists():raise FileExistsError('Source crown target already exists')
    out.mkdir(parents=True)
    points,colors=source_points(original);lods=[];counts=[];cells=[]
    for level,size in enumerate([near_cell,far_cell]):
        mesh=crown(points,colors,size);triangles=len(mesh[0])//3;counts.append(triangles);cells.append(mesh[3])
        if triangles*original['cluster']['source_copies']>6400000:raise ValueError('Source aggregate exceeds declared mesh budget')
        file=out/(target_id+('_lod1' if level else '')+'.glb')
        faces,vertices=export_cluster(file,mesh,original['cluster'])
        lods.append({'level':level,'file':file.name,'sha256':sha(file),'triangles':faces,'vertices':vertices})
        print('SOURCE_CROWN',level,'cells',mesh[3],'triangles/tree',triangles,flush=True)
    manifest=copy.deepcopy(original)
    manifest.update(id=target_id,name='Source fir A cell-local crown volumes',file=lods[0]['file'],glb_sha256=lods[0]['sha256'],
                    lods=lods,triangles=lods[0]['triangles'],faces=lods[0]['triangles'],vertices=lods[0]['vertices'],
                    impostor=None,foliage_representation=None,textures=[],materials=[{'name':'source_supported_crown_albedo','roughness':.95}])
    manifest.pop('source_card_mips',None)
    manifest['conversion_recipe']['policy']['near_triangle_budget']=6400000
    manifest['source_geometry_lods']={'near_triangles_per_tree':counts[0],'far_triangles_per_tree':counts[1],
        'source_cells':cells,'cell_size_m':[near_cell,far_cell],'method':__doc__}
    manifest['source_crown_volume']={'source_asset':source_id,'source_manifest_sha256':sha(source),
         'source_vertices':len(points),'source_object':original['conversion_recipe']['policy']['select_object'],
         'geometry_scope':__doc__,'color':'Actual source UV albedo sampled in linear light; per-cell mean. No baked lighting.',
         'generator_sha256':sha(Path(__file__))}
    write_json(out/'manifest.json',manifest)
    return manifest
