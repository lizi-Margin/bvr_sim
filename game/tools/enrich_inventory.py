"""Inspect existing GLBs without changing their geometry or material payloads."""
from pathlib import Path
import hashlib,json,struct,io
from PIL import Image
ROOT=Path(__file__).resolve().parents[2];ASSETS=ROOT/'game/assets'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
for id in ['F22','F16','road_barrier']:
    directory=ASSETS/'registered'/id;path=directory/'manifest.json';m=json.loads(path.read_text());data=(directory/m['file']).read_bytes()
    if sha(directory/m['file'])!=m['glb_sha256']:raise ValueError('Registered GLB changed '+id)
    length=struct.unpack_from('<I',data,12)[0];document=json.loads(data[20:20+length]);binary_offset=20+length+8;binary=data[binary_offset:]
    m['name']=id;m['tags']=['aircraft','flightgear'] if id!='road_barrier' else ['prop','concrete','polyhaven']
    m['original_file_sha256']=m['source_sha256'];m['original_axes']='AC3D -X nose, +Z up; reviewed -90 degree Blender Z rotation' if id!='road_barrier' else 'glTF RH +Y up'
    m['vertices']=sum(document['accessors'][p['attributes']['POSITION']]['count'] for mesh in document['meshes'] for p in mesh['primitives'])
    m['triangles']=sum(document['accessors'][p['indices']]['count']//3 for mesh in document['meshes'] for p in mesh['primitives'])
    m['materials']=document.get('materials',[]);m['textures']=[]
    for index,image in enumerate(document.get('images',[])):
        if 'bufferView' not in image:raise ValueError('Registered GLB contains an external image')
        view=document['bufferViews'][image['bufferView']];offset=view.get('byteOffset',0);payload=binary[offset:offset+view['byteLength']]
        with Image.open(io.BytesIO(payload)) as decoded:size=list(decoded.size)
        m['textures'].append({'index':index,'name':image.get('name','image_'+str(index)),'sha256':hashlib.sha256(payload).hexdigest(),'dimensions':size,'mime_type':image.get('mimeType')})
    m['lods']=[{'level':0,'file':m['file'],'sha256':m['glb_sha256'],'vertices':m['vertices'],'triangles':m['triangles'],'bounds':m['bounds_blender']}]
    m['recommended_use']='player or opponent aircraft' if id!='road_barrier' else 'near-field concrete barrier'
    m['recommended_density_per_km2']=1 if id!='road_barrier' else 20;m['collision_type']='simulation aircraft' if id!='road_barrier' else 'box';m['instancing_allowed']=True
    if id=='F16':
        notice=Path(m['source']).parents[1]/'LICENSE';m['license']='GPL-2.0';m['license_evidence']=[{'file':str(notice),'sha256':sha(notice)}];m['distribution_allowed']=True;m['distribution_conditions']='Retain package authors/notices and corresponding editable sources; not CC0.'
    elif id=='F22':
        notice=Path(m['source']).parent/'F-22-JSBSIM-Model-File.xml';m['license_evidence']=[{'file':str(notice),'sha256':sha(notice)}];m['distribution_allowed']=False;m['distribution_conditions']='Local existing package only. Linked model XML declares GPL-2.0; separate AC3D mesh/texture coverage requires confirmation before redistribution.'
    else:m['distribution_allowed']=True;m['license_evidence']=[{'url':'https://polyhaven.com/license','declaration':'CC0 provider; original fetch manifest retained'}]
    path.write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf8')
inventory=[json.loads(p.read_text(encoding='utf8')) for p in sorted((ASSETS/'registered').glob('*/manifest.json')) if p.parent.name!='audio']
(ASSETS/'catalog.json').write_text(json.dumps({'schema_version':2,'assets':inventory},ensure_ascii=False,indent=2),encoding='utf8')
print('INSPECTED',len(inventory),'models; GLB payloads unchanged')
