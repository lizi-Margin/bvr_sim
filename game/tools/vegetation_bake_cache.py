"""Validate exact registered source-tree images before reusing a costly bake."""
from pathlib import Path
import hashlib,json,re,struct

def reusable_bakes(spec,source_sha,policy):
    path=Path(spec['manifest']);raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=spec['sha256']:raise ValueError('Reuse manifest changed')
    old=json.loads(raw);original=old['conversion_recipe']['policy']
    if old['source_sha256']!=source_sha:raise ValueError('Reuse source tree differs')
    for key in ['select_object','height_m','foliage_cards','impostor_resolution','impostor_normal_maps']:
        if original.get(key)!=policy.get(key):raise ValueError('Reuse bake settings differ: '+key)
    def validate(lod,bake):
        file=path.parent/old['lods'][lod]['file'];data=file.read_bytes()
        if hashlib.sha256(data).hexdigest()!=old['lods'][lod]['sha256']:raise ValueError('Reuse GLB changed')
        size=struct.unpack_from('<I',data,12)[0];doc=json.loads(data[20:20+size]);blob=data[28+size:];images={}
        for material in doc['materials']:
            match=re.match(r'^source_impostor_(\d+)(?:\.|$)',material['name'])
            if not match:continue
            for kind,index in [('views',material['pbrMetallicRoughness']['baseColorTexture']['index']),('normal_views',material['normalTexture']['index'])]:
                view=doc['bufferViews'][doc['images'][doc['textures'][index]['source']]['bufferView']]
                start=view.get('byteOffset',0);sha=hashlib.sha256(blob[start:start+view['byteLength']]).hexdigest()
                images.setdefault((kind,int(match[1])),set()).add(sha)
        hashes={}
        for kind in ['views','normal_views']:
            if len(bake[kind])!=4:raise ValueError('Four source bake views required')
            for i,name in enumerate(bake[kind]):
                sha=hashlib.sha256(Path(name).read_bytes()).hexdigest()
                if sha not in images[(kind,i)]:raise ValueError('Reuse PNG differs from registered embedded source image')
                hashes[str(Path(name))]=sha
        return {**bake,'validated_png_sha256':hashes,'registered_glb_sha256':old['lods'][lod]['sha256']}
    return {'far':validate(1,old['impostor']['source_tree_bake']),
            'near':validate(0,old['foliage_representation']['bake']),
            'manifest_sha256':spec['sha256'],'source_asset_id':old['id']}
