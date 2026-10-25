"""Camera-independent authored woodland openings, shared by offline trees/color."""
import json
from functools import lru_cache
import numpy as np
from .regional_cover import cell_noise,smooth_noise


@lru_cache(maxsize=4)
def road_exclusion(encoded_roads):
    from shapely import union_all,prepare
    from shapely.geometry import LineString
    result=union_all([LineString(r['points']).buffer(r['forest_clearance_m']) for r in json.loads(encoded_roads)])
    prepare(result);return result


def validate_policy(policy):
    if policy.get('kind')!='authored_reference_woodland':raise ValueError('Unsupported authored canopy policy')
    spacing=float(policy['clearing_cell_m']);low,high=map(float,policy['clearing_radius_m'])
    if not 400<=spacing<=2000 or not 20<=low<=high<=spacing*.28:raise ValueError('Invalid authored clearing policy')
    if 'shore_root_clearance_m' in policy and not 0<=float(policy['shore_root_clearance_m'])<=100:raise ValueError('Invalid shore root clearance')
    if 'road_root_clearance_m' in policy and not 0<=float(policy['road_root_clearance_m'])<=100:raise ValueError('Invalid road root clearance')
    if not 0<=policy.get('clearing_probability',1.)<=1:raise ValueError('Invalid clearing probability')
    if policy.get('clearing_shape','harmonic') not in ('harmonic','world_noise'):raise ValueError('Invalid clearing shape')
    if policy.get('clearing_shape')=='world_noise':
        if not 10<=policy.get('clearing_edge_scale_m',45)<=200 or not 0<=policy.get('clearing_edge_strength',.28)<=.5:raise ValueError('Invalid clearing edge noise')
    fragment=policy.get('meadow_fragmentation')
    if fragment is not None:
        if not isinstance(fragment,dict):raise ValueError('Invalid meadow fragmentation')
        bounds=np.asarray(fragment.get('bounds_nw',[]),dtype=float)
        if bounds.shape!=(4,) or not np.isfinite(bounds).all() or bounds[0]>=bounds[2] or bounds[1]>=bounds[3]:raise ValueError('Invalid meadow fragmentation bounds')
        if not 100<=fragment.get('scale_m',600)<=2000 or not .5<=fragment.get('threshold',.88)<=1 or not 10<=fragment.get('fade_m',500)<=4000:raise ValueError('Invalid meadow fragmentation parameters')
    for road in policy.get('roads',[]):
        points=np.asarray(road['points'],dtype=float)
        if points.ndim!=2 or points.shape[1]!=2 or len(points)<2 or not np.isfinite(points).all() or not 5<=road['forest_clearance_m']<=200:raise ValueError('Invalid authored canopy road')
    return spacing,low,high,int(policy['seed'])


def woodland_mask(north,west,policy):
    spacing,low,high,seed=validate_policy(policy)
    n,w=np.broadcast_arrays(north,west);x=np.floor(n/spacing).astype(np.int64);y=np.floor(w/spacing).astype(np.int64)
    opening=np.zeros(n.shape,dtype=bool)
    shape_edge=(1+policy.get('clearing_edge_strength',.28)*(2*smooth_noise(n,w,policy.get('clearing_edge_scale_m',45),seed+20)-1)) if policy.get('clearing_shape')=='world_noise' else None
    # Adjacent cells matter when the jittered clearing crosses a cell edge.
    # Every shape is defined in world coordinates and works unchanged at
    # any raster resolution or planting domain, with no camera input.
    for dx in [-1,0,1]:
        for dy in [-1,0,1]:
            a=x+dx;b=y+dy
            cn=(a+.5+(cell_noise(a,b,seed+1)-.5)*.65)*spacing
            cw=(b+.5+(cell_noise(a,b,seed+2)-.5)*.65)*spacing
            turn=cell_noise(a,b,seed+3)*2*np.pi;stretch=.85+.5*cell_noise(a,b,seed+4)
            dn=n-cn;dw=w-cw;u=(dn*np.cos(turn)+dw*np.sin(turn))/stretch;v=(-dn*np.sin(turn)+dw*np.cos(turn))*stretch
            angle=np.arctan2(v,u);radius=low+(high-low)*cell_noise(a,b,seed+5)
            edge=radius*shape_edge if shape_edge is not None else radius*(1+.17*np.sin(3*angle+turn)+.11*np.cos(5*angle-turn))
            active=True if policy.get('clearing_probability',1.)==1 else cell_noise(a,b,seed+21)<policy['clearing_probability']
            opening|=(u*u+v*v<edge*edge)&active
    # A small number of broad meadow patches break the otherwise continuous
    # canopy. This is authored land use, not recovered source placement.
    meadow=smooth_noise(n,w,2200,seed+6)>.86
    fragment=policy.get('meadow_fragmentation')
    if fragment:
        n0,w0,n1,w1=fragment['bounds_nw']
        distance=np.minimum.reduce([n-n0,w-w0,n1-n,w1-w])
        blend=np.clip(distance/fragment.get('fade_m',500),0,1);blend=blend*blend*(3-2*blend)
        # Split only existing broad meadows. This admits every old tree point,
        # retains small clearings, and fades back to the unchanged outer map.
        fragment_noise=smooth_noise(n,w,fragment.get('scale_m',600),seed+22)
        meadow&=(blend<=0)|(fragment_noise>fragment.get('threshold',.88)*blend)
    opening|=meadow
    if policy.get('roads'):
        from shapely import contains_xy
        opening|=contains_xy(road_exclusion(json.dumps(policy['roads'],sort_keys=True)),n,w)
    return ~opening
