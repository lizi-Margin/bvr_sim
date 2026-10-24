"""Rigid decorative-grove fit against the shared baked terrain, without grading."""
import math
import numpy as np

def placed_stems(manifest,item):
    """Base references before per-tree height sampling, or rigid source anchors."""
    if 'ground_stems' in item:
        points=np.asarray(item['ground_stems'],dtype=float);count=len(manifest['cluster']['poses_before_recentering'])
        if points.ndim!=2 or points.shape[1]!=2 or not 1<=len(points)<=count or not np.isfinite(points).all():raise ValueError('Independent source tree count/position mismatch')
        return np.column_stack([points,np.full(len(points),item['position'][2])])
    cluster=manifest['cluster'];source=np.array([p['base_anchor'] if 'base_anchor' in p else p['position'] for p in cluster['poses_before_recentering']],dtype=float)-np.asarray(cluster['recentering'])
    anchors=source[:,[1,0,2]].copy();anchors[:,1]*=-1;anchors*=item['scale']
    c,s=math.cos(item['yaw']),math.sin(item['yaw']);anchors=anchors@np.array([[c,s,0],[-s,c,0],[0,0,1]])
    up=item.get('up_normal',[0,1,0]);normal=np.asarray([up[2],-up[0],up[1]],dtype=float)
    if not np.isfinite(normal).all() or normal[2]<=0:raise ValueError('Invalid grove up normal')
    normal/=np.linalg.norm(normal);axis=np.cross([0,0,1],normal)
    k=np.array([[0,-axis[2],axis[1]],[axis[2],0,-axis[0]],[-axis[1],axis[0],0]])
    return anchors@(np.eye(3)+k+k@k/(1+normal[2])).T+np.asarray(item['position'])


def conform_grove(manifest,north,west,yaw,scale,height,*,sample_heights=None,include_anchors=False,ground_stems=None):
    """Offline source references for upright trees independently placed on terrain.

    These expected heights are not a GPU measurement. Runtime deformation uses
    the same version's R32 atlas, with separate GPU draw-buffer validation.
    """
    if not manifest['cluster'].get('ground_conform'):raise ValueError('Source mesh has no per-tree base encoding')
    root=float(height(north,west));item={'position':[north,west,root],'scale':scale,'yaw':yaw,'up_normal':[0,1,0]}
    if ground_stems is not None:item['ground_stems']=ground_stems
    stems=placed_stems(manifest,item)
    values=np.array([height(n,w) for n,w,_ in stems]) if sample_heights is None else np.asarray(sample_heights(stems[:,0],stems[:,1]),dtype=float)
    if values.shape!=(len(stems),) or not np.isfinite(values).all():raise ValueError('Invalid per-tree terrain samples')
    stems[:,2]=values
    result={'height':root,'up_normal':[0,1,0],'source_trees':len(stems),'source_height_span_m':float(np.ptp(values)),
        'method':'Independent source UV1 base anchors; upright source trees; expected shared terrain heights, not measured GPU errors'}
    if include_anchors:result['_world_anchors']=stems.tolist()
    return result

def stem_spacing_report(items,metadata,tolerance_m=.015):
    """Validate opted-in overlapping crowns using actual inter-grove stems."""
    from scipy.spatial import cKDTree
    selected=[];points=[];owners=[];limits=[];independent=[]
    for item in items:
        manifest=metadata[item['model']]
        minimum=float(manifest.get('conversion_recipe',{}).get('policy',{}).get('cluster',{}).get('inter_grove_stem_spacing_m',0))
        if not manifest.get('cluster') or not minimum:continue
        if not 0<minimum<=10:raise ValueError('Invalid inter-grove stem spacing')
        stems=placed_stems(manifest,item);owners.extend([len(selected)]*len(stems));points.append(stems[:,:2]);limits.append(minimum);selected.append(item['id']);independent.append('ground_stems' in item)
    conflicts=[];cross_pairs=0
    if points:
        points=np.concatenate(points);owners=np.asarray(owners);limits=np.asarray(limits)
        pairs=cKDTree(points).query_pairs(float(limits.max()),output_type='ndarray')
        independent=np.asarray(independent)
        pairs=pairs[(owners[pairs[:,0]]!=owners[pairs[:,1]])|independent[owners[pairs[:,0]]]]
        cross_pairs=len(pairs)
        for a,b in pairs:
            distance=float(np.linalg.norm(points[a]-points[b]));minimum=float(max(limits[owners[a]],limits[owners[b]]))
            if distance<minimum-tolerance_m:conflicts.append({'instance':selected[owners[a]],'other':selected[owners[b]],'error':'inter-grove stem spacing','distance_m':distance,'required_m':minimum})
    return {'groves':len(selected),'source_stems':len(owners),'inter_grove_pairs_in_search_radius':cross_pairs,'tolerance_m':tolerance_m,'failures':conflicts}


def fit_grove(manifest, north, west, yaw, scale, height, *, sample_heights=None, tolerance_m=.25, max_tilt_rad=.2, include_anchors=False):
    cluster = manifest['cluster']; center = np.asarray(cluster['recentering'])
    source = np.array([p.get('base_anchor',p['position']) for p in cluster['poses_before_recentering']]) - center
    # Blender source XY -> north/west, then the same yaw used by ScenePlacement.
    anchors = np.column_stack([source[:, 1], -source[:, 0], source[:, 2]]) * scale
    c, s = math.cos(yaw), math.sin(yaw)
    anchors = anchors @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    def heights(points):
        if sample_heights is None:return np.array([height(north+p[0], west+p[1]) for p in points])
        values=np.asarray(sample_heights(north+points[:,0],west+points[:,1]),dtype=float)
        if values.shape!=(len(points),) or not np.isfinite(values).all():raise ValueError('Invalid batch ground samples')
        return values
    samples = heights(anchors)
    plane = np.column_stack([anchors[:, :2], np.ones(len(anchors))])
    dn, dw, _ = np.linalg.lstsq(plane, samples-anchors[:, 2], rcond=None)[0]
    normal = np.array([-dn, -dw, 1.]); normal /= np.linalg.norm(normal)
    tilt = math.acos(float(normal[2]))
    if tilt > max_tilt_rad:
        return None
    axis = np.cross([0, 0, 1], normal)
    k = np.array([[0, -axis[2], axis[1]], [axis[2], 0, -axis[0]], [-axis[1], axis[0], 0]])
    rotation = np.eye(3)+k+k@k/(1+normal[2])
    placed = anchors @ rotation.T
    actual = heights(placed)
    root_height = float(np.mean(actual-placed[:, 2]))
    errors = placed[:, 2]+root_height-actual
    maximum = float(np.max(np.abs(errors)))
    if maximum > tolerance_m:
        return None
    result={'height': root_height, 'up_normal': [-float(normal[1]), float(normal[2]), float(normal[0])],
        'source_trees': len(anchors), 'max_anchor_error_m': maximum,
        'base_anchor_method':cluster.get('base_anchor_method','Legacy normalized source bounds base reference; not actual stem vertices'),
        'rms_anchor_error_m': float(np.sqrt(np.mean(errors**2))), 'tilt_rad': tilt}
    if include_anchors:result['_world_anchors']=np.column_stack([placed[:,0]+north,placed[:,1]+west,placed[:,2]+root_height]).tolist()
    return result
