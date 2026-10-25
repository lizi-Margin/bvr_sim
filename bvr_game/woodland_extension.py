"""Offline scenery extension using immutable shared-terrain source heights."""
import math
import numpy as np
from shapely import contains_xy
from .regional_cover import smooth_noise


def extension_points(blocked,*,inner_half_m,outer_half_m,spacing_m=12.,jitter_m=2.,seed=155):
    """Jittered world cells retain a provable minimum spacing, independent of view.

    The authored density gradually decreases outside the dense central forest.
    This is fixed scenery placement, with no camera or runtime LOD input.
    """
    values=[inner_half_m,outer_half_m,spacing_m,jitter_m]
    if not all(math.isfinite(v) for v in values) or not 0<inner_half_m<outer_half_m<=40000 or not 0<=jitter_m<spacing_m/2:
        raise ValueError('Invalid offline woodland extension dimensions')
    rng=np.random.default_rng(seed)
    axis=(np.arange(math.floor(-outer_half_m/spacing_m),math.ceil(outer_half_m/spacing_m))+.5)*spacing_m
    result=[]
    for first in range(0,len(axis),64):
        n,w=np.meshgrid(axis,axis[first:first+64])
        candidates=np.column_stack([n.ravel(),w.ravel()])
        candidates+=rng.uniform(-jitter_m,jitter_m,candidates.shape)
        n,w=candidates.T
        edge=np.maximum(abs(n),abs(w))
        mask=(edge>inner_half_m+spacing_m)&(edge<outer_half_m-spacing_m)
        candidates=candidates[mask]
        if len(candidates):
            n,w=candidates.T
            outside=np.maximum(abs(n),abs(w))-inner_half_m
            density=np.maximum(.14,1/(1+np.maximum(outside-3000,0)/8500)**2)
            # Large irregular openings remain a spatial authoring choice.
            irregular=np.clip((smooth_noise(n,w,1300,seed+31)-.18)*3.5,0,1)
            blend=np.clip(outside/3500,0,1);blend=blend*blend*(3-2*blend)
            woods=1-blend+irregular*blend
            candidates=candidates[rng.random(len(candidates))<density*woods]
            if len(candidates):
                candidates=candidates[~contains_xy(blocked,candidates[:,0],candidates[:,1])]
            result.append(candidates)
        print('EXTENSION_ROWS',min(first+64,len(axis)),'/',len(axis),flush=True)
    return np.concatenate(result) if result else np.empty((0,2))
