"""Search/fetch verified local War Thunder texture imports; no game access at runtime."""
from pathlib import Path
import hashlib,json,re,shutil

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def inventory(report,registered_root=None):
    report=Path(report).resolve();document=json.loads(report.read_text(encoding='utf8'));items=[]
    for row in document['textures']:
        if row['status']!='decoded':continue
        file=Path(row['png']).resolve();id=file.parent.name+'/'+file.stem
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',id):raise ValueError('Unsupported imported texture ID: '+id)
        items.append({'source':'warthunder','id':id,'kind':'texture','file':str(file),
            'sha256':row['png_sha256'],'width':row['width'],'height':row['height'],'mode':row['mode'],
            'license':'user-owned-local-War-Thunder-resource','distribution_allowed':False,
            'raw_source':row['source'],'raw_source_sha256':row['source_sha256']})
    if registered_root is not None:
        for file in sorted(Path(registered_root).glob('WT-*/manifest.json')):
            asset=json.loads(file.read_text(encoding='utf8'))
            if asset.get('license')!='user-owned-local-War-Thunder-resource':continue
            items.append({'source':'warthunder','id':asset['id'],'kind':'model','name':asset['name'],
                'file':str((file.parent/asset['file']).resolve()),'sha256':asset['glb_sha256'],
                'registered_manifest':str(file.resolve()),'registered_manifest_sha256':sha(file),
                'triangles':asset['triangles'],'bounds_blender':asset['bounds_blender'],
                'license':asset['license'],'distribution_allowed':False,'tags':asset.get('tags',[])})
    return report,document,items

def search(report,query,limit,registered_root=None,kind='any'):
    report,document,items=inventory(report,registered_root);words=query.casefold().split()
    matches=[row for row in items if (kind=='any' or row['kind']==kind or kind=='material' and row['kind']=='texture')
        and all(word in (row['id']+' '+row.get('name','')+' '+' '.join(row.get('tags',[]))).casefold() for word in words)]
    return {'total':len(matches),'results':matches[:limit],'import_report':str(report),
        'scope':'Verified local texture imports and registered WT GLB models. Texture names do not establish PBR channel semantics.'}

def fetch(report,cache,id,max_mb,registered_root=None):
    report,document,items=inventory(report,registered_root)
    selected=next((row for row in items if row['id']==id),None)
    if selected is None:raise ValueError('No decoded texture with ID '+id)
    if selected['kind']=='model':
        original=Path(selected['registered_manifest']);asset=json.loads(original.read_text(encoding='utf8'))
        files=[(original,'asset-manifest.json',selected['registered_manifest_sha256'])]
        for lod in asset['lods']:
            source=(original.parent/lod['file']).resolve()
            if not source.is_relative_to(original.parent.resolve()):raise ValueError('Registered model file leaves its asset directory')
            files.append((source,lod['file'],lod['sha256']))
        if sum(p.stat().st_size for p,_,_ in files)>max_mb*1024*1024:raise ValueError('Model exceeds --max-mb')
        for source,_,digest in files:
            if sha(source)!=digest:raise ValueError('Registered model changed: '+str(source))
        root=Path(cache).resolve()/'warthunder'/id;root.mkdir(parents=True,exist_ok=True)
        records=[]
        for source,name,digest in files:
            target=root/name
            if not target.exists() or sha(target)!=digest:shutil.copy2(source,target)
            records.append({'path':name,'sha256':sha(target),'bytes':target.stat().st_size})
        manifest={**selected,'entry':asset['file'],'files':records,'source_url':asset['source_url'],
            'scope':'Exact registered GLB/source metadata. Both registered mesh levels remain available; runtime vegetation uses the highest geometry.'}
        (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
        return {'directory':str(root),'manifest':str(root/'manifest.json'),'entry':asset['file'],
            'files':len(records),'bytes':sum(r['bytes'] for r in records),'sha256':selected['sha256'],'distribution_allowed':False}
    source=Path(selected['file'])
    if source.stat().st_size>max_mb*1024*1024:raise ValueError('Texture exceeds --max-mb')
    if sha(source)!=selected['sha256']:raise ValueError('Imported texture changed: '+str(source))
    root=Path(cache).resolve()/'warthunder'/id;root.mkdir(parents=True,exist_ok=True);target=root/source.name
    if not target.exists() or sha(target)!=selected['sha256']:shutil.copy2(source,target)
    manifest={**selected,'source_url':'local://WarThunder/'+id,'entry':target.name,
        'import_report':str(report),'import_report_sha256':sha(report),
        'files':[{'path':target.name,'sha256':sha(target),'bytes':target.stat().st_size}],
        'original_packs':document.get('original_packs',[]),
        'scope':'Exact decoded source pixels. No inferred normal/PBR packing or aerodynamic data.'}
    (root/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    return {'directory':str(root),'manifest':str(root/'manifest.json'),'entry':target.name,
        'files':1,'bytes':target.stat().st_size,'sha256':sha(target),'distribution_allowed':False}
