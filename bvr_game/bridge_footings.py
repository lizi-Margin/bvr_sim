"""Original lowest bridge rings continued into the actual shared riverbed."""
from pathlib import Path
import json,struct
import numpy as np
from shapely.geometry import MultiPoint
from .road_authoring import placed_blender_points,scene_heights


def source_bottom_components(model,threshold=.05):
    raw=Path(model).read_bytes();size=struct.unpack_from('<I',raw,12)[0];g=json.loads(raw[20:20+size]);at=28+size
    def accessor(index):
        a=g['accessors'][index];view=g['bufferViews'][a['bufferView']];dtype={5126:'<f4',5125:'<u4',5123:'<u2',5121:'u1'}[a['componentType']]
        width={'SCALAR':1,'VEC3':3}[a['type']];item=np.dtype(dtype).itemsize
        return np.ndarray((a['count'],width),dtype=dtype,buffer=raw,offset=at+view.get('byteOffset',0)+a.get('byteOffset',0),strides=(view.get('byteStride',item*width),item)).copy()
    parts=[]
    for node in g['nodes']:
        if 'mesh' not in node:continue
        if any(k in node for k in ['matrix','rotation','translation','scale']):raise ValueError('Source footing extraction requires normalized identity mesh nodes')
        for primitive in g['meshes'][node['mesh']]['primitives']:
            p=accessor(primitive['attributes']['POSITION']).astype(float)[:,[0,2,1]]*np.array([1,-1,1]);indices=accessor(primitive['indices']).ravel().astype(int).reshape(-1,3)
            parts.append((p,indices))
    lowest=min(p[:,2].min() for p,_ in parts);values={};parents={}
    def find(x):
        while parents[x]!=x:parents[x]=parents[parents[x]];x=parents[x]
        return x
    for points,triangles in parts:
        keys={i:tuple(np.rint(p*1e5).astype(np.int64)) for i,p in enumerate(points) if p[2]<=lowest+threshold}
        for i,key in keys.items():values.setdefault(key,points[i]);parents.setdefault(key,key)
        for tri in triangles:
            selected=[keys[i] for i in tri if i in keys]
            for a,b in zip(selected,selected[1:]):parents[find(b)]=find(a)
    groups={}
    for key,point in values.items():groups.setdefault(find(key),[]).append(point)
    return [np.asarray(points) for points in groups.values() if len(points)>=3]


def extend_footing(scene,points,item,id):
    world=placed_blender_points(points,item);footprint=MultiPoint(world[:,:2]).convex_hull
    if footprint.area<.01:return None
    xy=np.asarray(footprint.exterior.coords)[:-1]
    coefficients=np.linalg.lstsq(np.column_stack([world[:,:2],np.ones(len(world))]),world[:,2],rcond=None)[0]
    top=np.column_stack([xy,np.ones(len(xy))])@coefficients;ground=scene_heights(scene,xy[:,0],xy[:,1]);bottom=ground-.20
    if np.all(top<=ground+.02):return None
    bottom=np.minimum(bottom,top-.01);count=len(xy)
    vertices=np.vstack([np.column_stack([xy,top]),np.column_stack([xy,bottom])]);indices=[]
    for i in range(1,count-1):indices.extend([0,i,i+1])
    for i in range(count):j=(i+1)%count;indices.extend([i,j,j+count,i,j+count,i+count])
    low=vertices.min(axis=0);high=vertices.max(axis=0)
    return {'surface':{'id':id,'material':'bridge_footing','vertices':vertices.tolist(),'indices':indices,'drivable':False},
        'obstacle':{'id':id,'center':((low+high)/2).tolist(),'half_size':((high-low)/2).tolist(),'yaw':0.},
        'source_bottom_vertices':world.tolist(),'ground_heights_m':ground.tolist(),'top_plane_residual_m':float(abs(np.column_stack([world[:,:2],np.ones(len(world))])@coefficients-world[:,2]).max()),
        'footprint':xy.tolist(),'minimum_bottom_burial_m':float((ground-bottom).min()),
        'scope':'Concrete continuation of actual source lowest-ring footprint to shared riverbed-0.2m;conservative collision box. Upper source pier geometry unchanged.'}
