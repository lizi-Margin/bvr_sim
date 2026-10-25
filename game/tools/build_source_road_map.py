"""Offline authored roads and an original-source bridge on shared source terrain."""
from pathlib import Path
import argparse,copy,json,math,shutil,sys
import numpy as np
from shapely import from_wkb,union_all
from shapely.geometry import LineString,Polygon,MultiPoint
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json,registered_version
from bvr_game.scene_runtime import BakedScene
from bvr_game.road_authoring import drape_polygon,scene_heights,placed_blender_points,drape_on_mesh


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['source','policy','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();scene=BakedScene(a.source);doc=copy.deepcopy(scene.document);policy=json.loads(a.policy.read_text())
    if sha(a.source)!=policy['source_map_sha256']:raise ValueError('Road plan belongs to different terrain')
    if any('ground_stems' in i for i in doc['instances']):raise ValueError('Author roads before populating the canopy')
    water=from_wkb((a.source.parent/'water-footprint.wkb').read_bytes());bridge=policy['bridge'];asset=bridge['model']
    manifest=json.loads((ASSETS/'registered'/asset/'manifest.json').read_text());deck_file=Path(bridge['source_deck'])
    if sha(deck_file)!=bridge['source_deck_sha256']:raise ValueError('Original bridge deck changed')
    deck=json.loads(deck_file.read_text());points=np.asarray(deck['vertices']);scale=bridge['scale'];cn,cw=bridge['center_nwu']
    minimum_n,maximum_n=points[:,1].min()*scale,points[:,1].max()*scale
    bank=scene_heights(scene,np.array([cn+minimum_n,cn+maximum_n]),cw)
    slope=float((bank[1]-bank[0])/(maximum_n-minimum_n));up=np.array([0.,1.,-slope]);up/=np.linalg.norm(up)
    end_z=np.mean(points[(points[:,1]<points[:,1].min()+.1)|(points[:,1]>points[:,1].max()-.1),2])*scale
    height=float(bank.mean()-end_z*up[1]);box=manifest['bounds_blender'];radius=math.hypot(box['span'][0],box['span'][1])*scale/2
    item={'id':bridge['id'],'model':asset,'category':'prop','zone':'authored_river_bridge','position':[cn,cw,height],'scale':scale,'yaw':0.,'up_normal':up.tolist(),
        'chunk':f'{math.floor(cn/doc["chunk_m"])}:{math.floor(cw/doc["chunk_m"])}','radius_m':radius,'lod_distance':200000.,'cull_distance':200000.,
        'collision_type':'Original road-deck triangles only;railings/piers have no volume collider'}
    corners=[[x,y,0] for x in [box['min'][0],box['max'][0]] for y in [box['min'][1],box['max'][1]]]
    item['canopy_footprint']=list(map(list,MultiPoint(placed_blender_points(corners,item)[:,:2]).convex_hull.exterior.coords))
    world_deck=placed_blender_points(points,item);deck_foot=union_all([Polygon(world_deck[np.asarray(deck['indices']).reshape(-1,3)[i],:2]) for i in range(len(deck['indices'])//3)])
    if not deck_foot.covers(water.intersection(LineString(policy['roads'][-1]['points']))):raise ValueError('Source bridge deck does not cover the complete wet crossing')
    doc['instances'].append(item);doc['chunks'].setdefault(item['chunk'],[]).append(item['id']);doc['counts']['prop']+=1
    version=registered_version(asset,manifest);version['manifest_sha256']=sha(ASSETS/'registered'/asset/'manifest.json');doc['resource_versions'][asset]=version
    doc['environment']['contact_surfaces'].append({'id':'original_bridge_deck','material':'pavement','vertices':world_deck.tolist(),'indices':deck['indices'],'drivable':True})
    # Actual downloaded PBR channels are declared and hash checked in the plan.
    for name,material in policy['road_materials'].items():
        for slot in ['base_color','normal','roughness_map']:
            if sha(material[slot])!=material[slot+'_sha256']:raise ValueError('Road source texture changed: '+slot)
        doc['materials'][name]=copy.deepcopy(material)
    doc['materials']['road_marking']={'color':[.72,.70,.61,1],'roughness':.9,'tile_m':1.,'provider':'authored road paint','id':'matte-road-edge-paint'}
    contact_triangles=0;road_area=0.;surfaces=[]
    for road in policy['roads']:
        line=LineString(road['points']);road_area+=line.length*road['width_m']
        for role,width,material,bias in [('shoulder',road['width_m']+2*road['shoulder_m'],'road_shoulder',.015),('surface',road['width_m'],road['material'],.030)]:
            footprint=line.buffer(width/2,cap_style='flat',join_style='round').difference(water.buffer(.5)).difference(deck_foot)
            vertices,indices=drape_polygon(scene,footprint,bias)
            surface={'id':road['id']+'_'+role,'material':material,'vertices':vertices,'indices':indices,'drivable':role=='surface'};surfaces.append(surface)
            if role=='surface':
                doc['environment']['contact_surfaces'].append({**surface,'material':'pavement' if road['material']=='road_asphalt' else 'soil'})
                contact_triangles+=len(indices)//3
            print('ROAD_DRAPED',surface['id'],len(indices)//3,flush=True)
        if road['material']=='road_asphalt':
            for side in [-1,1]:
                paint=line.offset_curve(side*(road['width_m']/2-.45)).buffer(.10,cap_style='flat')
                paint=paint.difference(water.buffer(.5)).difference(deck_foot)
                vertices,indices=drape_polygon(scene,paint,.034)
                surfaces.append({'id':road['id']+'_edge_'+str(side),'material':'road_marking','vertices':vertices,'indices':indices,'drivable':False})
    # Bridge edge paint uses the original curved source-deck planes.
    for side in [-1,1]:
        paint=LineString([[cn+minimum_n,cw+side*6.55],[cn+maximum_n,cw+side*6.55]]).buffer(.10,cap_style='flat')
        vertices,indices=drape_on_mesh(world_deck[np.asarray(deck['indices']).reshape(-1,3)],paint)
        surfaces.append({'id':'bridge_edge_'+str(side),'material':'road_marking','vertices':vertices,'indices':indices,'drivable':False})
    doc['surfaces'].extend(surfaces);doc['roads']=copy.deepcopy(policy['roads']);doc['environment']['decorative_instance_ids'].append(item['id'])
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    for key in ['base','details']:
        assert doc['terrain'][key]==scene.document['terrain'][key]
    for key in ['mission','airfields','settlements']:assert doc[key]==scene.document[key]
    for key in ['water_regions','obstacles']:assert doc['environment'][key]==scene.document['environment'][key]
    doc['source_road_bake']={'policy_file':str(a.policy.resolve()),'policy_sha256':sha(a.policy),'source_map_sha256':sha(a.source),
        'tool_sha256':sha(__file__),'helper_sha256':sha(ROOT/'bvr_game/road_authoring.py'),'road_contact_triangles':contact_triangles,'road_surface_area_m2':road_area,
        'bridge':{'placement':item,'source_deck':str(deck_file),'source_deck_sha256':sha(deck_file),'original_deck_triangles':len(deck['indices'])//3,'bank_heights_m':bank.tolist(),
            'scope':'Uniform half-scale originalLOD0 bridge,small authored tilt/base to meet actual banks;contact uses exactly its original upward road-material triangles. Railings/piers are visual geometry without volume collision.'},
        'scope':'Saved authored roads clipped against actual indexed terrain planes,one source bridge and shared road/deck contact triangles. Original heights and hydrology unchanged. Not original Smolensk roads or a completed ground-driving map.'}
    write_json(out/'generated-map.json',doc);shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb')
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text());recipe['source_road_bake']=doc['source_road_bake'];recipe['resource_use']['asset_manifest_sha256'][asset]=sha(ASSETS/'registered'/asset/'manifest.json');write_json(out/'scene-recipe.json',recipe)
    BakedScene(out/'generated-map.json');write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'roads':doc['source_road_bake'],'status':'requires_actual_bridge_and_road_review'})
    print('SOURCE_ROAD_MAP_BUILT',out/'generated-map.json',flush=True)
if __name__=='__main__':main()
