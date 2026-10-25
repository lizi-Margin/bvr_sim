"""Create a local registered foliage material variant without touching mesh/image bytes."""
from pathlib import Path
import argparse,copy,hashlib,json,struct,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json

def derive(asset,id,specular):
    if not 0<=specular<=1:raise ValueError('Specular factor must be in[0,1]')
    import re
    if not re.fullmatch('[A-Za-z0-9_-]+',id):raise ValueError('Invalid registered asset ID')
    source=ASSETS/'registered'/asset;manifest=json.loads((source/'manifest.json').read_text(encoding='utf8'))
    target=ASSETS/'registered'/id;target.mkdir(exist_ok=False);result=copy.deepcopy(manifest);evidence=[]
    for level,lod in enumerate(result['lods']):
        file=source/lod['file']
        if sha(file)!=lod['sha256']:raise ValueError('Parent registered LOD changed')
        raw=file.read_bytes();length=struct.unpack_from('<I',raw,12)[0];doc=json.loads(raw[20:20+length]);original=copy.deepcopy(doc)
        changed=[]
        for material in doc['materials']:
            if not material['name'].startswith('tree_oak_branches'):continue
            material.setdefault('extensions',{})['KHR_materials_specular']={'specularFactor':float(specular)}
            changed.append(material['name'])
        if not changed:raise ValueError('No declared original oak leaf material found')
        doc['extensionsUsed']=sorted(set(doc.get('extensionsUsed',[]))|{'KHR_materials_specular'})
        for key in set(original)|set(doc):
            if key not in ('materials','extensionsUsed'):assert doc[key]==original[key]
        payload=json.dumps(doc,separators=(',',':')).encode();payload+=b' '*(-len(payload)%4);binary=raw[20+length:]
        output=target/(id+('' if level==0 else '_lod'+str(level))+'.glb')
        output.write_bytes(struct.pack('<III',0x46546c67,2,20+len(payload)+len(binary))+struct.pack('<II',len(payload),0x4e4f534a)+payload+binary)
        lod.update(file=output.name,sha256=sha(output))
        evidence.append({'level':level,'source_file':str(file),'source_sha256':sha(file),'output_sha256':sha(output),
            'unchanged_binary_sha256':hashlib.sha256(binary).hexdigest(),'leaf_materials':changed})
    result.update(id=id,name=manifest['name']+'; leaf specular '+str(specular),file=result['lods'][0]['file'],glb_sha256=result['lods'][0]['sha256'])
    result['material_derivation']={'parent_asset':asset,'parent_manifest_sha256':sha(source/'manifest.json'),
        'tool_sha256':sha(__file__),'specular_factor':specular,'evidence':evidence,
        'scope':'Only leaf KHR_materials_specular changes. Mesh/accessor/node/UV/normal/image data and complete GLB binary chunk unchanged. Diagnostic artistic parameter,not measured leaf BRDF.'}
    write_json(target/'manifest.json',result);return {'id':id,'manifest':str(target/'manifest.json'),'sha256':sha(target/'manifest.json')}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--asset',required=True);p.add_argument('--id',required=True)
    p.add_argument('--specular-factor',type=float,required=True);a=p.parse_args();print(json.dumps(derive(a.asset,a.id,a.specular_factor)),flush=True)
if __name__=='__main__':main()
