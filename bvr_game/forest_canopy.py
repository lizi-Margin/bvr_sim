"""Offline source-albedo forest aggregate for the existing material baker.

This is a ground-projected distant canopy approximation, not extra 3D trees,
physical terrain or a claim of exact correspondence with individual instances.
"""
import json, math
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from .content import ASSETS, sha


def blend_canopy(understory, north, west, pixel_m, policy):
    asset = ASSETS / 'registered' / policy['asset']
    manifest_file = asset / 'manifest.json'
    manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
    if manifest.get('license') != 'CC0-1.0' or not manifest.get('distribution_allowed'):
        raise ValueError('Canopy aggregate requires a cleared registered source')
    # The converter's last view is orthographic from above, with source albedo
    # and opacity only. Resolve it inside the registered bundle.
    source = (asset / _basename(manifest['impostor']['views'][-1])).resolve()
    if not source.is_relative_to(asset.resolve()):
        raise ValueError('Canopy source must stay inside its registered bundle')
    if sha(source) != policy['source_sha256']:
        raise ValueError('Registered canopy albedo hash does not match the map recipe')
    tile = float(policy['tile_m']); layers = int(policy.get('layers', 3))
    strength = float(policy.get('strength', .9))
    if not 4 <= tile <= 200 or not 1 <= layers <= 4 or not 0 <= strength <= 1:
        raise ValueError('Invalid canopy aggregate policy')
    rgba = np.asarray(Image.open(source).convert('RGBA'), dtype=np.float32) / 255
    rgb = np.where(rgba[..., :3] <= .04045, rgba[..., :3] / 12.92,
                   ((rgba[..., :3] + .055) / 1.055) ** 2.4)
    premultiplied = np.concatenate([rgb * rgba[..., 3:], rgba[..., 3:]], axis=2)
    # Integrate a map pixel's footprint in linear premultiplied color before
    # sampling. Filtering straight RGB would darken translucent crown edges.
    size = max(2, min(rgba.shape[0], math.ceil(tile / pixel_m)))
    filtered = np.stack([np.asarray(Image.fromarray(premultiplied[..., i], mode='F').resize(
        (size, size), Image.Resampling.BOX)) for i in range(4)], axis=2)
    result = understory.copy(); coverage = np.zeros(north.shape, dtype=np.float32)
    for angle, dn, dw in [(0., .17, .31), (.73, .61, .13), (1.91, .29, .79), (2.47, .83, .47)][:layers]:
        u = np.mod((north * math.cos(angle) - west * math.sin(angle)) / tile + dn, 1) * size - .5
        v = np.mod((north * math.sin(angle) + west * math.cos(angle)) / tile + dw, 1) * size - .5
        sampled = np.stack([map_coordinates(filtered[..., i], [v, u], order=1,
            mode='grid-wrap') for i in range(4)], axis=1)
        alpha = sampled[:, 3] * strength
        result = result * (1 - alpha[:, None]) + sampled[:, :3] * strength
        coverage = coverage + alpha * (1 - coverage)
    return result, {'asset': policy['asset'], 'registered_manifest_sha256': sha(manifest_file),
        'source_file': str(source), 'source_sha256': sha(source), 'source_url': manifest['source_url'],
        'license': manifest['license'], 'tile_m': tile, 'layers': layers, 'strength': strength,
        'filtered_resolution': [size, size], 'mean_alpha_coverage': float(coverage.mean()),
        'method': 'Linear premultiplied source top-view albedo over understory; deterministic rotated layers, footprint area filter',
        'limitation': 'Ground-projected distant aggregate; no canopy height, shadows or exact per-instance correspondence. Does not change the terrain or count as additional 3D trees.'}


def _basename(value):
    # Bundles produced on Windows also remain readable on POSIX.
    return value.replace('\\', '/').rsplit('/', 1)[-1]
