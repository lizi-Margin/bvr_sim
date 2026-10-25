"""Offline level-water footprints clipped against the actual indexed terrain."""
import numpy as np
from shapely import box,polygons,union_all
from shapely.geometry import LineString,Polygon
from shapely.ops import split


def wet_footprint(heights,meta,level=0.,cutout=None):
    h=np.asarray(heights);step=meta['spacing'];n0=meta['origin_north'];w0=meta['origin_west']
    if h.shape!=(meta['rows'],meta['columns']) or not np.isfinite(h).all():raise ValueError('Invalid shared water-height field')
    corners=np.stack([h[:-1,:-1],h[:-1,1:],h[1:,:-1],h[1:,1:]],axis=-1)
    wet=corners<level;full=wet.all(axis=-1);partial=wet.any(axis=-1)&~full
    if cutout:
        a,b,c,d=cutout;n=n0+(np.arange(h.shape[1]-1)+.5)*step;w=w0+(np.arange(h.shape[0]-1)+.5)*step
        excluded=(n[None,:]>a)&(n[None,:]<c)&(w[:,None]>b)&(w[:,None]<d)
        full&=~excluded;partial&=~excluded
    pieces=[];rectangles=[]
    for row in range(full.shape[0]):
        ends=np.flatnonzero(np.diff(np.r_[False,full[row],False]))
        rectangles.extend((n0+a*step,w0+row*step,n0+b*step,w0+(row+1)*step) for a,b in ends.reshape(-1,2))
    if rectangles:
        rect=np.asarray(rectangles);pieces.extend(box(rect[:,0],rect[:,1],rect[:,2],rect[:,3]))
    rows,cols=np.nonzero(partial)
    base=np.column_stack([n0+cols*step,w0+rows*step])
    offsets=np.array([[0,0],[step,0],[0,step],[step,step]])
    coords=base[:,None,:]+offsets;values=corners[rows,cols]
    # This diagonal is the one used by sample_grid,typed Terrain,and native
    # terrain indices. Bilinear marching squares gives a different shoreline.
    for indices in [[0,1,2],[3,2,1]]:
        p=coords[:,indices];z=values[:,indices];codes=((z<level)*[1,2,4]).sum(axis=1)
        if (codes==7).any():pieces.extend(polygons(p[codes==7]))
        for i in range(3):
            j=(i+1)%3;k=(i+2)%3
            mask=codes==(1<<i)
            if mask.any():
                a=p[mask];v=z[mask]
                qj=a[:,i]+((level-v[:,i])/(v[:,j]-v[:,i]))[:,None]*(a[:,j]-a[:,i])
                qk=a[:,i]+((level-v[:,i])/(v[:,k]-v[:,i]))[:,None]*(a[:,k]-a[:,i])
                pieces.extend(polygons(np.stack([a[:,i],qj,qk],axis=1)))
            mask=codes==(7-(1<<i))
            if mask.any():
                a=p[mask];v=z[mask]
                qk=a[:,k]+((level-v[:,k])/(v[:,i]-v[:,k]))[:,None]*(a[:,i]-a[:,k])
                qj=a[:,i]+((level-v[:,i])/(v[:,j]-v[:,i]))[:,None]*(a[:,j]-a[:,i])
                pieces.extend(polygons(np.stack([a[:,j],a[:,k],qk,qj],axis=1)))
    return union_all(pieces)


def without_holes(geometry):
    """Decompose wet islands for the existing core polygon-only DTO."""
    queue=[geometry] if isinstance(geometry,Polygon) else list(geometry.geoms);result=[]
    while queue:
        polygon=queue.pop()
        if polygon.is_empty or polygon.area<1e-8:continue
        if not polygon.interiors:result.append(polygon);continue
        hole=Polygon(polygon.interiors[0]).representative_point();a,b,c,d=polygon.bounds
        parts=[p for p in split(polygon,LineString([(a-1,hole.y),(c+1,hole.y)])).geoms if isinstance(p,Polygon)]
        if sum(len(p.interiors) for p in parts)>=len(polygon.interiors):raise ValueError('Could not preserve a water island during polygon decomposition')
        queue.extend(parts)
    if abs(sum(p.area for p in result)-geometry.area)>max(1e-8,geometry.area*1e-10):raise ValueError('Water island decomposition changed wet area')
    return result
