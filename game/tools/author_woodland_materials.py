"""Offline ground-color authoring for the explicitly authored source-terrain biome."""
from pathlib import Path
import argparse,copy,hashlib,json,math,shutil,sys
import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates
from shapely import from_wkb,contains_xy
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import ASSETS,sha,write_json
from bvr_game.scene_runtime import BakedScene
from bvr_game.source_macro import to_linear,to_srgb
from bvr_game.source_woodland import protected_footprints
from bvr_game.authored_canopy import woodland_mask,validate_policy
from bvr_game.open_ground import OpenGround
from bvr_game.ground_color_mix import filtered_landcover


def geometry(document):
    return {'height_sha256':document['terrain']['sha256'],
        'tiles':[{k:v for k,v in t.items() if k!='material'} for t in [document['terrain']['base'],*document['terrain']['details']]],
        'physical_environment_sha256':hashlib.sha256(json.dumps({k:document['environment'][k] for k in ['contact_surfaces','water_regions','obstacles']},sort_keys=True,separators=(',',':')).encode()).hexdigest()}


def bake(a):
    scene=BakedScene(a.source);doc=scene.document;policy=json.loads(a.policy.read_text(encoding='utf8'));validate_policy(policy)
    if policy.get('roads') and doc.get('source_road_bake',{}).get('policy_sha256')!=sha(a.policy):raise ValueError('Ground biome requires the matching saved road plan')
    populated=any('ground_stems' in item for item in doc['instances'])
    if populated:
        if not getattr(a,'retain_populated_layout',False):raise ValueError('Material template must be the unpopulated source terrain')
        saved=doc['source_woodland_bake']['authored_biome']
        if saved['sha256']!=sha(a.policy) or saved['policy']!=policy or doc['source_woodland_bake']['half_m']!=a.half_m:
            raise ValueError('Retained trees require the exact saved biome policy and extent')
    manifest=json.loads((ASSETS/'registered'/a.large_asset/'manifest.json').read_text(encoding='utf8'))
    radius=max(math.hypot(x,y) for b in manifest['cluster']['ground_conform']['tree_bounds_relative_blender'] for x in [b['min'][0],b['max'][0]] for y in [b['min'][1],b['max'][1]])*1.35
    footprint_doc=dict(doc,instances=[i for i in doc['instances'] if 'ground_stems' not in i])
    forbidden=protected_footprints(footprint_doc,from_wkb((a.source.parent/'water-footprint.wkb').read_bytes()),radius,shore_root_clearance_m=policy.get('shore_root_clearance_m'),road_root_clearance_m=policy.get('road_root_clearance_m'))
    report=json.loads(a.textures.read_text(encoding='utf8'));item=next(x for x in report['textures'] if x['status']=='decoded' and Path(x['source']).stem=='air_smolensk_forest_a')
    if sha(item['png'])!=item['png_sha256']:raise ValueError('Original forest color changed')
    forest=to_linear(Image.open(item['png']).convert('RGB'))
    ground=OpenGround(a.open_ground_policy) if a.open_ground_policy else None
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);materials={};inputs=[]
    focus=doc['terrain']['details'][0];extent=(focus['columns']-1)*focus['spacing']
    for name,file,origin,size in [('source_macro',Path(doc['materials']['source_macro']['base_color']),[-65536,-65536],131072),
        ('source_focus',a.focus_color,[focus['origin_north'],focus['origin_west']],extent)]:
        image=np.asarray(Image.open(file).convert('RGB'));height,width=image.shape[:2]
        if height!=width:raise ValueError('Source color region must be square')
        result=np.empty_like(image);axis=origin[0]+(np.arange(width)+.5)*size/width
        def mask_at(n,w):return woodland_mask(n,w,policy)&(abs(n)<a.half_m)&(abs(w)<a.half_m)&~contains_xy(forbidden,n,w)
        coverage=None;transition=getattr(a,'forest_transition_m',0.)
        if transition:
            original_mask=np.empty((height,width),dtype=np.uint8)
            for first in range(0,height,32):
                west=origin[1]+(np.arange(first,min(first+32,height))+.5)*size/height;n,w=np.meshgrid(axis,west)
                original_mask[first:first+len(west)]=mask_at(n,w)
            coverage=filtered_landcover(original_mask,size/width,transition);del original_mask
        for first in range(0,height,32):
            west=origin[1]+(np.arange(first,min(first+32,height))+.5)*size/height
            n,w=np.meshgrid(axis,west)
            mask=mask_at(n,w) if coverage is None else coverage[first:first+len(west)]
            # Same original forest tile UV as the source class. Color changes
            # only inside the saved authored biome; no new terrain relief.
            u=np.mod(-w/2048,1)*forest.shape[1]-.5;v=np.mod(-n/2048,1)*forest.shape[0]-.5
            color=np.stack([map_coordinates(forest[...,c],[v,u],order=1,mode='grid-wrap',prefilter=False) for c in range(3)],axis=-1)
            if coverage is None:
                background=to_srgb(ground.color_linear(n,w)) if ground else image[first:first+len(west)]
                result[first:first+len(west)]=np.where(mask[...,None],to_srgb(color),background)
            else:
                background=ground.color_linear(n,w) if ground else to_linear(image[first:first+len(west)])
                result[first:first+len(west)]=to_srgb(color*mask[...,None]+background*(1-mask[...,None]))
            if first%1024==0:print('AUTHORED_COLOR_ROWS',name,first,'/',height,flush=True)
        path=out/(name+'-authored-canopy.png');Image.fromarray(result).save(path)
        material=copy.deepcopy(doc['materials']['source_macro']);material.update(id='authored-'+name,base_color=str(path),base_color_sha256=sha(path),
            tile_m=size,uv_origin_north=origin[0],uv_origin_west=origin[1],repeat_detail=True)
        if ground:material['ground_detail']=ground.detail
        materials[name]=material;inputs.append({'file':str(file.resolve()),'sha256':sha(file)})
    if getattr(a,'road_shoulder_policy',None):
        detail=copy.deepcopy(json.loads(a.road_shoulder_policy.read_text(encoding='utf8'))['road_shoulder'])
        for slot in ['base_color','normal','roughness_map']:
            if sha(detail[slot])!=detail[slot+'_sha256']:raise ValueError('Road shoulder source changed')
        mean=to_linear(Image.open(detail['base_color']).convert('RGB')).mean(axis=(0,1),dtype=np.float64)
        detail.update(tile_m=2.,strength=.55,mean_linear_luminance=float(mean@np.array([.2126,.7152,.0722])))
        shoulder=copy.deepcopy(materials['source_macro']);shoulder.update(id='authored-road-shoulder',ground_detail=detail,
            provider='Authored ground macro with real CC0 gravel microdetail',distribution_allowed=False,
            scope='Existing shoulder geometry,global ground macro for continuous color,real gravel detail at2m;not entirelyCC0 because retained source forest color participates in macro.')
        materials['road_shoulder']=shoulder
    write_json(out/'materials.json',{'materials':materials,'geometry':geometry(doc),'biome_policy':policy,'biome_policy_sha256':sha(a.policy),
        'biome_helper_sha256':sha(ROOT/'bvr_game/authored_canopy.py'),'footprint_helper_sha256':sha(ROOT/'bvr_game/source_woodland.py'),
        'half_m':a.half_m,'clearance_radius_m':radius,'large_asset':a.large_asset,'large_manifest_sha256':sha(ASSETS/'registered'/a.large_asset/'manifest.json'),
        'source_colors':inputs+[{'file':item['png'],'sha256':item['png_sha256']}],'tool_sha256':sha(__file__),
        'open_ground':ground.provenance if ground else None,
        'forest_transition_m':getattr(a,'forest_transition_m',0.),
        'scope':'Authored land-use overlay using retained original forest color/UV and the same world-space clearings as planted trees. Original physical terrain and water unchanged;not original Smolensk land use or the full source shader.'})
    print('AUTHORED_MATERIALS_COMPLETE',out/'materials.json',flush=True)


