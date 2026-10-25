"""Derive a saved map by extending actual source bridge foot rings into terrain."""
from pathlib import Path
import argparse,copy,json,shutil,sys
from shapely.geometry import Polygon
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.bridge_footings import source_bottom_components,extend_footing


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    scene=BakedScene(a.source);doc=copy.deepcopy(scene.document)
    if doc.get('bridge_footing_bake'):raise ValueError('Source map already has footing extensions')
    item=doc['source_road_bake']['bridge']['placement'];version=doc['resource_versions'][item['model']];model=ASSETS/'registered'/item['model']/version['lods'][0]['file']
    if sha(model)!=version['lods'][0]['sha256']:raise ValueError('Registered bridge model changed')
    parts=source_bottom_components(model);extensions=[]
    for index,points in enumerate(parts):
        extension=extend_footing(scene,points,item,'source_pier_footing_'+str(index))
        if extension is None:continue
        if not Polygon(item['canopy_footprint']).buffer(.01).covers(Polygon(extension['footprint'])):raise ValueError('Footing leaves the existing bridge canopy exclusion')
        extensions.append(extension);doc['surfaces'].append(extension['surface']);doc['environment']['obstacles'].append(extension['obstacle'])
    if not extensions:raise ValueError('No floating source foot rings require extension')
    doc['materials']['bridge_footing']={'id':'source-pier-continuation','provider':'authored continuation of source pier footprint','color':[.36,.36,.34,1],'roughness':.9,'tile_m':1.}
    for key in ['instances','roads','mission','chunks','resource_versions']:assert doc[key]==scene.document[key]
    for key in ['contact_surfaces','water_regions','decorative_instance_ids']:assert doc['environment'][key]==scene.document['environment'][key]
    assert doc['terrain']==scene.document['terrain']
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    doc['bridge_footing_bake']={'source_map_sha256':sha(a.source),'registered_model_sha256':sha(model),'tool_sha256':sha(__file__),
        'helper_sha256':sha(ROOT/'bvr_game/bridge_footings.py'),'source_bottom_components':len(parts),'extensions':extensions,
        'scope':'Original bridge upper geometry,all trees,materials,terrain,road/deck contacts and hydrology retained. Source foot-ring continuations and conservative static boxes added wholly inside existing bridge canopy exclusion;not full upper-pier/railing collision certification.'}
    write_json(out/'generated-map.json',doc);recipe=json.loads((a.source.parent/'scene-recipe.json').read_text());recipe['bridge_footing_bake']=doc['bridge_footing_bake'];write_json(out/'scene-recipe.json',recipe)
    shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb');BakedScene(out/'generated-map.json')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'source_bottom_components':len(parts),'extensions':len(extensions),'status':'requires_actual_footing_and_whole_map_review'})
    print('SOURCE_FOOTINGS_EXTENDED',len(extensions),out/'generated-map.json',flush=True)
if __name__=='__main__':main()
