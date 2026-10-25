"""Offline map authoring: create -> edit -> bake -> render -> review -> publish.

Runtime only lists/loads immutable published releases; no bake on launch.
"""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.map_library import MapLibrary,DEFAULT_CATALOG

def main():
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf8')
    p=argparse.ArgumentParser(description=__doc__);s=p.add_subparsers(dest='action',required=True)
    c=s.add_parser('create');c.add_argument('--recipe',type=Path,required=True);c.add_argument('--workspace',type=Path,required=True)
    b=s.add_parser('bake');b.add_argument('--workspace',type=Path,required=True)
    r=s.add_parser('render');r.add_argument('--map',type=Path,required=True);r.add_argument('--output',type=Path,required=True);r.add_argument('--runtime',type=Path,default=ROOT/'game/runtime-ui.json')
    r.add_argument('--visual-profile',type=Path,default=ROOT/'game/recipes/player_daylight.json');r.add_argument('--ignore-map-environment',action='store_true')
    u=s.add_parser('publish');u.add_argument('--map',type=Path,required=True);u.add_argument('--name',required=True);u.add_argument('--label',required=True);u.add_argument('--review',type=Path,required=True);u.add_argument('--catalog',type=Path,default=DEFAULT_CATALOG)
    u.add_argument('--storage-root',help='Named absolute directory from catalog storage_roots; stages and freezes the release on that volume')
    l=s.add_parser('list');l.add_argument('--catalog',type=Path,default=DEFAULT_CATALOG)
    v=s.add_parser('verify');v.add_argument('id');v.add_argument('--catalog',type=Path,default=DEFAULT_CATALOG)
    x=s.add_parser('recover');x.add_argument('--staging',type=Path,required=True);x.add_argument('--catalog',type=Path,default=DEFAULT_CATALOG)
    a=p.parse_args()
    if a.action=='list':result=MapLibrary(a.catalog).versions()
    elif a.action=='verify':result=MapLibrary(a.catalog).resolve(a.id)
    elif a.action=='render':
        command=[sys.executable,str(ROOT/'game/tools/capture_reference_map.py'),'--map',str(a.map),'--output',str(a.output),'--runtime',str(a.runtime),'--visual-profile',str(a.visual_profile)]
        if a.ignore_map_environment:command.append('--ignore-map-environment')
        subprocess.run(command,check=True);return
    else:
        from bvr_game.map_authoring import create_workspace,bake,publish,finish_release
        if a.action=='create':result={'recipe':str(create_workspace(a.workspace,a.recipe))}
        elif a.action=='bake':result=bake(a.workspace)
        elif a.action=='recover':result=finish_release(a.staging,a.catalog)
        else:result=publish(a.map,a.catalog,name=a.name,label=a.label,review=a.review,storage_root=a.storage_root)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
