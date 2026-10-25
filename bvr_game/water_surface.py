"""Offline water-surface tessellation over the same union as core water regions.

Tile the connected polygon before triangulating: no overlapping ribbons at a
confluence, and no huge sloping object bound corrupting the reflection plane.
"""
import math
from shapely.geometry import box
from shapely import constrained_delaunay_triangles


def conform_outer_water(surface,base,height,focus_bounds,clearance_m=.25):
    """Keep distant water on the actual indexed base planes, with no core edit.

    The legacy outer water follows ground (it is not an authored level river).
    A different diagonal can put its interior metres inside a coarse saddle.
    Split at every source triangle; a positive offset then stays positive over
    the entire triangle, rather than only at sampled vertices. Regional level
    water and its intended bank intersections are deliberately retained.
    """
    from shapely.geometry import Polygon
    if not .05<=clearance_m<=1:raise ValueError('Outer water clearance must be .05..1m')
    vertices=surface['vertices'];lo_n=min(p[0] for p in vertices);hi_n=max(p[0] for p in vertices)
    lo_w=min(p[1] for p in vertices);hi_w=max(p[1] for p in vertices)
    a,b,c,d=focus_bounds
    if not (hi_n<=a or lo_n>=c or hi_w<=b or lo_w>=d):return surface
    # Source union tiles are simple triangulated polygons, potentially islands.
    from shapely.ops import unary_union
    water=unary_union([Polygon([vertices[i][:2] for i in surface['indices'][j:j+3]])
        for j in range(0,len(surface['indices']),3)])
    step=base['spacing'];n0=base['origin_north'];w0=base['origin_west']
    result=[];indices=[];lookup={};area=0.
    for col in range(max(0,math.floor((lo_n-n0)/step)),min(base['columns']-1,math.ceil((hi_n-n0)/step))):
        for row in range(max(0,math.floor((lo_w-w0)/step)),min(base['rows']-1,math.ceil((hi_w-w0)/step))):
            n=n0+col*step;w=w0+row*step
            for plane in ([(n,w),(n+step,w),(n,w+step)],[(n+step,w+step),(n,w+step),(n+step,w)]):
                clipped=water.intersection(Polygon(plane))
                if clipped.area<1e-9:continue
                for triangle in constrained_delaunay_triangles(clipped).geoms:
                    if triangle.area<1e-9:continue
                    points=list(triangle.exterior.coords)[:3]
                    if (points[1][0]-points[0][0])*(points[2][1]-points[0][1])-(points[1][1]-points[0][1])*(points[2][0]-points[0][0])<0:points.reverse()
                    for pn,pw in points:
                        key=(round(pn,7),round(pw,7))
                        if key not in lookup:
                            # Match the existing regional join; all other far
                            # vertices get a safe gap above the same core plane.
                            join=(abs(pn-a)<1e-7 or abs(pn-c)<1e-7 or abs(pw-b)<1e-7 or abs(pw-d)<1e-7)
                            offset=.025 if join else clearance_m
                            lookup[key]=len(result);result.append([pn,pw,float(height(pn,pw))+offset])
                        indices.append(lookup[key])
                    area+=triangle.area
    if abs(area-water.area)>max(.001,water.area*1e-9):raise ValueError('Outer water tessellation changed footprint area')
    return {**surface,'vertices':result,'indices':indices,'outer_core_plane_conform':True,
        'outer_clearance_m':clearance_m,'source_footprint_area_m2':water.area}

def build_water_surfaces(baker):
    cfg=baker.r['landscape'];step=float(cfg.get('water_render_chunk_m',1000))
    if not 100<=step<=5000:raise ValueError('Water tile size must be100..5000m')
    water=baker.water;lo_n,lo_w,hi_n,hi_w=water.bounds;surfaces=[];area=0.
    for n in range(math.floor(lo_n/step),math.ceil(hi_n/step)):
        for w in range(math.floor(lo_w/step),math.ceil(hi_w/step)):
            section=water.intersection(box(n*step,w*step,(n+1)*step,(w+1)*step))
            if section.is_empty or section.area<1e-8:continue
            vertices=[];indices=[];lookup={}
            for triangle in constrained_delaunay_triangles(section).geoms:
                if triangle.area<1e-9:continue
                points=list(triangle.exterior.coords)[:3]
                # Same NWU winding as the existing shared terrain/surface data.
                if (points[1][0]-points[0][0])*(points[2][1]-points[0][1])-(points[1][1]-points[0][1])*(points[2][0]-points[0][0])<0:points.reverse()
                for pn,pw in points:
                    key=(round(pn,7),round(pw,7))
                    if key not in lookup:
                        halfn,halfw=(k*500 for k in baker.r['focus_area_km'])
                        border=min(halfn-abs(pn),halfw-abs(pw))
                        from .river_valley import smooth
                        t=float(smooth(border/cfg['regional_transition_m']))
                        z=(baker.terrain.height(pn,pw)+.025)*(1-t)+baker.r['terrain']['river_level_m']*t
                        lookup[key]=len(vertices);vertices.append([pn,pw,z])
                    indices.append(lookup[key])
                area+=triangle.area
            if indices:surfaces.append({'id':f'water_union_{n}_{w}','material':'water','vertices':vertices,'indices':indices,
                'drivable':False,'water_union_tile':True,'source_area_m2':section.area})
    if abs(area-water.area)>max(.01,water.area*1e-9):raise ValueError('Water union lost or duplicated area')
    if cfg.get('outer_water_core_plane_conform'):
        halfn,halfw=(k*500 for k in baker.r['focus_area_km'])
        surfaces=[conform_outer_water(s,baker.terrain.base_meta,baker.terrain.height,
            (-halfn,-halfw,halfn,halfw),float(cfg.get('outer_water_clearance_m',.25))) for s in surfaces]
    return surfaces
