"""Rigid decorative-grove fit against the shared baked terrain, without grading."""
import math
import numpy as np


def fit_grove(manifest, north, west, yaw, scale, height, *, tolerance_m=.25, max_tilt_rad=.2, include_anchors=False):
    cluster = manifest['cluster']; center = np.asarray(cluster['recentering'])
    source = np.array([p.get('base_anchor',p['position']) for p in cluster['poses_before_recentering']]) - center
    # Blender source XY -> north/west, then the same yaw used by ScenePlacement.
    anchors = np.column_stack([source[:, 1], -source[:, 0], source[:, 2]]) * scale
    c, s = math.cos(yaw), math.sin(yaw)
    anchors = anchors @ np.array([[c, s, 0], [-s, c, 0], [0, 0, 1]])
    samples = np.array([height(north+p[0], west+p[1]) for p in anchors])
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
    actual = np.array([height(north+p[0], west+p[1]) for p in placed])
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
