"""Validated presentation LODs; published maps and near-source bytes stay intact."""
import json
from pathlib import Path
from .content import sha


def distance_lod_models(models,profile=None):
    result=dict(models)
    for asset,spec in (profile or {}).get('vegetation_distance_lods',{}).items():
        if asset not in models:continue
        parent_path=Path(spec.get('parent_manifest',Path(models[asset]).parent/'manifest.json'))
        parent=json.loads(parent_path.read_text(encoding='utf8'))
        if parent.get('id')!=asset or sha(models[asset])!=parent['glb_sha256']:
            raise ValueError('Distance LOD near source mismatch: '+asset)
        path=Path(spec['manifest']).resolve()
        if sha(path)!=spec['manifest_sha256']:raise ValueError('Distance LOD manifest changed: '+asset)
        derived=json.loads(path.read_text(encoding='utf8'))
        provenance=derived.get('source_distance_lod',{})
        if provenance.get('parent_asset')!=asset or provenance.get('parent_manifest_sha256')!=sha(parent_path):
            raise ValueError('Distance LOD parent mismatch: '+asset)
        if derived['glb_sha256']!=parent['glb_sha256'] or derived['lods'][0]['sha256']!=parent['glb_sha256']:
            raise ValueError('Distance LOD changed near geometry: '+asset)
        for key in ['recentering','source_base_anchor_blender','poses_before_recentering']:
            if derived['cluster'][key]!=parent['cluster'][key]:
                raise ValueError('Distance LOD changed tree placements: '+asset)
        for index,lod in enumerate(derived['lods']):
            file=(path.parent/lod['file']).resolve()
            if not file.is_relative_to(path.parent):raise ValueError('Distance LOD path escapes asset')
            if sha(file)!=lod['sha256']:raise ValueError('Distance LOD mesh changed: '+asset)
            result[asset if index==0 else asset+'::lod'+str(index)]=str(file)
        for materials in derived.get('source_card_mips',{}).get('materials_by_lod_file',{}).values():
            for slots in materials.values():
                for entry in slots.values():
                    file=(path.parent/entry['file']).resolve()
                    if not file.is_relative_to(path.parent) or sha(file)!=entry['sha256']:
                        raise ValueError('Distance LOD texture changed: '+asset)
    return result
