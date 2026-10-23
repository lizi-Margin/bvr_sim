"""Small JSON CLI for Poly Haven, ambientCG v3, and a FlightGear archive mirror.
Powered by Poly Haven. No third-party Python packages required.
"""
import argparse, hashlib, json, os, re, subprocess, sys, urllib.parse, urllib.request, zipfile
from pathlib import Path

UA='BVRSimAssetLibraryPrototype/0.1 (Powered by Poly Haven)'
HERE=Path(__file__).resolve().parent
TYPES={'hdri':0,'material':1,'model':2}
def emit(value): print(json.dumps(value,ensure_ascii=False,indent=2))
def get_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=40) as response:return json.load(response)
def catalog(cache):
    target=cache/'polyhaven_catalog.json'
    if not target.exists():
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(get_json('https://api.polyhaven.com/assets'),ensure_ascii=False),encoding='utf8')
    return json.loads(target.read_text(encoding='utf8'))
def checked_path(root,name):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('Path leaves asset directory: '+name)
    return path
def download(url,path,expected=None):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists() and expected and hashlib.md5(path.read_bytes()).hexdigest()==expected:return
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    temp=path.with_name(path.name+'.partial')
    try:
        with urllib.request.urlopen(req,timeout=60) as response,temp.open('wb') as out:
            while chunk:=response.read(1024*1024):out.write(chunk)
        if expected and hashlib.md5(temp.read_bytes()).hexdigest()!=expected:raise ValueError('MD5 mismatch: '+str(path))
        temp.replace(path)
    finally:
        if temp.exists():temp.unlink()
def extract(archive,root):
    with zipfile.ZipFile(archive) as z:
        for item in z.infolist():checked_path(root,item.filename)
        z.extractall(root)
def search(args,cache):
    if args.source=='polyhaven':
        words=args.query.lower().split();matches=[]
        for key,value in catalog(cache).items():
            if args.kind!='any' and value.get('type')!=TYPES[args.kind]:continue
            haystack=' '.join([key,value.get('name',''),value.get('description',''),' '.join(value.get('tags',[]))]).lower()
            if all(w in haystack for w in words):
                matches.append({'source':'polyhaven','id':key,'name':value['name'],'kind':next(k for k,v in TYPES.items() if v==value['type']),'polycount':value.get('polycount'),'license':'CC0-1.0'})
        return {'total':len(matches),'results':matches[:args.limit],'credit':'Powered by Poly Haven'}
    if args.source=='ambientcg':
        query=urllib.parse.urlencode({'q':args.query,'limit':min(args.limit,500),'include':'title,type,url,dimensions'})
        return get_json('https://ambientcg.com/api/v3/assets?'+query)
    data=json.loads(Path(args.inventory).read_text(encoding='utf-8-sig'))
    matches=[{'source':'aircraft','id':Path(a['name']).stem,'archive':a['name'],'bytes':a['bytes'],'license':'inspect package','formats':a['formats']} for a in data['archives'] if args.query.casefold() in a['name'].casefold()]
    return {'total':len(matches),'results':matches[:args.limit]}
def fetch(args,cache):
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',args.id):raise ValueError('This prototype accepts ASCII asset IDs without spaces')
    root=cache/args.source/args.id;root.mkdir(parents=True,exist_ok=True)
    pending=[];license_name='CC0-1.0';entry=None
    if args.source=='polyhaven':
        info=catalog(cache)[args.id];kind=next(k for k,v in TYPES.items() if v==info['type'])
        files=get_json('https://api.polyhaven.com/files/'+args.id)
        if kind=='model':
            chosen=files['gltf'][args.resolution]['gltf'];entry=Path(urllib.parse.urlparse(chosen['url']).path).name
            pending=[(entry,chosen)]+list(chosen.get('include',{}).items())
        elif kind=='hdri':
            chosen=files['hdri'][args.resolution]['hdr'];entry=Path(urllib.parse.urlparse(chosen['url']).path).name;pending=[(entry,chosen)]
        else:
            for map_name in ['Diffuse','nor_gl','Rough','Metal','AO']:
                if map_name not in files:continue
                variants=files[map_name].get(args.resolution,{})
                chosen=variants.get('jpg') or variants.get('png')
                if chosen:pending.append((Path(urllib.parse.urlparse(chosen['url']).path).name,chosen))
        source_url='https://polyhaven.com/a/'+args.id
    elif args.source=='ambientcg':
        query=urllib.parse.urlencode({'id':args.id,'include':'title,url,downloads','limit':1})
        data=get_json('https://ambientcg.com/api/v3/assets?'+query)['assets'][0]
        chosen=next(v for v in data['downloads'] if v['attributes'].lower()==args.resolution.lower()+'-jpg')
        entry=args.id+'_'+chosen['attributes']+'.zip';pending=[(entry,chosen)];source_url=data['url']
    else:
        inventory=json.loads(Path(args.inventory).read_text(encoding='utf-8-sig'))
        item=next(a for a in inventory['archives'] if Path(a['name']).stem==args.id)
        if item['bytes']>args.max_mb*1024*1024:raise ValueError('Archive exceeds --max-mb')
        entry=item['name'];path=checked_path(root,entry)
        subprocess.run(['scp','-q','-o','BatchMode=yes','-P',str(args.ssh_port),args.ssh_host+':'+args.remote_root.rstrip('/')+'/'+entry,str(path)],check=True)
        extract(path,root);license_name='inspect package';source_url='ssh://'+args.ssh_host+':'+str(args.ssh_port)+args.remote_root+'/'+entry
    total=sum(v.get('size',0) for _,v in pending)
    if total>args.max_mb*1024*1024:raise ValueError('Files exceed --max-mb')
    for name,meta in pending:download(meta['url'],checked_path(root,name),meta.get('md5'))
    if args.source=='ambientcg':extract(root/entry,root/'unpacked')
    artifacts=[{'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(root.rglob('*')) if p.is_file() and p.name!='manifest.json']
    manifest={'source':args.source,'id':args.id,'source_url':source_url,'license':license_name,'entry':entry,'resolution':args.resolution,'credit':'Powered by Poly Haven' if args.source=='polyhaven' else None,'files':artifacts}
    (root/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    return {'directory':str(root),'manifest':str(root/'manifest.json'),'files':len(artifacts),'bytes':sum(a['bytes'] for a in artifacts),'entry':entry}
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cache',type=Path,default=HERE.parent/'assets/cache')
    parser.add_argument('--inventory',default=str(HERE.parent/'assets/aircraft_inventory.json'))
    sub=parser.add_subparsers(dest='command',required=True)
    s=sub.add_parser('search');s.add_argument('source',choices=['polyhaven','ambientcg','aircraft']);s.add_argument('query');s.add_argument('--kind',choices=['any',*TYPES],default='any');s.add_argument('--limit',type=int,default=8)
    f=sub.add_parser('fetch');f.add_argument('source',choices=['polyhaven','ambientcg','aircraft']);f.add_argument('id');f.add_argument('--resolution',default='1k');f.add_argument('--max-mb',type=float,default=80);f.add_argument('--ssh-host',default='hulc@172.24.147.18');f.add_argument('--ssh-port',type=int,default=1145);f.add_argument('--remote-root',default='/home/hulc/Aircraft-2024')
    args=parser.parse_args();args.cache=args.cache.resolve();emit((search if args.command=='search' else fetch)(args,args.cache))
if __name__=='__main__':
    try:main()
    except Exception as e:emit({'error':str(e)});sys.exit(1)
