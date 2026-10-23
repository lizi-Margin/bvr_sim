"""Agent resource pipeline: register/inspect/place; search/fetch via asset_library.py."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;GAME=HERE.parent
BLENDER=r'C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe'
def inspect(asset_id):
    root=GAME/'assets/registered'/asset_id;m=json.loads((root/'manifest.json').read_text(encoding='utf8'))
    path=root/m['file']
    if hashlib.sha256(path.read_bytes()).hexdigest()!=m['glb_sha256']:raise ValueError('Asset hash mismatch: '+asset_id)
    if m['faces']>100000:raise ValueError('Asset exceeds prototype face budget')
    return m
def main():
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    r=s.add_parser('register');r.add_argument('id');r.add_argument('--entry',type=Path,required=True);r.add_argument('--manifest',type=Path,required=True);r.add_argument('--blender',default=BLENDER)
    i=s.add_parser('inspect');i.add_argument('id')
    a=s.add_parser('place');a.add_argument('id');a.add_argument('--map',type=Path,default=GAME/'maps/training.json');a.add_argument('--name',required=True);a.add_argument('--position',nargs=3,type=float,required=True);a.add_argument('--scale',type=float,default=1)
    args=p.parse_args()
    if args.action=='register':
        if not args.id.replace('_','').replace('-','').isalnum():raise ValueError('Invalid asset id')
        subprocess.run([args.blender,'--background','--python-exit-code','1','--python',str(HERE/'convert_environment.py'),'--',str(args.entry),str(args.manifest),args.id,str(GAME/'assets/registered'/args.id)],check=True,stdout=sys.stderr)
    m=inspect(args.id)
    if args.action in ('register','place'):
        runtime=GAME/'runtime.json';r=json.loads(runtime.read_text(encoding='utf8'));r['models'][args.id]=str((GAME/'assets/registered'/args.id/m['file']).resolve());runtime.write_text(json.dumps(r,indent=2),encoding='utf8')
    if args.action=='place':
        if args.scale<=0:raise ValueError('Asset scale must be positive')
        scene=json.loads(args.map.read_text(encoding='utf8'));scene.setdefault('assets',[])
        if any(o['id']==args.name for o in scene['assets']):raise ValueError('Duplicate placement id')
        scene['assets'].append({'id':args.name,'model':args.id,'position':args.position,'scale':args.scale});scene['version']+=1
        args.map.write_text(json.dumps(scene,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(m,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
