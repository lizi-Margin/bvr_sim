"""Agent resource pipeline: register/inspect/place; search/fetch via asset_library.py."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;GAME=HERE.parent
BLENDER=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
def inspect(asset_id):
    root=GAME/'assets/registered'/asset_id;m=json.loads((root/'manifest.json').read_text(encoding='utf8'))
    path=root/m['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=m['glb_sha256']:raise ValueError('Asset hash mismatch: '+asset_id)
    for lod in m.get('lods',[]):
        file=(root/lod['file']).resolve()
        if not file.is_relative_to(root.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest()!=lod['sha256']:
            raise ValueError('Asset LOD path/hash mismatch: '+asset_id)
    for materials in m.get('source_card_mips',{}).get('materials_by_lod_file',{}).values():
        for slots in materials.values():
            for item in slots.values():
                path=(root/item['file']).resolve()
                if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:raise ValueError('Source card mip sidecar mismatch: '+asset_id)
    if m['faces']>100000:raise ValueError('Asset exceeds prototype face budget')
    return m
def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    r=s.add_parser('register');r.add_argument('id');r.add_argument('--entry',type=Path,required=True);r.add_argument('--manifest',type=Path,required=True);r.add_argument('--blender',default=BLENDER)
    r.add_argument('--recipe',type=Path,help='Optional source-object selection, explicit height and LOD/impostor conversion policy')
    i=s.add_parser('inspect');i.add_argument('id')
    d=s.add_parser('mip-variant');d.add_argument('id');d.add_argument('--source',required=True);d.add_argument('--maximum-alpha-control',action='store_true')
    a=s.add_parser('place');a.add_argument('id');a.add_argument('--map',type=Path,default=GAME/'maps/training.json');a.add_argument('--name',required=True);a.add_argument('--position',nargs=3,type=float,required=True);a.add_argument('--scale',type=float,default=1)
    args=p.parse_args()
    if args.action=='mip-variant':
        sys.path.insert(0,str(GAME.parent));from bvr_game.card_mips import derive
        derive(args.source,args.id,maximum_alpha=args.maximum_alpha_control)
    if args.action=='register':
        if not args.id.replace('_','').replace('-','').isalnum():raise ValueError('Invalid asset id')
        command=[args.blender,'--background','--python-exit-code','1','--python',str(HERE/'convert_environment.py'),'--',str(args.entry),str(args.manifest),args.id,str(GAME/'assets/registered'/args.id)]
        if args.recipe:command.append(str(args.recipe.resolve()))
        subprocess.run(command,check=True,stdout=sys.stderr)
    m=inspect(args.id)
    if args.action in ('register','place','mip-variant'):
        runtime=GAME/'runtime.json';r=json.loads(runtime.read_text(encoding='utf8'));r['models'][args.id]=str((GAME/'assets/registered'/args.id/m['file']).resolve());runtime.write_text(json.dumps(r,indent=2),encoding='utf8')
        if args.action=='mip-variant':
            for lod in m['lods']:r['models'][args.id+('' if lod['level']==0 else '::lod1')]=str((GAME/'assets/registered'/args.id/lod['file']).resolve())
            runtime.write_text(json.dumps(r,indent=2),encoding='utf8')
            inventory=[json.loads(p.read_text(encoding='utf8')) for p in (GAME/'assets/registered').glob('*/manifest.json') if p.parent.name!='audio']
            (GAME/'assets/catalog.json').write_text(json.dumps({'schema_version':2,'assets':inventory},indent=2),encoding='utf8')
    if args.action=='place':
        if args.scale<=0:raise ValueError('Asset scale must be positive')
        scene=json.loads(args.map.read_text(encoding='utf8'));scene.setdefault('assets',[])
        if any(o['id']==args.name for o in scene['assets']):raise ValueError('Duplicate placement id')
        scene['assets'].append({'id':args.name,'model':args.id,'position':args.position,'scale':args.scale});scene['version']+=1
        args.map.write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
