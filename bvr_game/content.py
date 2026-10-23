"""Versioned, license-checked content providers independent of scene recipes."""
from __future__ import annotations
import argparse,hashlib,json,re,sys,urllib.request,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];ASSETS=ROOT/'game/assets'
KENNEY={
 'nature-kit':{'name':'Nature Kit','tags':['tree','bush','rock','vegetation']},
 'city-kit-roads':{'name':'City Kit Roads','tags':['road','fence','lamp','equipment']},
 'city-kit-industrial':{'name':'City Kit Industrial','tags':['warehouse','tank','industrial']},
 'city-kit-suburban':{'name':'City Kit Suburban','tags':['house','village','building']}}
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def get(url):
    request=urllib.request.Request(url,headers={'User-Agent':'BVRSimSceneBuilder/2.0 (content research)'})
    with urllib.request.urlopen(request,timeout=60) as response:return response.read()
def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def fetch_kenney(asset_id):
    if asset_id not in KENNEY:raise ValueError('Unknown Kenney pack: '+asset_id)
    root=ASSETS/'cache/kenney'/asset_id;manifest=root/'provider.json'
    if manifest.exists():
        m=json.loads(manifest.read_text(encoding='utf8'))
        if sha(root/m['archive'])!=m['archive_sha256']:raise ValueError('Cached archive hash changed')
        return m
    url='https://kenney.nl/assets/'+asset_id;page=get(url).decode('utf8')
    if not re.search(r'(CC0|publicdomain/zero)',page,re.I):raise ValueError('Explicit CC0 evidence missing: '+url)
    links=re.findall(r'href=[\"\']([^\"\']+\.zip(?:\?[^\"\']*)?)[\"\']',page)
    links=[s for s in links if '/media/pages/assets/'+asset_id+'/' in s]
    if len(set(links))!=1:raise ValueError('Ambiguous official download links: '+repr(links))
    download=links[0]
    if download.startswith('/'):download='https://kenney.nl'+download
    if not download.startswith('https://kenney.nl/'):raise ValueError('Unexpected asset host')
    root.mkdir(parents=True,exist_ok=True);archive=root/download.split('/')[-1].split('?')[0]
    archive.write_bytes(get(download));unpacked=root/'unpacked';unpacked.mkdir(exist_ok=True)
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():
            if not (unpacked/item.filename).resolve().is_relative_to(unpacked.resolve()):raise ValueError('Unsafe archive member')
        z.extractall(unpacked)
    notices=[p for p in unpacked.rglob('*') if p.is_file() and 'license' in p.name.lower()]
    evidence=[{'file':str(p.relative_to(root)),'sha256':sha(p)} for p in notices if 'CC0' in p.read_text(encoding='utf8',errors='replace')]
    if not evidence:raise ValueError('Package does not contain a verifiable CC0 notice')
    (root/'source-page.html').write_text(page,encoding='utf8')
    m={'id':asset_id,**KENNEY[asset_id],'provider':'kenney','source_url':url,'download_url':download,'license':'CC0-1.0','license_evidence':evidence,'archive':archive.name,'archive_sha256':sha(archive),'distribution_allowed':True,'directory':str(unpacked.resolve()),'models':[str(p.relative_to(unpacked)) for p in sorted(unpacked.rglob('*')) if p.suffix.lower() in ['.glb','.gltf','.obj']]}
    write_json(manifest,m);return m
def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='command',required=True)
    search=s.add_parser('search');search.add_argument('query')
    fetch=s.add_parser('fetch');fetch.add_argument('id',choices=KENNEY)
    a=p.parse_args()
    result=fetch_kenney(a.id) if a.command=='fetch' else [{'id':k,**v,'license':'CC0-1.0','source_url':'https://kenney.nl/assets/'+k} for k,v in KENNEY.items() if a.query.lower() in ' '.join([k,v['name'],*v['tags']]).lower()]
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
