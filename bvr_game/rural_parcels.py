"""Seeded road-oriented agricultural subdivisions within existing exclusions."""
import math,random
import numpy as np
from shapely.geometry import LineString
from shapely.ops import split


def road_parcels(baker,farm):
    from .worldgen import pieces
    from .regional_cover import smooth_noise
    cfg=baker.r['landscape']['rural_parcels'];low,high=cfg['area_range_m2']
    if not 5000<=low<high<=1000000:raise ValueError('Invalid rural parcel area range')
    rng=random.Random(baker.r['seed']^0x52555241);pending=[(p,0) for p in pieces(farm)];leaves=[]
    while pending:
        poly,depth=pending.pop();center=poly.representative_point()
        road=min((line for _,line in baker.roads),key=lambda line:line.distance(center))
        station=road.project(center);a=road.interpolate(max(0,station-80));b=road.interpolate(min(road.length,station+80))
        heading=math.atan2(b.y-a.y,b.x-a.x);slope=baker.terrain.slope(center.x,center.y)
        target=math.exp(rng.uniform(math.log(low),math.log(high)))/(1+min(.3,slope)*3)
        if poly.area<=target or depth>=24:
            leaves.append(poly);continue
        heading+=rng.uniform(-.16,.16);c,s=math.cos(heading),math.sin(heading)
        vertices=np.asarray(poly.exterior.coords);along=vertices@np.array([c,s]);across=vertices@np.array([-s,c])
        # Bisect the longer road-relative extent, producing shared boundaries
        # and T junctions instead of an independent grid per field.
        angle=heading+math.pi/2 if np.ptp(along)>np.ptp(across) else heading
        tangent=np.array([math.cos(angle),math.sin(angle)]);normal=np.array([-tangent[1],tangent[0]])
        extent=max(poly.bounds[2]-poly.bounds[0],poly.bounds[3]-poly.bounds[1]);radius=extent*3+100
        projected=vertices@normal;children=[]
        for attempt in range(8):
            coordinate=float(projected.min()+(projected.max()-projected.min())*rng.uniform(.35,.65))
            if attempt>=4:coordinate=center.x*normal[0]+center.y*normal[1]
            origin=np.array([center.x,center.y]);origin+=normal*(coordinate-origin@normal)
            bend=min(12.,math.sqrt(poly.area)*.012)*rng.choice([-1,1])
            cutter=LineString([origin+tangent*t+normal*bend*math.cos(t/radius*math.pi/2)
                for t in np.linspace(-radius,radius,9)])
            children=list(pieces(split(poly,cutter)))
            if len(children)>1 and (min(p.area for p in children)>low*.12 or attempt==7):break
        if len(children)<2:leaves.append(poly)
        else:pending.extend((p,depth+1) for p in children)
    result=[]
    palette=cfg['palette_linear']
    for poly in leaves:
        n,w=poly.centroid.x,poly.centroid.y;draw=rng.random()
        regional=float(smooth_noise(np.asarray(n),np.asarray(w),1600,baker.r['seed']+83))
        cover=1. if draw<.18 else rng.uniform(.18,.35) if draw<.26 else float(np.clip(.63+.35*regional+rng.uniform(-.07,.07),.5,.98))
        rectangle=np.asarray(poly.minimum_rotated_rectangle.exterior.coords);edges=np.diff(rectangle,axis=0)
        longest=edges[np.argmax(np.linalg.norm(edges,axis=1))];heading=math.atan2(longest[1],longest[0])%math.pi
        result.append({'id':'road_parcel_'+str(len(result)),'polygon':list(map(list,poly.exterior.coords)),
            'holes':[list(map(list,h.coords)) for h in poly.interiors],'area_m2':poly.area,
            'surface':'grass' if cover==1 else 'farmland','crop_cover':cover,
            'color':rng.choice(palette),'heading_rad':heading,
            'appearance_source':'Authored source-grass/soil cover within road and forest exclusions; road-oriented cuts and slope-related parcel area. Not GIS or measured agriculture.'})
    return result
