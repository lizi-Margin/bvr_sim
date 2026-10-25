"""Local Tacview OBJ/default-properties adapter; no flight dynamics are inferred."""
from pathlib import Path
import hashlib,json,shutil,xml.etree.ElementTree as ET

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def normalized(text):return ''.join(c.casefold() for c in text if c.isalnum())
def inventory(root,cache):
    root=Path(root).resolve();cache=Path(cache);meshes=root/'3D Models/Data/Meshes';database=root/'Database/Default Properties'
    files=sorted(meshes.glob('*.obj'))+sorted(database.glob('*.xml'))+[root/'LICENSE.txt']
    signature=[(str(p.relative_to(root)),p.stat().st_size,p.stat().st_mtime_ns) for p in files]
    target=cache/'tacview/catalog.json'
    if target.exists():
        old=json.loads(target.read_text(encoding='utf8'))
        if old.get('adapter_sha256')==sha(Path(__file__)) and old.get('root')==str(root) and old.get('source_signature')==[list(v) for v in signature]:return old
    declarations={};errors=[]
    collections=[]
    for file in sorted(database.glob('*.xml')):
        try:
            doc=ET.parse(file).getroot();priority=float(doc.get('LoadingOrder',doc.get('Priority','0')))
            collections.append((priority,file,doc))
        except (ET.ParseError,ValueError) as e:errors.append({'file':str(file),'error':str(e)})
    for _,file,doc in sorted(collections,key=lambda v:(v[0],str(v[1]))):
        for node in doc.findall('DefaultProperties'):
            if not node.get('Id'):continue
            criteria=node.find('Criteria');properties=node.find('Properties')
            declarations[node.get('Id')]={'id':node.get('Id'),'base':node.get('Base'),
                'aliases':[n.text for n in criteria.findall('Name') if n.text] if criteria is not None else [],
                'type':criteria.findtext('Type') if criteria is not None else None,
                'properties':{n.tag:n.text or '' for n in properties} if properties is not None else {},
                'file':str(file),'file_sha256':sha(file)}
    resolved={}
    def resolve(id,stack=()):
        if id in resolved:return resolved[id]
        if id in stack:raise ValueError('Database inheritance cycle: '+id)
        raw=declarations[id];parent=resolve(raw['base'],stack+(id,)) if raw['base'] in declarations else {}
        props={**parent.get('properties',{}),**raw['properties']}
        row={**raw,'properties':props,'type':raw['type'] if raw['type'] is not None else parent.get('type'),
             'shape_owner':id if 'Shape' in raw['properties'] else parent.get('shape_owner')}
        resolved[id]=row;return row
    objects=[];mesh_names={p.name for p in meshes.glob('*.obj')}
    for id in declarations:
        try:
            row=resolve(id);shape=row['properties'].get('Shape');file=meshes/shape if shape else None
            objects.append({**row,'shape':shape,'mesh_exists':shape in mesh_names,
                            'model_specificity':'explicit' if row['shape_owner']==id else 'inherited_shared_shape'})
        except ValueError as e:errors.append({'id':id,'error':str(e)})
    geometry=[]
    for file in sorted(meshes.glob('*.obj')):
        lo=[float('inf')]*3;hi=[-float('inf')]*3;vertices=faces=triangles=0;groups=[]
        for line in file.read_text(encoding='utf8',errors='replace').splitlines():
            fields=line.split()
            if not fields:continue
            if fields[0]=='v' and len(fields)>=4:
                xyz=list(map(float,fields[1:4]));vertices+=1;lo=[min(a,b) for a,b in zip(lo,xyz)];hi=[max(a,b) for a,b in zip(hi,xyz)]
            elif fields[0]=='f':faces+=1;triangles+=max(0,len(fields)-3)
            elif fields[0] in ('g','o'):groups.append(' '.join(fields[1:]))
        geometry.append({'id':file.stem,'file':str(file),'sha256':sha(file),'bytes':file.stat().st_size,
                         'vertices':vertices,'faces':faces,'triangles':triangles,'groups':groups,
                         'bounds':{'min':lo,'max':hi,'span':[b-a for a,b in zip(lo,hi)]} if vertices else None})
    result={'schema_version':1,'adapter_sha256':sha(Path(__file__)),'root':str(root),'source_signature':signature,'meshes':geometry,'objects':objects,'errors':errors,
            'declared_license':'GPL-3.0 (repository LICENSE.txt)','license_file':str(root/'LICENSE.txt'),'license_sha256':sha(root/'LICENSE.txt'),
            'declared_axes':{'forward':'-Z','up':'+Y','units':'meters','documentation':'https://raia-software-inc.gitbook.io/tacview/customization/3d-models'},
            'scope':'Mesh and inherited display metadata only. Shared/fallback shapes are explicit; no inferred aerodynamic, animation, collision or damage model.'}
    target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');return result

def search(root,cache,query,limit=8):
    data=inventory(root,cache);words=[normalized(w) for w in query.split()];matches=[]
    for row in data['objects']:
        text=normalized(' '.join([row['id'],*row['aliases'],*row['properties'].values()]))
        if all(word in text for word in words):
            matches.append({'source':'tacview','id':row['id'],'name':row['properties'].get('FullName',row['id']),
                            'shape':row['shape'],'shape_owner':row['shape_owner'],'model_specificity':row['model_specificity'],'mesh_exists':row['mesh_exists']})
    return {'total':len(matches),'results':matches[:limit],'unique_meshes':len(data['meshes']),'database_objects':len(data['objects']),'parse_errors':data['errors']}

def fetch(root,cache,id,max_mb):
    data=inventory(root,cache);row=next((r for r in data['objects'] if r['id']==id),None)
    model=next((r for r in data['meshes'] if r['id']==id or row and Path(r['file']).name==row['shape']),None)
    if not model:raise ValueError('No OBJ for Tacview ID: '+id)
    source=Path(model['file']);root=Path(root).resolve()
    if not source.resolve().is_relative_to(root):raise ValueError('Tacview mesh leaves the source library')
    if model['bytes']>max_mb*1024*1024:raise ValueError('Model exceeds --max-mb')
    safe=''.join(c if c.isalnum() or c in '._-' else '_' for c in id);out=Path(cache)/'tacview'/safe;out.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,out/source.name);shutil.copy2(root/'LICENSE.txt',out/'LICENSE.txt')
    metadata={'mesh':model,'database_object':row,'source_axes':data['declared_axes'],'scope':data['scope']}
    (out/'properties.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf8')
    files=[{'path':p.name,'bytes':p.stat().st_size,'sha256':sha(p)} for p in sorted(out.iterdir()) if p.is_file() and p.name!='manifest.json']
    manifest={'source':'tacview','id':id,'source_url':'https://github.com/Vyrtuoz/Tacview','local_root':str(root),
              'license':data['declared_license'],'license_evidence':[{'file':'LICENSE.txt','sha256':sha(out/'LICENSE.txt')}],
              'entry':source.name,'files':files,'model_specificity':row['model_specificity'] if row else 'unmapped_mesh'}
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf8')
    return {'directory':str(out.resolve()),'manifest':str((out/'manifest.json').resolve()),'entry':source.name,'model_specificity':manifest['model_specificity']}