def compose(a):
    bundle=json.loads(a.materials.read_text(encoding='utf8'));scene=BakedScene(a.source);doc=copy.deepcopy(scene.document)
    if geometry(doc)!=bundle['geometry']:raise ValueError('Material bundle requires the same source height,tiles and physical environment')
    forest=doc['source_woodland_bake'];biome=forest['authored_biome']
    if not biome or biome['sha256']!=bundle['biome_policy_sha256'] or biome['policy']!=bundle['biome_policy'] or forest['half_m']!=bundle['half_m']:
        raise ValueError('Tree and ground authored biomes differ')
    if biome['helper_sha256']!=bundle.get('biome_helper_sha256') or forest['helper_sha256']!=bundle.get('footprint_helper_sha256'):
        raise ValueError('Tree and ground authoring helper versions differ;rebake the ground bundle')
    if bundle['large_asset'] not in doc['resource_versions'] or doc['resource_versions'][bundle['large_asset']]['manifest_sha256']!=bundle['large_manifest_sha256']:
        raise ValueError('Ground clearance uses a different source grove')
    for mat in bundle['materials'].values():
        for layer in [mat]+([mat['ground_detail']] if mat.get('ground_detail') else []):
            for slot in ['base_color','normal','roughness_map']:
                if layer.get(slot) and sha(layer[slot])!=layer[slot+'_sha256']:raise ValueError('Authored ground source changed: '+slot)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    doc['materials'].update(bundle['materials'])
    for tile in doc['terrain']['details']:tile['material']='source_focus'
    shutil.copy2(scene.height_file,out/'terrain.npz');doc['terrain']['file']='terrain.npz'
    for key in ['instances','surfaces','mission','environment','roads','rivers','airfields','settlements']:assert doc[key]==scene.document[key],key
    doc['authored_canopy_materials']={'bundle':str(a.materials.resolve()),'sha256':sha(a.materials),'source_map_sha256':sha(a.source),'tool_sha256':sha(__file__),'scope':bundle['scope']}
    write_json(out/'generated-map.json',doc)
    recipe=json.loads((a.source.parent/'scene-recipe.json').read_text(encoding='utf8'));recipe['authored_canopy_materials']=doc['authored_canopy_materials'];write_json(out/'scene-recipe.json',recipe)
    shutil.copy2(a.source.parent/'water-footprint.wkb',out/'water-footprint.wkb')
    BakedScene(out/'generated-map.json')
    write_json(out/'candidate.json',{'map':str(out/'generated-map.json'),'sha256':sha(out/'generated-map.json'),'status':'requires_actual_visual_and_grounding_review'})
    print('AUTHORED_CANOPY_MAP_COMPLETE',out/'generated-map.json',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    b=sub.add_parser('bake')
    for name in ['source','policy','textures','focus-color','output']:b.add_argument('--'+name,type=Path,required=True)
    b.add_argument('--large-asset',required=True);b.add_argument('--half-m',type=int,default=40000)
    b.add_argument('--open-ground-policy',type=Path,help='Pinned real grass/dry-ground mixture instead of photo-city source patches in clearings')
    b.add_argument('--retain-populated-layout',action='store_true',help='Repaint an existing saved forest without changing any placements')
    b.add_argument('--forest-transition-m',type=float,default=0.,help='Ground-color coverage prefilter only;planting mask remains unchanged')
    b.add_argument('--road-shoulder-policy',type=Path,help='Pinned real gravel PBR on the existing shoulder mesh with continuous ground macro')
    c=sub.add_parser('compose')
    for name in ['source','materials','output']:c.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args()
    if a.command=='bake':
        if not 1000<=a.half_m<=40000:raise ValueError('Authored biome half extent must fit the source atlas')
        bake(a)
    else:compose(a)
if __name__=='__main__':main()
