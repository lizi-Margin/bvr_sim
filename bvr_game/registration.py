"""Register another reviewed GLB/glTF recipe without changing scene-generator code."""
import json,re,subprocess,sys,zipfile
from pathlib import Path
from .content import ROOT,ASSETS,sha,write_json

def register_spec(path,blender):
    spec=json.loads(Path(path).read_text(encoding='utf8'));id=spec['id']
    if not re.fullmatch(r'[A-Za-z0-9_-]+',id):raise ValueError('Asset ID must be an ASCII filename identifier')
    source=Path(spec['source']).resolve();provider_path=Path(spec['provider_manifest']).resolve();provider=json.loads(provider_path.read_text(encoding='utf8'))
    if source.suffix.lower() not in ['.glb','.gltf']:raise ValueError('Generic registration accepts reviewed GLB/glTF; use the separate aircraft recipe for AC3D')
    if provider['license']!='CC0-1.0':raise ValueError('Generic scenery registration requires a verified CC0 provider')
    if provider.get('provider')=='kenney':
        directory=Path(provider['directory']).resolve()
        if not source.is_relative_to(directory) or str(source.relative_to(directory)) not in provider['models']:raise ValueError('Source is not listed in this provider pack')
        archive=provider_path.parent/provider['archive']
        if sha(archive)!=provider['archive_sha256']:raise ValueError('Provider archive hash mismatch')
        import hashlib
        with zipfile.ZipFile(archive) as package:
            if hashlib.sha256(package.read(source.relative_to(directory).as_posix())).hexdigest()!=sha(source):raise ValueError('Extracted source differs from the official archive')
    elif provider.get('files') and not any((provider_path.parent/item['path']).resolve()==source for item in provider['files']):raise ValueError('Source is not listed in the provider file manifest')
    for item in provider.get('files',[]):
        p=provider_path.parent/item['path']
        if sha(p)!=item['sha256']:raise ValueError('Provider source hash changed: '+str(p))
    if 'provider' not in provider:
        name=provider.get('source')
        if name not in ['polyhaven','ambientcg']:raise ValueError('Unrecognized provider; explicit license evidence and provider metadata are required')
        notice='https://polyhaven.com/license' if name=='polyhaven' else 'https://docs.ambientcg.com/license/'
        normalized={**provider,'provider':name,'download_url':None,'license_evidence':[{'url':notice,'source_manifest':str(provider_path),'source_manifest_sha256':sha(provider_path)}],'archive_sha256':None,'distribution_allowed':True}
        provider_path=ASSETS/'cache/registration-providers'/(id+'.json');write_json(provider_path,normalized)
    else:
        if not provider.get('license_evidence') or not provider.get('distribution_allowed'):raise ValueError('Provider lacks explicit license/distribution evidence')
    output=ASSETS/'registered'/id
    if (output/'manifest.json').exists():raise ValueError('ID already registered; choose a new version ID to avoid replacing existing baked resources')
    spec={**spec,'source':str(source),'provider_manifest':str(provider_path),'output':str(output),'name':spec.get('name',source.stem),'tags':spec.get('tags',[]),'use':spec.get('use','reviewed scenery'),'density':spec.get('density',10),'collision':spec.get('collision','decorative'),'material_policy':spec.get('material_policy',{'metallic':0,'roughness':.85,'temperate_foliage':False}),'converter_sha256':sha(ROOT/'game/tools/convert_catalog.py')}
    recipe=ASSETS/'cache/registration-recipes'/(id+'.json');write_json(recipe,[spec])
    subprocess.run([blender,'--background','--python-exit-code','1','--python',str(ROOT/'game/tools/convert_catalog.py'),'--',str(recipe)],check=True,stdout=sys.stderr)
    manifest=json.loads((output/'manifest.json').read_text(encoding='utf8'));runtime_path=ROOT/'game/runtime.json';runtime=json.loads(runtime_path.read_text(encoding='utf8'))
    for lod in manifest['lods']:runtime['models'][id+('' if lod['level']==0 else '::lod1')]=str(output/lod['file'])
    write_json(runtime_path,runtime)
    inventory=[json.loads(p.read_text(encoding='utf8')) for p in sorted((ASSETS/'registered').glob('*/manifest.json')) if p.parent.name!='audio'];write_json(ASSETS/'catalog.json',{'schema_version':2,'assets':inventory})
    return manifest
