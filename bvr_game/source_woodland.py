"""Retained source coverage/density masks with explicit authored tree substitution."""
from pathlib import Path
import numpy as np
from .content import sha
from .wt_landscape import RoBitmap


def protected_footprints(document,water,radius,*,shore_root_clearance_m=None,road_root_clearance_m=None):
    from shapely import union_all
    from shapely.geometry import MultiPoint,Point,Polygon
    if shore_root_clearance_m is not None and not 0<=shore_root_clearance_m<=100:raise ValueError('Invalid shoreline root clearance')
    if road_root_clearance_m is not None and not 0<=road_root_clearance_m<=100:raise ValueError('Invalid road root clearance')
    road_contacts={r['id']+'_surface' for r in document.get('roads',[]) if isinstance(r.get('id'),str)}
    blocked=[water.buffer(radius+1 if shore_root_clearance_m is None else shore_root_clearance_m)]
    # Airport ribbons contain many vertex pairs. The first four do not
    # represent their full footprint and can even form a crossed polygon.
    # Actual triangle footprints preserve winding roads without excluding
    # their entire convex hull. Older declarations have no index list.
    for s in document['environment']['contact_surfaces']:
        vertices=np.asarray(s['vertices'])[:,:2];indices=s.get('indices')
        if indices:
            polygons=[Polygon(vertices[t]) for t in np.asarray(indices).reshape(-1,3)]
            footprint=union_all([p for p in polygons if p.area>1e-8])
        else:footprint=MultiPoint(vertices).convex_hull
        clearance=road_root_clearance_m if road_root_clearance_m is not None and s.get('id') in road_contacts else radius+2
        blocked.append(footprint.buffer(clearance))
    blocked.extend((Polygon(i['canopy_footprint']) if i.get('canopy_footprint') else Point(i['position'][:2]).buffer(i['radius_m'])).buffer(radius+1) for i in document['instances'])
    return union_all(blocked)


def source_plant_layers(report):
    result=[]
    for row,recipe in zip(report['layer']['masks'][1:],report['recipes']):
        if sha(row['bitmap'])!=row['bitmap_sha256']:raise ValueError('Source coverage bitmap changed')
        density=recipe['density_maps'][0]
        if sha(density['source'])!=density['source_sha256']:raise ValueError('Source local density bitmap changed')
        groups=[g['parameters'] for g in recipe['recipe']['blocks'] if g['name']=='obj_plant_generate']
        sizes={tuple(g['mapSize']) for g in groups}
        if len(recipe['density_maps'])!=1 or len(sizes)!=1:raise ValueError('Unsupported source planting tile layout')
        coverage,stride=RoBitmap(Path(row['bitmap']).read_bytes()).image(4096)
        local,local_stride=RoBitmap(Path(density['source']).read_bytes()).image(4096)
        if stride!=1 or local_stride!=1:raise ValueError('Full source bitmaps required for planting')
        result.append({'name':row['name'],'coverage':coverage!=0,'density':local!=0,'tile_m':next(iter(sizes)),
            'density_per_100m2':sum(g['density'] for g in groups),'coverage_sha256':row['bitmap_sha256'],'density_sha256':density['source_sha256']})
    return result


def planting_density(layers,north,west):
    # Retained original source X/Z -> project NWU is N=Z,W=-X.
    x=-np.asarray(west);z=np.asarray(north);result=np.zeros(np.broadcast(x,z).shape)
    ix=np.floor((x+65536)/32).astype(int);iz=np.floor((z+65536)/32).astype(int)
    for layer in layers:
        coverage=layer['coverage']
        if ((ix<0)|(iz<0)|(ix>=coverage.shape[1])|(iz>=coverage.shape[0])).any():raise ValueError('Source planting outside retained source coverage')
        local=layer['density'];tile=np.asarray(layer['tile_m'])
        u=np.floor(np.mod(x+65536,tile[0])/tile[0]*local.shape[1]).astype(int)
        v=np.floor(np.mod(z+65536,tile[1])/tile[1]*local.shape[0]).astype(int)
        result+=coverage[iz,ix]*local[v,u]*layer['density_per_100m2']
    return result
