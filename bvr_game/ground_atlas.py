"""Immutable float32 presentation copy of the shared indexed terrain surface."""
from pathlib import Path
import math
import numpy as np
from .content import sha,write_json
from .heightfield import sample_grid


def build_atlas(arrays,terrain,grid):
    """Resample aligned refinements without introducing a new surface diagonal.

    A finest grid can represent the coarser indexed triangles exactly only
    when all source origins, spacings, and tile boundaries align to it.
    Runtime contact and collision continue to use the original core terrain.
    """
    spacing=float(grid['spacing']);columns=int(grid['columns']);rows=int(grid['rows'])
    if not math.isfinite(spacing) or spacing<=0 or not 2<=columns<=16384 or not 2<=rows<=16384:
        raise ValueError('Invalid ground atlas grid')
    if not all(math.isfinite(grid[k]) for k in ['origin_north','origin_west']):raise ValueError('Invalid ground atlas origin')
    tiles=[(terrain['base'],'base')]+[(t,t.get('array_key','focus')) for t in sorted(terrain['details'],key=lambda x:x['spacing'],reverse=True)]
    for meta,key in tiles:
        values=[meta['spacing']/spacing,(meta['origin_north']-grid['origin_north'])/spacing,(meta['origin_west']-grid['origin_west'])/spacing]
        if any(abs(v-round(v))>1e-7 for v in values) or values[0]<1:
            raise ValueError('Atlas must align with every source triangle grid')
        if np.asarray(arrays[key]).shape!=(meta['rows'],meta['columns']):raise ValueError('Source height dimensions mismatch')
    base=terrain['base']
    for origin,count,base_count in [('origin_north',columns,'columns'),('origin_west',rows,'rows')]:
        if grid[origin]<base[origin] or grid[origin]+(count-1)*spacing>base[origin]+(base[base_count]-1)*base['spacing']:
            raise ValueError('Ground atlas extends beyond shared terrain')
    atlas=np.empty((rows,columns),dtype='<f4');north=grid['origin_north']+np.arange(columns)*spacing
    for first in range(0,rows,128):
        west=grid['origin_west']+np.arange(first,min(first+128,rows))*spacing
        n,w=np.broadcast_arrays(north[None,:],west[:,None]);height=sample_grid(arrays['base'],base,n,w)
        for meta,key in tiles[1:]:
            inside=(n>=meta['origin_north'])&(n<=meta['origin_north']+(meta['columns']-1)*meta['spacing'])&(w>=meta['origin_west'])&(w<=meta['origin_west']+(meta['rows']-1)*meta['spacing'])
            height[inside]=sample_grid(arrays[key],meta,n[inside],w[inside])
        atlas[first:first+len(west)]=height
    if not np.isfinite(atlas).all():raise ValueError('Nonfinite source terrain height')
    return atlas


def write_atlas(directory,arrays,terrain,grid):
    """Publish a content-addressed sidecar; leave previous map versions intact."""
    import hashlib
    atlas=build_atlas(arrays,terrain,grid);checksum=hashlib.sha256(atlas.tobytes()).hexdigest()
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True);path=directory/(checksum+'.r32')
    if path.exists():
        if sha(path)!=checksum:raise ValueError('Existing ground atlas was modified')
    else:atlas.tofile(path)
    metadata={**grid,'file':str(path.resolve()),'sha256':checksum,'source_height_archive_sha256':terrain['sha256'],
        'encoding':'R32_FLOAT little endian; rows west, columns north; indexed triangles, no bilinear sampling',
        'bytes':atlas.nbytes}
    write_json(directory/(checksum+'.json'),metadata)
    return metadata


def load_atlas(meta,map_path,terrain_sha256):
    if meta['source_height_archive_sha256']!=terrain_sha256:raise ValueError('Ground atlas belongs to a different shared terrain version')
    path=(Path(map_path).parent/meta['file']).resolve()
    expected=int(meta['rows'])*int(meta['columns'])*4
    if path.stat().st_size!=expected or sha(path)!=meta['sha256']:raise ValueError('Ground atlas bytes/hash mismatch')
    result=np.fromfile(path,dtype='<f4').reshape(meta['rows'],meta['columns'])
    if not np.isfinite(result).all():raise ValueError('Ground atlas contains nonfinite heights')
    return result


def copy_or_build_atlas(source_scene,terrain,directory):
    """Rebuild old map versions without an atlas, or preserve exact existing bytes."""
    import shutil
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    if terrain.get('ground_atlas'):
        meta=dict(terrain['ground_atlas']);source=(source_scene.path.parent/meta['file']).resolve();dest=directory/(meta['sha256']+'.r32')
        if sha(source)!=meta['sha256']:raise ValueError('Source ground atlas changed')
        if dest.exists():
            if sha(dest)!=meta['sha256']:raise ValueError('Existing ground atlas destination was modified')
        elif source!=dest.resolve():shutil.copy2(source,dest)
        meta['file']=str(dest.resolve());return meta
    parent=terrain['details'][0];spacing=min(t['spacing'] for t in terrain['details'])
    grid={'origin_north':parent['origin_north'],'origin_west':parent['origin_west'],'spacing':spacing,
        'columns':round((parent['columns']-1)*parent['spacing']/spacing)+1,'rows':round((parent['rows']-1)*parent['spacing']/spacing)+1}
    return write_atlas(directory,source_scene.arrays,terrain,grid)
