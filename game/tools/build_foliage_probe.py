"""Freeze a bounded copy of existing tree placements for controlled material diagnosis."""
from pathlib import Path
import argparse,copy,json,shutil,sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--half-m',type=float,default=1200);p.add_argument('--retain-all',action='store_true')
    p.add_argument('--swap',nargs=2,action='append',default=[])
    p.add_argument('--opaque-red-water',action='store_true',help='Diagnostic ordinary opaque red raster material;physical water is unchanged')
    a=p.parse_args()
    scene=BakedScene(a.source);doc=scene.document;replacements=dict(a.swap)
    kept=[i for i in doc['instances'] if a.retain_all or 'ground_stems' not in i or max(abs(v) for v in i['position'][:2])<=a.half_m]
    original_count=len(doc['instances']);doc['instances']=kept;ids={i['id'] for i in kept}
    doc['environment']['decorative_instance_ids']=[id for id in doc['environment']['decorative_instance_ids'] if id in ids]
    for item in kept:
        if item['model'] in replacements:item['model']=replacements[item['model']]
    used={i['model'] for i in kept};versions={id:v for id,v in doc['resource_versions'].items() if id in used}
    for original,id in replacements.items():
        file=ASSETS/'registered'/id/'manifest.json';m=json.loads(file.read_text(encoding='utf8'))
        derivation=m.get('material_derivation') or m.get('source_normal_derivation') or {}
        if derivation.get('parent_asset')!=original:raise ValueError('Wrong appearance parent')
        versions[id]={'sha256':m['glb_sha256'],'lods':m['lods'],'manifest_sha256':sha(file)}
    doc['resource_versions']=versions
    if a.opaque_red_water:
        doc['materials']['diagnostic_opaque_water']={'id':'diagnostic-water','provider':'diagnostic constant',
            'color':[.8,.01,.01,1.],'roughness':1.,'tile_m':1.}
        for surface in doc['surfaces']:
            if surface['material']=='water':surface['material']='diagnostic_opaque_water'
    doc['foliage_probe']={'source_map_sha256':sha(a.source),'tool_sha256':sha(__file__),'half_m':None if a.retain_all else a.half_m,
        'source_instance_count':original_count,'retained_instance_count':len(kept),'material_swaps':replacements,
        'opaque_red_water_diagnostic':a.opaque_red_water,
        'scope':('Full-map material-only derivative;all instances retained.' if a.retain_all else 'Bounded diagnostic.')+
                'Retained trees keep exact positions;terrain,hydrology,contacts,roads and bridge unchanged. Optional water raster material is diagnostic only. No visual acceptance claim.'}
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    if (a.source.parent/'water-footprint.wkb').is_file():shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb')
    write_json(out/'generated-map.json',doc);BakedScene(out/'generated-map.json')
    print('FOLIAGE_PROBE',len(kept),sha(out/'generated-map.json'),flush=True)
if __name__=='__main__':main()
