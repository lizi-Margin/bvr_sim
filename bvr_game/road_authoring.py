"""Offline road draping on the exact shared indexed terrain triangles."""
import math
import numpy as np
from shapely import contains_xy,polygons,intersection,constrained_delaunay_triangles
from shapely.geometry import box,Polygon
from .heightfield import sample_grid


def scene_heights(scene,north,west):
    n,w=np.broadcast_arrays(north,west);meta=scene.document['terrain'];result=sample_grid(scene.arrays['base'],meta['base'],n,w)
    for tile in meta['details']:
        inside=(n>=tile['origin_north'])&(n<=tile['origin_north']+(tile['columns']-1)*tile['spacing'])&(w>=tile['origin_west'])&(w<=tile['origin_west']+(tile['rows']-1)*tile['spacing'])
        result=np.where(inside,sample_grid(scene.arrays[tile.get('array_key','focus')],tile,n,w),result)
    return result


def drape_polygon(scene,footprint,bias=.025):
    """Clip road polygons within each real terrain triangle,then triangulate.

    Sampling a long ribbon alone would bridge over the terrain's indexed
    diagonal and can either float or cut into the surface. This mesh shares
    the underlying planes even inside clipped/concave road junctions.
    """
    vertices=[];indices=[];terrain=scene.document['terrain'];tiles=[terrain['base'],*terrain['details']]
    for index,meta in enumerate(tiles):
        key='base' if index==0 else meta.get('array_key','focus');step=meta['spacing'];on=meta['origin_north'];ow=meta['origin_west']
        region=footprint.intersection(box(on,ow,on+(meta['columns']-1)*step,ow+(meta['rows']-1)*step))
        for fine in tiles[index+1:]:region=region.difference(box(fine['origin_north'],fine['origin_west'],fine['origin_north']+(fine['columns']-1)*fine['spacing'],fine['origin_west']+(fine['rows']-1)*fine['spacing']))
        if region.is_empty:continue
        minimum_n,minimum_w,maximum_n,maximum_w=region.bounds
        c0=max(0,math.floor((minimum_n-on)/step));c1=min(meta['columns']-1,math.ceil((maximum_n-on)/step))
        r0=max(0,math.floor((minimum_w-ow)/step));r1=min(meta['rows']-1,math.ceil((maximum_w-ow)/step))
        candidates=region.buffer(step*.708+1e-5)
        for first in range(r0,r1,64):
            n,w=np.meshgrid(on+(np.arange(c0,c1)+.5)*step,ow+(np.arange(first,min(first+64,r1))+.5)*step)
            selected=contains_xy(candidates,n,w);n=n[selected]-step/2;w=w[selected]-step/2
            if not len(n):continue
            a=np.column_stack([n,w]);b=a+[step,0];c=a+[0,step];d=a+[step,step]
            source=np.concatenate([np.stack([a,b,c],axis=1),np.stack([d,c,b],axis=1)])
            for clipped in intersection(polygons(source),region):
                if clipped.is_empty:continue
                parts=list(clipped.geoms) if hasattr(clipped,'geoms') else [clipped]
                for part in parts:
                    if not isinstance(part,Polygon) or part.area<1e-9:continue
                    for triangle in constrained_delaunay_triangles(part).geoms:
                        xy=np.asarray(triangle.exterior.coords)[:3]
                        u=xy[1]-xy[0];v=xy[2]-xy[0];area=u[0]*v[1]-u[1]*v[0]
                        if area<0:xy=xy[[0,2,1]]
                        height=sample_grid(scene.arrays[key],meta,xy[:,0],xy[:,1])+bias
                        start=len(vertices);vertices.extend(np.column_stack([xy,height]).tolist());indices.extend([start,start+1,start+2])
    return vertices,indices


def placed_blender_points(points,item):
    """Match native root scale,yaw,and upright-to-up-normal rotation exactly."""
    p=np.asarray(points,dtype=float)[:,[0,2,1]]*item['scale']
    angle=-item['yaw'];c,s=math.cos(angle),math.sin(angle)
    p=p@np.array([[c,0,-s],[0,1,0],[s,0,c]])
    up=np.asarray(item.get('up_normal',[0,1,0]),dtype=float);up/=np.linalg.norm(up)
    axis=np.cross([0,1,0],up);k=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
    rotation=np.eye(3)+k+k@k/(1+up[1]);p=p@rotation.T
    n,w,h=item['position'];p+=np.array([-w,h,n])
    return p[:,[2,0,1]]*np.array([1,-1,1])


def drape_on_mesh(triangles,footprint,bias=.003):
    """Paint overlay clipped to real source deck triangles,not a second deck."""
    vertices=[];indices=[]
    for source in np.asarray(triangles,dtype=float):
        xy=source[:,:2];matrix=xy[1:]-xy[0]
        if abs(np.linalg.det(matrix))<1e-9:continue
        plane=np.linalg.solve(matrix,source[1:,2]-source[0,2]);clipped=Polygon(xy).intersection(footprint)
        if clipped.is_empty or clipped.area<1e-10:continue
        for triangle in constrained_delaunay_triangles(clipped).geoms:
            points=np.asarray(triangle.exterior.coords)[:3];u=points[1]-points[0];v=points[2]-points[0]
            if u[0]*v[1]-u[1]*v[0]<0:points=points[[0,2,1]]
            z=(points-xy[0])@plane+source[0,2]+bias
            first=len(vertices);vertices.extend(np.column_stack([points,z]).tolist());indices.extend([first,first+1,first+2])
    return vertices,indices


class DryRoadPlanner:
    """Terrain-cost A* with conservative wet clearance on a saved planning grid."""
    def __init__(self,scene,water,half_m=40000,spacing=100):
        self.spacing=spacing;self.origin=-half_m;self.axis=np.arange(-half_m,half_m+1,spacing)
        n,w=np.meshgrid(self.axis,self.axis);self.heights=scene_heights(scene,n,w)
        self.blocked=contains_xy(water.buffer(spacing*.72+20),n,w)
    def node(self,point):
        c,r=np.rint((np.asarray(point)-self.origin)/self.spacing).astype(int)
        if not (0<=r<len(self.axis) and 0<=c<len(self.axis)) or self.blocked[r,c]:raise ValueError('Road waypoint is wet or leaves planning grid: '+str(point))
        return int(r),int(c)
    def route(self,start,end):
        import heapq
        first=self.node(start);last=self.node(end);queue=[(0.,0.,first)];cost={first:0.};parent={}
        directions=[(a,b) for a in [-1,0,1] for b in [-1,0,1] if a or b]
        while queue:
            _,distance,here=heapq.heappop(queue)
            if distance!=cost.get(here):continue
            if here==last:break
            r,c=here
            for dr,dc in directions:
                nr,nc=r+dr,c+dc
                if not 0<=nr<len(self.axis) or not 0<=nc<len(self.axis) or self.blocked[nr,nc]:continue
                step=math.hypot(dr,dc)*self.spacing;grade=abs(float(self.heights[nr,nc]-self.heights[r,c]))/step
                value=distance+step*(1+3*grade+30*max(0,grade-.08))
                if value>=cost.get((nr,nc),float('inf')):continue
                cost[nr,nc]=value;parent[nr,nc]=here;heuristic=math.hypot(nr-last[0],nc-last[1])*self.spacing
                heapq.heappush(queue,(value+heuristic,value,(nr,nc)))
        if last not in cost:raise ValueError('No dry road route connects waypoints')
        result=[last]
        while result[-1]!=first:result.append(parent[result[-1]])
        return [[float(self.axis[c]),float(self.axis[r])] for r,c in result[::-1]]
