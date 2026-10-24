"""Create/bake the river-valley airfield through the existing registered Baker."""
from pathlib import Path
import argparse,json,sys,hashlib,shutil,uuid
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from bvr_game.content import write_json

def recipe(forest_asset='fir_grove_cards_c',forest_floor_only=False):
    r=json.loads((ROOT/'game/recipes/training_range_v3.json').read_text(encoding='utf-8'))
    r.update(name='river_valley_airfield',seed=3124,height_spacing_m=25,field_spacing_m=750,
        field_palette_linear=[[.88,.87,.71,1],[.76,.84,.67,1],[.91,.83,.67,1],[.67,.77,.61,1]])
    r['landscape']={'version':1,'feature_extent_km':[8,8],'feature_center':[-1000,-2200],
        'valley_base_rise_m':95,'valley_scale_m':1800,'ridge_amplitude_m':450,'ridge_start_m':2200,
        'ridge_scale_m':6000,'undulation_m':35,'earthwork_blend_m':180,'regional_transition_m':1200,'macro_resolution':4096,
        'generator':'Seeded river valley and local runway/apron earthworks; source BVR terrain retained beyond20km focus',
        'field_layout':'warped_merged_parcels','water_render_chunk_m':500,
        'field_layout_note':'Seeded shared warped block edges with merged parcels and T junctions; authored agricultural appearance, not measured GIS',
        'individual_building_tuning':'Road frontages and source-bound footprint foundations; no region-wide settlement/industry flattening'}
    r['terrain']['airport_height_m']=220
    r['budgets']['vegetation_instances']=20000
    r['asset_roles']['canopy']=[forest_asset]
    r['materials']['farmland']['color']=[.98,.94,.83,1]
    r['materials']['forest']['color']=[.7,.76,.6,1]
    directory=ROOT/'game/assets/registered'/forest_asset;top_view=directory/'source_albedo_view_3.png'
    if not forest_floor_only and not top_view.exists():raise FileNotFoundError('Register forest source '+forest_asset+' before building this map')
    forest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    if not forest_floor_only:
        r['materials']['forest']['canopy_proxy']={'asset':forest_asset,'tile_m':max(forest['bounds_blender']['span'])*1.06,'layers':4,'strength':1.,
            'source_sha256':hashlib.sha256(top_view.read_bytes()).hexdigest()}
    if (forest.get('cluster') or {}).get('ground_conform'):
        if not forest_floor_only:raise ValueError('Per-tree source grounding requires --forest-floor-only')
        r['landscape']['ground_atlas']={'origin_north':-10000,'origin_west':-10000,'spacing':5,'columns':4001,'rows':4001}
    r['airfields'][0].update(runway_width_m=45,taxi_offset_m=160,apron=[-2200,-3000],apron_size_m=[1100,400],hangars=6)
    r['rivers'][0].update(width_m=95,bank_width_m=120,points=[[-80000,600],[-10000,600],[-7000,820],[-5200,510],[-3400,140],[-1800,280],[-400,700],[1100,820],[2500,600],[4200,200],[6000,430],[8200,900],[10000,600],[80000,600]])
    r['roads']=[
        {'id':'airport_village','width_m':8,'points':[[-1400,-3000],[-1150,-2500],[-700,-2300],[-800,-4600],[-2100,-5000],[-3500,-5400]]},
        {'id':'village_link','width_m':9,'points':[[-3500,-5400],[-2500,-5100],[-800,-4600],[300,-4200],[1400,-2700],[2300,-2000],[2450,-600],[2500,600],[2800,1800],[4500,2400]]},
        {'id':'north_town','width_m':8,'points':[[1400,-2700],[2200,-3200],[3300,-2700],[4300,-1800],[6000,-1600],[8800,-1100]]},
        {'id':'regional_highway','width_m':12,'points':[[-10000,-7100],[-6500,-6300],[-3500,-5400],[-800,-4600],[1400,-2700],[3300,-2700],[6000,-1600],[10000,-600]]},
        {'id':'industrial_service','width_m':8,'points':[[2300,-2000],[2600,-1900],[2850,-1700],[2900,-1000]]},
        {'id':'industrial_cross','width_m':7,'points':[[2450,-2050],[2450,-1500],[2700,-1300],[2900,-1000]]},
        {'id':'south_lane','width_m':5,'points':[[-4100,-5700],[-3650,-5600],[-3300,-6000],[-2400,-6100]]},
        {'id':'town_lane','width_m':5,'points':[[2900,-3100],[3150,-3300],[3700,-3150],[4100,-2700]]}]
    r['settlements']=[{'id':'south_village','center':[-3500,-5400],'road':'village_link','houses':75,'radius_m':850,'height_m':250},
        {'id':'north_town','center':[3300,-2700],'road':'north_town','houses':90,'radius_m':1050,'height_m':210},
        {'id':'south_hamlet','center':[-3300,-6000],'road':'south_lane','houses':22,'radius_m':480,'height_m':250},
        {'id':'town_hamlet','center':[3700,-3150],'road':'town_lane','houses':24,'radius_m':450,'height_m':210}]
    for z in r['zones']:
        if z['type']=='industrial':z['polygon']=[[2100,-2200],[3100,-2050],[3200,-800],[2300,-700]]
        if z['id']=='sample_woodland':z['polygon']=[[-3900,-2200],[-3300,-1850],[-1900,-1800],[-1200,-2100],[-2000,-2400]]
    r['zones'].append({'id':'valley_west_woodland','type':'forest','polygon':[[-6500,-2200],[-4200,-1500],[-2500,-1800],[-1800,-800],[-400,-700],[-1000,-1800],[-3500,-2500],[-5300,-2900]]})
    for scatter in r['scatter_rules']:
        if scatter['roles']=='canopy' and (forest.get('cluster') or {}).get('ground_conform',{}).get('anchor_encoding')=='source_tree_index_uv1':scatter['spatial_batch_extent_m']=250
        if scatter['id']=='forest_canopy':scatter['count']=10000;scatter['zones'].extend(['valley_west_woodland','sample_woodland']);scatter['lod_distance_m']=900;scatter['area_weighted']=True
        elif scatter['id']=='riverbank_vegetation':scatter['count']=3000
        elif scatter['id']=='hedgerows':scatter['count']=1400
        elif scatter['id']=='sample_woodland':scatter['count']=200;scatter['lod_distance_m']=900
    # Reserve the declared local woodland first. Regional groves sample by area
    # so small polygons are not saturated while large forests remain empty.
    r['scatter_rules'].sort(key=lambda rule:rule['id']!='sample_woodland')
    r['mission'].update(player_start=[-7000,-3500,650],speed_mps=180,enemy_range_m=160000,target=[2650,-1400])
    if 'convoy_target' in r['mission']:r['mission']['convoy_target']=[2600,-1900]
    r['mission']['strike_start']=[-4500,-1900,3200]
    r['mission']['convoy_start']=[-20000,-1900,8500]
    r['mission']['ground_units']=[{'uid':'sam_1','model':'SLAMRAAM','kind':'sam','team':'red',
        'position':[2450,-1500,0],'missiles':2,'mission_target':True}]
    for i in range(3):
        n=2310-i*18;w=-2000+(n-2300)/3
        r['mission']['ground_units'].append({'uid':'convoy_'+str(i+1),'model':'WillysJeep','kind':'vehicle','team':'red',
            'position':[n,w,0],'mission_target':True,'route':{'points':[[n,w],[2600,-1900],[2850,-1700],[2900,-1000]],'speed':7,'loop':False}})
    r['detail_sample'].update(center=[-2500,-3000],size_m=[2000,2000],relief_amplitude_m=1.2,texture_resolution=2048,material_blend_m=24,
        roadside_signs=[{'position':[-1390,-2990],'yaw':0},{'position':[-790,-4590],'yaw':1.4}])
    r['exclusion_zones'][1].update(center=[-2200,-3000],size_m=[1250,600])
    r['bridges']=[{'id':'valley_crossing','road':'village_link','center':[2500,600],'length_m':480,'width_m':10,'ramp_length_m':100,'deck_height_m':140}]
    r['gates']=[]
    r['display_flight']={'minimum_seconds':180,'waypoints_nwu':[[-4500,-3500,550],[-2200,-2900,480],[0,-800,400],[2200,600,380],[3700,-2300,520],[5200,-1800,750],[7500,-1000,1200]],
        'sequence':['airfield','river_valley_low','town_turn','climb','observed_contact_approach'],'contact_rule':'Only true radar tracks may be selected; no hidden enemy coordinates'}
    return r

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--bake',action='store_true');p.add_argument('--output',type=Path,default=ROOT/'game/maps/river_valley_airfield')
    p.add_argument('--forest-asset',default='fir_grove_cards_c',help='Registered grove resource; earlier candidates: pine_grove_a or fir_grove_c')
    p.add_argument('--recipe-output',type=Path,default=ROOT/'game/recipes/river_valley_airfield.json',help='Save a candidate recipe separately while keeping the current default map recipe')
    p.add_argument('--outer-cover',action='store_true',help='Continue source-albedo land use across the full outer terrain')
    p.add_argument('--river-channel',action='store_true',help='Generate a shared physical riverbed and banks below a separate water surface; requires a full bake')
    p.add_argument('--forest-floor-only',action='store_true',help='Use source ground albedo under individual-tree 3D LODs, without ground-projected canopy imagery')
    p.add_argument('--rural-layout',action='store_true',help='Full bake: road-oriented recursive fields and area-uniform forest placement; requires --forest-floor-only')
    p.add_argument('--retexture-map',type=Path,help='Rebake materials of a verified immutable map, preserving all terrain and scene geometry')
    p.add_argument('--rebuild-forest-map',type=Path,help='Resample source trees through the existing Baker, preserving source terrain/material/contact/mission and ordinary placements')
    a=p.parse_args()
    if a.rebuild_forest_map and (a.retexture_map or a.river_channel or a.outer_cover or a.rural_layout):p.error('--rebuild-forest-map preserves terrain/materials; omit material/terrain rebake flags')
    if a.river_channel and a.retexture_map:p.error('--river-channel changes shared terrain and requires --bake, not --retexture-map')
    if a.forest_floor_only and a.retexture_map:p.error('--forest-floor-only requires a full bake with an individual-tree forest asset')
    if a.rural_layout and (a.retexture_map or not a.forest_floor_only):p.error('--rural-layout requires a full bake with --forest-floor-only')
    if a.retexture_map or a.rebuild_forest_map:
        source_map=a.retexture_map or a.rebuild_forest_map
        if a.recipe_output==ROOT/'game/recipes/river_valley_airfield.json':a.recipe_output=a.output/'scene-recipe.json'
        source_pointer=json.loads(source_map.read_text(encoding='utf8'))
        if source_pointer.get('data_version'):
            source_map=source_map.parent/'versions'/source_pointer['data_version']/'generated-map.json'
        if a.retexture_map:a.retexture_map=source_map
        else:a.rebuild_forest_map=source_map
        if a.output.resolve()==source_map.resolve().parent:p.error('Use a separate candidate output directory')
        r=json.loads((source_map.parent/'scene-recipe.json').read_text(encoding='utf8'))
        if a.rebuild_forest_map:
            forest=json.loads((ROOT/'game/assets/registered'/a.forest_asset/'manifest.json').read_text(encoding='utf8'))
            if not (forest.get('cluster') or {}).get('ground_conform',{}).get('anchor_encoding')=='source_tree_index_uv1':p.error('--rebuild-forest-map requires an independent source-tree resource')
            if r['materials']['forest'].get('canopy_proxy'):p.error('Rebuild a source map with forest-floor-only materials')
            r['asset_roles']['canopy']=[a.forest_asset]
            for rule in r['scatter_rules']:
                if rule['roles']=='canopy':rule['spatial_batch_extent_m']=250
    else:r=recipe(a.forest_asset,a.forest_floor_only)
    if a.outer_cover:r['landscape']['outer_surface']={'resolution':4096,'field_size_m':900,'forest_scale_m':3600,'focus_blend_m':2200}
    if a.river_channel:
        r['landscape']['river_channel']={'depth_m':4.,'bank_width_m':22.,'bank_height_m':.8,
            'provenance':'Authored 4m channel cross section; not measured bathymetry or fluid simulation'}
        r['materials']['water']['color']=[.045,.075,.055,.65]
    if a.forest_floor_only:
        forest=json.loads((ROOT/'game/assets/registered'/a.forest_asset/'manifest.json').read_text(encoding='utf8'))
        if not (forest.get('impostor') or {}).get('source_trees'):p.error('--forest-floor-only requires individual-tree far LODs; select a registered asset such as fir_grove_normal_a')
        r['materials']['forest'].pop('canopy_proxy',None)
        r['landscape']['forest_floor_note']='Source ground albedo and actual individual-tree 3D LODs; no ground-projected canopy preview'
    if a.rural_layout:
        r['landscape']['field_layout']='road_recursive'
        r['landscape']['rural_parcels']={'area_range_m2':[30000,280000],
            'palette_linear':[[.88,.91,.86,1],[.94,.93,.87,1],[.85,.90,.82,1],[.94,.94,.92,1]],
            'field_margin_m':4.,'tint_blend_m':8.,'forest_ground_source_mean':True}
        r['landscape']['field_layout_note']='Shared recursive boundaries follow nearby road directions; smaller areas on slopes, source grass/soil cover and4mgrass margins. Authored appearance, not GIS.'
        for rule in r['scatter_rules']:
            if rule['roles']=='canopy':rule['distribution']='area_uniform'
    write_json(a.recipe_output,r)
    if a.bake or a.retexture_map or a.rebuild_forest_map:
        from bvr_game.worldgen import Baker
        from bvr_game.scene_runtime import BakedScene
        from bvr_game.content import sha
        import numpy as np
        # Complete and verify an immutable data version before publishing one
        # root map pointer. A failed bake cannot corrupt the last working map.
        a.output=a.output.resolve();stage=a.output/('._bake-'+uuid.uuid4().hex)
        if a.rebuild_forest_map:
            from bvr_game.source_tree_layout import rebuild_forests
            from bvr_game.worldgen import canonical
            original=BakedScene(a.rebuild_forest_map);doc=json.loads(json.dumps(original.document));stage.mkdir(parents=True,exist_ok=False)
            shutil.copy2(original.height_file,stage/'terrain.npz');doc['terrain']['file']='terrain.npz'
            from bvr_game.ground_atlas import copy_or_build_atlas
            doc['terrain']['ground_atlas']=copy_or_build_atlas(original,doc['terrain'],stage)
            doc=rebuild_forests(r,original,doc);doc['recipe_sha256']=hashlib.sha256(canonical(r)).hexdigest()
            for key in ['surfaces','mission','fields','roads','rivers','airfields','settlements']:assert doc[key]==original.document[key],key
            for key in ['contact_surfaces','obstacles','water_regions']:assert doc['environment'][key]==original.document['environment'][key],key
            assert sha(stage/'terrain.npz')==original.document['terrain']['sha256']
            write_json(stage/'scene-recipe.json',r);write_json(stage/'generated-map.json',doc)
            report={'instances':len(doc['instances']),'counts':doc['counts'],'operation':'Source trees resampled; original terrain/materials/contact/mission/ordinary placements retained','source_map':str(a.rebuild_forest_map.resolve()),'source_map_sha256':sha(a.rebuild_forest_map)}
        elif a.retexture_map:
            from bvr_game.worldgen import BakedTerrain,canonical
            from bvr_game.detail_bake import _bake_material
            from bvr_game.regional_cover import bake_outer_cover
            original=BakedScene(a.retexture_map);doc=json.loads(json.dumps(original.document));arrays=original.arrays
            stage.mkdir(parents=True,exist_ok=False);shutil.copy2(original.height_file,stage/'terrain.npz');doc['terrain']['file']='terrain.npz'
            baker=Baker(r);baker.terrain=BakedTerrain(arrays['base'],arrays['focus'],doc['terrain']['base'],doc['terrain']['details'][0])
            bake_outer_cover(baker,doc,arrays,stage)
            regional={**r['detail_sample'],'size_m':[x*1000 for x in r['focus_area_km']],
                'texture_resolution':r['landscape']['macro_resolution'],
                'seam_blend_m':r['landscape'].get('outer_surface',{}).get('focus_blend_m',r['landscape']['regional_transition_m']),
                'material_detail_strength':.65,'macro_source_tile_m':160}
            _bake_material(doc,arrays,doc['terrain']['details'][0],regional,stage,baker,material_id='regional_1',prefix='regional')
            doc['materials']['regional_1'].update(world_uv=True,uv_origin_north=doc['terrain']['details'][0]['origin_north'],uv_origin_west=doc['terrain']['details'][0]['origin_west'])
            doc['landscape']=r['landscape'];doc['recipe_sha256']=hashlib.sha256(canonical(r)).hexdigest()
            assert sha(stage/'terrain.npz')==original.document['terrain']['sha256']
            for key in ['instances','surfaces','environment','mission','resource_versions']:assert doc[key]==original.document[key],key
            write_json(stage/'scene-recipe.json',r);write_json(stage/'generated-map.json',doc)
            report={'instances':len(doc['instances']),'counts':doc['counts'],'operation':'Material-only rebake; exact terrain, instances, surfaces, environment, mission and registered model versions preserved','source_map':str(a.retexture_map.resolve()),'source_map_sha256':sha(a.retexture_map)}
        else:report=Baker(r).bake(stage)
        doc=json.loads((stage/'generated-map.json').read_text(encoding='utf-8'))
        arrays=np.load(stage/'terrain.npz',allow_pickle=False);fine=arrays['sample']
        if not np.isfinite(fine).all() or max(np.max(abs(np.diff(fine,axis=0))),np.max(abs(np.diff(fine,axis=1))))>25:
            raise ValueError('Airfield fine terrain contains a nonphysical discontinuity; failed staging data retained')
        def relocate(value,destination):
            if isinstance(value,str):return value.replace(str(stage),destination)
            if isinstance(value,list):return [relocate(v,destination) for v in value]
            if isinstance(value,dict):return {relocate(k,destination):relocate(v,destination) for k,v in value.items()}
            return value
        normalized=json.dumps(relocate(doc,'<MAP_VERSION>'),sort_keys=True,separators=(',',':')).encode('utf-8')
        id=hashlib.sha256(normalized).hexdigest()[:24];version=a.output/'versions'/id;version.mkdir(parents=True,exist_ok=True)
        for file in stage.iterdir():
            if not file.is_file() or file.name=='generated-map.json':continue
            dest=version/file.name
            if dest.exists() and sha(dest)!=sha(file):raise ValueError('Immutable map version collision: '+str(dest))
            if not dest.exists():shutil.copy2(file,dest)
        resolved=relocate(doc,str(version));version_map=version/'generated-map.json'
        if version_map.exists():
            if json.loads(version_map.read_text(encoding='utf8'))!=resolved:raise ValueError('Immutable map document collision: '+str(version_map))
        else:write_json(version_map,resolved)
        BakedScene(version/'generated-map.json')
        from bvr_game.mapcheck import validate
        spatial=validate(version_map);write_json(version/'spatial-validation.json',spatial)
        if spatial['status']!='passed':raise ValueError('Candidate spatial validation failed; immutable/staging evidence retained without publishing root pointer')
        published={**resolved,'terrain':{**resolved['terrain'],'file':f'versions/{id}/terrain.npz'},'data_version':id}
        pointer=a.output/'generated-map.json';temporary=pointer.with_suffix('.pending.json');write_json(temporary,published);temporary.replace(pointer)
        print(json.dumps({**report,'map':str(pointer),'generated_map_sha256':sha(pointer),'data_version':id,'version_directory':str(version),
            'fine_height_min_max':[float(fine.min()),float(fine.max())],'publication':'Atomic root pointer after full immutable-version validation; staging data retained for diagnosis'},ensure_ascii=False,indent=2))
    else:print(a.recipe_output)
if __name__=='__main__':main()
